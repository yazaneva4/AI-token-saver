"""Compression verification on realistic datasets, with a real tokenizer and preservation checks.

    python benchmarks/compression_round2.py [--size 1000000] [--baseline-ref origin/main] [--json out.json]

For every dataset it reports original and output tokens, the reduction, processing time, peak
memory, and whether information was preserved (run with redaction off, so only compaction is
measured). Token counts use the Tekken BPE tokenizer when ``mistral-common`` is installed
(a real subword tokenizer, but NOT Claude's); otherwise the approximate chars/4 counter, which
is labelled as such. The "best case" row is synthetic padding; the other rows are typical.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import tracemalloc

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ai_token_saver as new  # noqa: E402
from datasets_round2 import DATASETS  # noqa: E402


def load_baseline(ref):
    source = subprocess.run(["git", "show", f"{ref}:ai_token_saver.py"], cwd=os.path.dirname(HERE), capture_output=True,
                            text=True, check=True).stdout
    path = os.path.join(tempfile.mkdtemp(), "ai_token_saver_baseline.py")
    open(path, "w", encoding="utf-8").write(source)
    spec = importlib.util.spec_from_file_location("ai_token_saver_baseline", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_token_saver_baseline"] = module
    spec.loader.exec_module(module)
    return module


def tokenizer():
    try:
        import mistral_common
        from mistral_common.tokens.tokenizers.tekken import Tekkenizer
        tekken = Tekkenizer.from_file(os.path.join(os.path.dirname(mistral_common.__file__), "data", "tekken_240911.json"))
        return "Tekken BPE (mistral-common 240911; not Claude's tokenizer)", lambda t: len(tekken.encode(t, bos=False, eos=False))
    except Exception:  # noqa: BLE001 - optional dependency
        return "approximate chars/4 (no real tokenizer installed)", lambda t: new.estimate_tokens(t)


def norm(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def distinct_lines(text):
    return {line.rstrip() for line in norm(text).split("\n") if line.strip()}


def checks(name, original, output):
    """Information-preservation results for one document (compaction only, redaction off)."""
    result = {"lost_distinct_lines": len(distinct_lines(original) - distinct_lines(output))}
    if "Python" in name:
        try:
            ast.parse(original)
        except (SyntaxError, ValueError):
            result["syntax"] = "n/a"
        else:
            result["syntax"] = "ok" if _parses(output) and ast.dump(ast.parse(original)) == ast.dump(ast.parse(output)) else "CHANGED"
    if "JSON" in name:
        try:
            result["syntax"] = "ok" if json.loads(output) == json.loads(original) else "CHANGED"
        except ValueError:
            result["syntax"] = "n/a"
    if "YAML" in name:
        try:
            import yaml
            before = list(yaml.safe_load_all(original))
        except Exception:  # noqa: BLE001 - tags/aliases the safe loader refuses
            result["syntax"] = "n/a"
        else:
            result["syntax"] = "ok" if list(yaml.safe_load_all(output)) == before else "CHANGED"
    events_before = sum(1 for line in norm(original).split("\n") if new._EVENT_RECORD.search(line))
    events_after = sum(1 for line in norm(output).split("\n") if new._EVENT_RECORD.search(line))
    result["event_lines_kept"] = events_after >= events_before
    result["exact"] = output == norm(original)
    return result


def _parses(text):
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def measure(module, docs, **kwargs):
    outputs, elapsed, peak = [], 0.0, 0
    for doc in docs:
        tracemalloc.start()
        start = time.perf_counter()
        outputs.append(module.compact_text(doc, redact_secrets=False, **kwargs))
        elapsed += time.perf_counter() - start
        peak = max(peak, tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return outputs, elapsed, peak


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size", type=int, default=1_000_000)
    parser.add_argument("--baseline-ref", default="origin/main", help='git ref to compare against, or "none"')
    parser.add_argument("--json")
    args = parser.parse_args()
    old = new if args.baseline_ref == "none" else load_baseline(args.baseline_ref)  # "none": compare with itself
    tok_name, count = tokenizer()
    print(f"tokenizer: {tok_name}\nbaseline : {args.baseline_ref}   input size target: {args.size} chars per dataset\n")
    header = f"{'dataset':34}{'docs':>5}{'tok in':>9}{'tok out':>9}{'saved':>8}{'old out':>9}{'old lost':>9}{'new lost':>9}  {'ms':>7} {'peak KB':>8}  preservation"
    print(header)
    rows = []
    for name, build in DATASETS.items():
        docs = build(args.size)
        t_in = sum(count(d) for d in docs)
        out, secs, peak = measure(new, docs)
        old_out, _, _ = measure(old, docs)
        t_out, t_old = sum(count(o) for o in out), sum(count(o) for o in old_out)
        per_doc = [checks(name, d, o) for d, o in zip(docs, out)]
        old_per_doc = [checks(name, d, o) for d, o in zip(docs, old_out)]
        lost, old_lost = sum(c["lost_distinct_lines"] for c in per_doc), sum(c["lost_distinct_lines"] for c in old_per_doc)
        syntax = {c.get("syntax") for c in per_doc} - {None, "n/a"}
        old_syntax = {c.get("syntax") for c in old_per_doc} - {None, "n/a"}
        exact = sum(c["exact"] for c in per_doc)
        status = []
        if syntax:
            status.append("syntax " + "/".join(sorted(syntax)) + (f" (old: {'/'.join(sorted(old_syntax))})" if old_syntax != syntax else ""))
        status.append(f"{exact}/{len(docs)} docs byte-identical")
        status.append("events kept" if all(c["event_lines_kept"] for c in per_doc) else "EVENTS LOST")
        saved = 100 * (1 - t_out / t_in) if t_in else 0.0
        print(f"{name:34}{len(docs):>5}{t_in:>9}{t_out:>9}{saved:>7.2f}%{t_old:>9}{old_lost:>9}{lost:>9}  {secs * 1000:>7.0f} {peak / 1024:>8.0f}  {'; '.join(status)}")
        rows.append({"dataset": name, "docs": len(docs), "tokens_in": t_in, "tokens_out": t_out, "saved_pct": round(saved, 2),
                     "baseline_tokens_out": t_old, "baseline_lost_distinct_lines": old_lost, "lost_distinct_lines": lost,
                     "ms": round(secs * 1000), "peak_kb": round(peak / 1024), "preservation": status, "tokenizer": tok_name})
    if args.json:
        json.dump(rows, open(args.json, "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
