"""Compare a baseline ai_token_saver.py with the working tree: tokens, time, peak memory.

    python benchmarks/audit_compare.py [--baseline-ref origin/main] [--large-mb 5]

Token counts use the Tekken BPE tokenizer when ``mistral-common`` is installed (a real
subword tokenizer, but NOT Claude's); otherwise the repo's approximate chars/4 counter.
Numbers are never tuned: a lower reduction after a fix means information was kept.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ai_token_saver as new  # noqa: E402


def load_baseline(ref: str):
    source = subprocess.run(["git", "show", f"{ref}:ai_token_saver.py"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout
    path = os.path.join(tempfile.mkdtemp(), "ai_token_saver_baseline.py")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    spec = importlib.util.spec_from_file_location("ai_token_saver_baseline", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_token_saver_baseline"] = module
    spec.loader.exec_module(module)
    return module


def tokenizer():
    try:
        import mistral_common
        from mistral_common.tokens.tokenizers.tekken import Tekkenizer
        path = os.path.join(os.path.dirname(mistral_common.__file__), "data", "tekken_240911.json")
        tekken = Tekkenizer.from_file(path)
        return "tekken-bpe", lambda text: len(tekken.encode(text, bos=False, eos=False))
    except Exception:  # noqa: BLE001 - optional dependency
        return "approx chars/4", lambda text: new.estimate_tokens(text)


def workloads() -> dict[str, str]:
    para = "The project state is important and must be saved accurately.\n"
    return {
        "prose, padded repeats": para * 400,
        "markdown with paragraphs": "".join(f"# Section {i}\n\nText about topic {i % 5}.\n\nMore text {i % 5}.\n\n" for i in range(150)),
        "python source": "".join(f"def f{i}(x):\n    return x + {i}\n\n\n" for i in range(150)),
        "json pretty": json.dumps({"items": [{"id": i % 20, "tag": "a"} for i in range(300)]}, indent=2),
        "yaml sequences": "items:\n" + "".join("  - 1\n  - 1\n  - 2\n" for _ in range(200)),
        "service logs (repeated events)": "".join(f"2024-01-01 12:00:{i % 60:02d} ERROR db timeout\n" * 3 for i in range(200)),
        "varied notes (no repetition)": "".join(f"Decision {i}: module_{i}.py uses timeout={i * 10}s\n" for i in range(300)),
        "config with secrets": 'api_key=abc123def456\n{"password": "hunter2", "host": "x"}\nuser: admin\n' * 50,
    }


def measure(fn, text: str, repeats: int = 3):
    times, peak = [], 0
    out = ""
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        out = fn(text)
        times.append((time.perf_counter() - start) * 1000)
        peak = max(peak, tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return out, statistics.median(times), peak / 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline-ref", default="origin/main")
    parser.add_argument("--large-mb", type=float, default=5.0)
    args = parser.parse_args()
    old = load_baseline(args.baseline_ref)
    name, count = tokenizer()
    print(f"tokenizer: {name}   baseline: {args.baseline_ref}\n")
    print(f"{'workload':32}{'tok in':>8}{'old out':>9}{'old %':>8}{'new out':>9}{'new %':>8}  batch==stream(new)")
    for label, text in workloads().items():
        before, after = old.compact_text(text), new.compact_text(text)
        chunks = [text[i:i + 7] for i in range(0, len(text), 7)]
        same = "".join(new.compact_stream(chunks)) == after
        t_in, t_old, t_new = count(text), count(before), count(after)
        print(f"{label:32}{t_in:>8}{t_old:>9}{100 * (1 - t_old / t_in):>7.1f}%{t_new:>9}{100 * (1 - t_new / t_in):>7.1f}%  {same}")
    big = ("Paragraph about the project state.\nPlain sentence number one.\n\n" * 20000)
    big = (big * max(1, int(args.large_mb * 1024 * 1024 / len(big))))
    print(f"\nlarge input: {len(big) / 1e6:.1f} MB")
    for label, mod in (("baseline", old), ("fixed", new)):
        out, ms, peak_kb = measure(mod.compact_text, big)
        print(f"  {label:9} batch  {ms:9.1f} ms  peak {peak_kb / 1024:8.1f} MB  out {len(out) / 1e6:.2f} MB")
    unique = "".join(f"Note {i}: observation number {i} about module_{i % 977}.py\n" for i in range(int(args.large_mb * 1e6 / 56)))
    print(f"large input, all lines unique: {len(unique) / 1e6:.1f} MB")
    for label, mod in (("baseline", old), ("fixed", new)):
        out, ms, peak_kb = measure(mod.compact_text, unique, repeats=1)
        print(f"  {label:9} batch  {ms:9.1f} ms  peak {peak_kb / 1024:8.1f} MB")
    chunks = [big[i:i + 4096] for i in range(0, len(big), 4096)]
    out, ms, peak_kb = measure(lambda _t: "".join(new.compact_stream(chunks)), big)
    print(f"  fixed     stream {ms:9.1f} ms  peak {peak_kb / 1024:8.1f} MB  out {len(out) / 1e6:.2f} MB")
    one_char = big[:300_000]
    out, ms, peak_kb = measure(lambda t: "".join(new.compact_stream(iter(t))), one_char)
    print(f"  fixed     1-char chunks x{len(one_char)} {ms:9.1f} ms  peak {peak_kb / 1024:8.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
