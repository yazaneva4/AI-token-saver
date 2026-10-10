"""Bounded stress test: runtime, peak memory, throughput and failures per case.

    python benchmarks/stress_round2.py [--max-mb 100] [--timeout 300] [--memory-gb 8] [--json out.json]

Every case runs in its own subprocess with an address-space limit and a wall-clock timeout, so a
runaway case is stopped and reported instead of taking the machine down. "extra MB" is peak
resident memory above what the process held after building the input, i.e. the engine's own
working memory.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import resource
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("AITS_ENGINE_DIR"):  # run the same cases against another checkout of the engine
    sys.path.insert(0, os.environ["AITS_ENGINE_DIR"])

KB, MB = 1_000, 1_000_000
SIZES = [KB, 100 * KB, MB, 10 * MB, 100 * MB]


def _rss_kb():
    with open("/proc/self/statm") as handle:
        return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // 1024


def build(kind, size):
    from datasets_round2 import (agent_conversation, javascript_source, multilingual, python_source)
    line_unique = lambda i: f"Note {i}: observation number {i} about module_{i % 977}.py\n"
    if kind == "repeated":
        unit = "The project state is important and must be saved accurately.\n"
        return unit * (size // len(unit) or 1)
    if kind == "unique":
        return "".join(line_unique(i) for i in range(size // 56 or 1))[:size]
    if kind == "python":
        text = "".join(python_source(min(size, 5 * MB)))
    elif kind == "javascript":
        text = "".join(javascript_source(min(size, 5 * MB)))
    elif kind == "agent":
        text = "".join(agent_conversation(min(size, 5 * MB)))
    elif kind == "multilingual":
        text = "".join(multilingual(min(size, 5 * MB)))
    elif kind == "json":
        rng = random.Random(2)
        text = json.dumps([{"id": i % 50, "ok": rng.random() < 0.7, "tags": ["a", "a"]} for i in range(size // 60 or 1)], indent=1)
    elif kind == "yaml":
        text = "".join(f"- name: item{i % 40}\n  tags: [a, a]\n  value: {i % 7}\n" for i in range(size // 50 or 1))
    elif kind == "secrets":
        text = "".join(f"DB_PASSWORD=hunter{i}\napi_key=abc{i}def\nnormal line {i}\n" for i in range(size // 50 or 1))
    else:
        raise ValueError(kind)
    return (text * (size // len(text) + 1))[:size] if text else text


def run_case(case):
    """Runs inside the child process. Returns a result dict."""
    import ai_token_saver as m
    kind, size, mode = case["kind"], case["size"], case["mode"]
    if mode == "special":
        text = special_input(kind, size)
    else:
        text = build(kind, size)
    base = _rss_kb()
    start = time.perf_counter()
    note = ""
    if mode == "batch":
        out = m.compact_text(text)
    elif mode == "stream":
        sizes = {"fixed": [4096], "random": None, "char": [1]}[case["chunking"]]
        rng = random.Random(11)
        chunks, pos = [], 0
        while pos < len(text):
            n = sizes[0] if sizes else rng.randint(1, 50)
            chunks.append(text[pos:pos + n])
            pos += n
        start = time.perf_counter()
        out = "".join(m.compact_stream(chunks))
        elapsed_stream = time.perf_counter() - start  # verification below is not part of the measurement
        if case.get("verify"):
            note = "stream==batch" if out == m.compact_text(text) else "STREAM!=BATCH"
    elif mode == "special":
        out = m.compact_text(text)
    elif mode == "threads":
        outs = [None] * 8
        pieces = [text[i::8] for i in range(8)] if False else [text] * 8
        threads = [threading.Thread(target=lambda i=i: outs.__setitem__(i, m.compact_text(pieces[i]))) for i in range(8)]
        start = time.perf_counter()
        [t.start() for t in threads]
        [t.join() for t in threads]
        out = outs[0]
        note = "8 threads equal" if all(o == outs[0] for o in outs) else "THREAD RESULTS DIFFER"
        text = text * 8
    else:
        raise ValueError(mode)
    elapsed = elapsed_stream if mode == "stream" else time.perf_counter() - start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"chars_in": len(text), "chars_out": len(out), "seconds": round(elapsed, 3),
            "mb_per_s": round(len(text) / MB / elapsed, 2) if elapsed else None,
            "extra_mb": round(max(peak - base, 0) / 1024, 1), "note": note}


def special_input(kind, size):
    if kind == "empty":
        return ""
    if kind == "newlines":
        return "\n" * size
    if kind == "crlf_lines":
        return "line of text\r\n" * (size // 14)
    if kind == "lone_cr":
        return "ab\r" * (size // 3)
    if kind == "nul_bytes":
        return "ab\x00cd\n" * (size // 6)
    if kind == "single_line":
        return "x" * size
    if kind == "surrogates":
        return "bad \ud800 line\n" * (size // 14)
    if kind == "lines_100k_repeated":
        return "The service is healthy and responding to requests.\n" * 100_000
    if kind == "lines_100k_events":
        return "2026-10-10 12:00:00 ERROR upstream timeout\n" * 100_000
    if kind == "nested_json_line":
        return "[" * (size // 2) + "]" * (size // 2) + "\n"
    if kind == "secret_block_unclosed":
        return 'password = [\n' + '  "x",\n' * (size // 7)
    if kind == "pem_blocks":
        return ("-----BEGIN PRIVATE KEY-----\n" + "A" * 64 + "\n" * 1 + "-----END PRIVATE KEY-----\n") * (size // 150)
    if kind == "malformed_json":
        return '{"a": [1, 2, {"b": ' * (size // 20)
    if kind == "binary_like":
        return "".join(chr(random.Random(5).randint(1, 0x2FF)) for _ in range(size // 20)) * 20
    raise ValueError(kind)


def cases(max_mb):
    out = []
    for kind in ("repeated", "unique", "python", "javascript", "multilingual", "agent", "json", "yaml", "secrets"):
        for size in SIZES:
            heavy = size >= 100 * MB
            if size > max_mb * MB or (heavy and kind not in ("repeated", "unique", "python", "agent", "secrets")):
                continue
            out.append({"id": f"batch/{kind}/{size // KB}KB", "kind": kind, "size": size, "mode": "batch"})
    for kind in ("repeated", "python", "agent", "unique"):
        for chunking, size in (("fixed", 10 * MB), ("random", 10 * MB), ("char", MB)):
            if size <= max_mb * MB:
                out.append({"id": f"stream/{kind}/{chunking}/{size // KB}KB", "kind": kind, "size": size, "mode": "stream", "chunking": chunking, "verify": size <= 10 * MB})
    for kind, size in (("empty", 0), ("newlines", MB), ("newlines", 10 * MB), ("crlf_lines", 10 * MB), ("lone_cr", 10 * MB), ("nul_bytes", 10 * MB),
                       ("single_line", 50 * MB), ("surrogates", MB), ("lines_100k_repeated", 0), ("lines_100k_events", 0), ("nested_json_line", MB),
                       ("secret_block_unclosed", 5 * MB), ("pem_blocks", 10 * MB), ("malformed_json", 5 * MB), ("binary_like", MB)):
        if size <= max_mb * MB:
            out.append({"id": f"special/{kind}/{size // KB}KB", "kind": kind, "size": size, "mode": "special"})
    out.append({"id": "concurrent/threads/8x1MB", "kind": "agent", "size": MB, "mode": "threads"})
    return out


def child(case_json):
    case = json.loads(case_json)
    try:
        print(json.dumps({"ok": True, **run_case(case)}))
    except MemoryError:
        print(json.dumps({"ok": False, "error": "MemoryError (limit reached)"}))
    except Exception as exc:  # noqa: BLE001 - report every failure
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-mb", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--memory-gb", type=float, default=8)
    parser.add_argument("--only", help="substring filter on case ids")
    parser.add_argument("--engine-dir", help="directory holding another ai_token_saver.py to measure (baseline)")
    parser.add_argument("--json")
    parser.add_argument("--child")
    args = parser.parse_args()
    if args.child:
        return child(args.child)
    if args.engine_dir:
        os.environ["AITS_ENGINE_DIR"] = os.path.abspath(args.engine_dir)
    limit = int(args.memory_gb * 1024 ** 3)
    results = []
    print(f"{'case':44}{'in MB':>8}{'seconds':>9}{'MB/s':>8}{'extra MB':>10}  result")
    for case in cases(args.max_mb):
        if args.only and args.only not in case["id"]:
            continue
        try:
            done = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", json.dumps(case)], capture_output=True, text=True,
                                  timeout=args.timeout, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_AS, (limit, limit)))
            result = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {"ok": False, "error": f"no output (exit {done.returncode}) {done.stderr[-120:]}"}
        except subprocess.TimeoutExpired:
            result = {"ok": False, "error": f"TIMEOUT after {args.timeout}s"}
        results.append({"case": case["id"], **result})
        if result["ok"]:
            print(f"{case['id']:44}{result['chars_in'] / MB:>8.2f}{result['seconds']:>9.2f}{result['mb_per_s'] or 0:>8.2f}{result['extra_mb']:>10.1f}  ok {result['note']}")
        else:
            print(f"{case['id']:44}{'':>8}{'':>9}{'':>8}{'':>10}  FAIL {result['error']}")
        sys.stdout.flush()
    if args.json:
        json.dump(results, open(args.json, "w"), indent=2)
    failed = [r for r in results if not r["ok"] or "!=" in r.get("note", "") or "DIFFER" in r.get("note", "")]
    print(f"\n{len(results)} cases, {len(failed)} failed or inconsistent")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
