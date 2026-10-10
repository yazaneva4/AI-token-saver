"""Compression verification on realistic datasets, with a real tokenizer and preservation checks.

    python benchmarks/compression_round2.py [--size 1000000] [--json out.json]

Every dataset is compacted four ways, with secret redaction OFF so that only compaction is measured:

  default    dedupe="off"      keeps every line (collapses blank-line runs only). Information-preserving.
  runs       dedupe="runs"     long identical runs become the line plus a count. Information-preserving:
                               expanding the markers must reproduce the input (verified here).
  adjacent   dedupe="adjacent" LOSSY. Drops repeated neighbouring prose lines; the number of dropped
                               occurrences is reported next to the saving.
  global     dedupe="global"   LOSSY. Drops any repeated prose line.

Token counts use the Tekken BPE tokenizer when ``mistral-common`` is installed (a real subword
tokenizer, but NOT Claude's); otherwise the approximate chars/4 counter, labelled as such. The
"best case" row is synthetic padding; every other row is typical text.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
import tracemalloc
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ai_token_saver as engine  # noqa: E402
from datasets_round2 import DATASETS  # noqa: E402

MODES = {"default": "off", "runs": "runs", "adjacent": "adjacent", "global": "global"}
_MARKER = re.compile(r"^\[previous line repeated (\d+) more times\]$")


def tokenizer():
    try:
        import mistral_common
        from mistral_common.tokens.tokenizers.tekken import Tekkenizer
        tekken = Tekkenizer.from_file(os.path.join(os.path.dirname(mistral_common.__file__), "data", "tekken_240911.json"))
        return "Tekken BPE (mistral-common 240911; not Claude's tokenizer)", lambda t: len(tekken.encode(t, bos=False, eos=False))
    except Exception:  # noqa: BLE001 - optional dependency
        return "approximate chars/4 (no real tokenizer installed)", lambda t: engine.estimate_tokens(t)


def norm(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def nonblank(text):
    return [line for line in norm(text).split("\n") if line.strip()]


def expand_runs(text):
    """Undo dedupe="runs": rebuild the repeated lines from their count markers."""
    out, previous = [], None
    for line in norm(text).split("\n"):
        match = _MARKER.match(line)
        if match and previous is not None:
            out.extend([previous] * int(match.group(1)))
        else:
            out.append(line)
            previous = line
    return "\n".join(out)


def syntax_ok(name, original, output):
    """Structured datasets must parse to the same value; None when not applicable."""
    if "Python" in name:
        try:
            ast.parse(original)
        except (SyntaxError, ValueError):
            return None
        try:
            return ast.dump(ast.parse(original)) == ast.dump(ast.parse(output))
        except (SyntaxError, ValueError):
            return False
    if "JSON" in name:
        try:
            before = json.loads(original)
        except ValueError:
            return None
        try:
            return json.loads(output) == before
        except ValueError:
            return False
    if "YAML" in name:
        try:
            import yaml
            before = list(yaml.safe_load_all(original))
        except Exception:  # noqa: BLE001 - PyYAML missing, or tags the safe loader refuses
            return None
        try:
            return list(yaml.safe_load_all(output)) == before
        except Exception:  # noqa: BLE001
            return False
    return None


def run_mode(docs, mode):
    outputs, seconds, peak = [], 0.0, 0
    for doc in docs:
        tracemalloc.start()
        start = time.perf_counter()
        outputs.append(engine.compact_text(doc, redact_secrets=False, dedupe=mode))
        seconds += time.perf_counter() - start
        peak = max(peak, tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return outputs, seconds, peak


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size", type=int, default=1_000_000)
    parser.add_argument("--json")
    args = parser.parse_args()
    tok_name, count = tokenizer()
    print(f"tokenizer: {tok_name}\ninput size target: {args.size} chars per dataset; redaction OFF (compaction only)\n")
    print(f"{'dataset':42}{'tok in':>9} | {'default':>8} {'intact':>7} | {'runs':>8} {'lossless':>9} | {'adjacent':>9} {'dropped':>8} | {'global':>8}  parse")
    rows = []
    for name, build in DATASETS.items():
        docs = build(args.size)
        t_in = sum(count(d) for d in docs)
        before = sum(len(nonblank(d)) for d in docs)
        row = {"dataset": name, "docs": len(docs), "tokens_in": t_in, "tokenizer": tok_name}
        for label, mode in MODES.items():
            outputs, seconds, peak = run_mode(docs, mode)
            tokens = sum(count(o) for o in outputs)
            saved = round(100 * (1 - tokens / t_in), 2) if t_in else 0.0
            if label == "runs":
                lossless = all(Counter(nonblank(expand_runs(o))) == Counter(nonblank(d)) for d, o in zip(docs, outputs))
                dropped = 0
            elif label == "default":  # every line, with its repeat count, must still be there
                lossless = all(Counter(nonblank(o)) == Counter(nonblank(d)) for d, o in zip(docs, outputs))
                dropped = before - sum(len(nonblank(o)) for o in outputs)
            else:
                lossless = None
                dropped = before - sum(len(nonblank(o)) for o in outputs)
            parse = {syntax_ok(name, d, o) for d, o in zip(docs, outputs)} - {None}
            row[label] = {"tokens_out": tokens, "saved_pct": saved, "lossless": lossless, "dropped_lines": dropped,
                          "parse_ok": (parse == {True}) if parse else None, "ms": round(seconds * 1000), "peak_kb": round(peak / 1024)}
        rows.append(row)
        flag = lambda v: "-" if v is None else ("yes" if v else "NO")
        parse = {r["parse_ok"] for r in (row[m] for m in MODES) if r["parse_ok"] is not None}
        print(f"{name:42}{t_in:>9} | {row['default']['saved_pct']:>7.2f}% {flag(row['default']['lossless']):>7} | {row['runs']['saved_pct']:>7.2f}% {flag(row['runs']['lossless']):>9} | "
              f"{row['adjacent']['saved_pct']:>8.2f}% {row['adjacent']['dropped_lines']:>8} | {row['global']['saved_pct']:>7.2f}%  "
              f"{'ok' if parse == {True} else ('n/a' if not parse else 'CHANGED')}")
    if args.json:
        json.dump(rows, open(args.json, "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
