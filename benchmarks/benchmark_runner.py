"""Dependency-free benchmark harness for AI Token Saver.

The runner measures real behavior of the public compaction APIs. It is intentionally
small enough to run in CI and can emit JSON for local inspection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
import statistics
import time
from typing import Callable, Iterable

from ai_token_saver import Memory, RealtimeCompactor, compact_stream, compact_text_with_metrics, merge_memory


@dataclass
class BenchmarkResult:
    name: str
    elapsed_ms: float
    input_chars: int
    output_chars: int
    input_tokens: int
    output_tokens: int
    reduction_percent: float
    passed: bool


def _measure(name: str, text: str, fn: Callable[[str], str], repeats: int = 3) -> BenchmarkResult:
    timings: list[float] = []
    output = ""
    for _ in range(repeats):
        start = time.perf_counter()
        output = fn(text)
        timings.append((time.perf_counter() - start) * 1000.0)
    metrics = compact_text_with_metrics(text, redact_secrets=False)
    return BenchmarkResult(
        name=name,
        elapsed_ms=statistics.median(timings),
        input_chars=len(text),
        output_chars=len(output),
        input_tokens=metrics.in_tokens,
        output_tokens=metrics.out_tokens,
        reduction_percent=metrics.token_change_percent,
        passed=isinstance(output, str) and len(output) <= len(text),
    )


def _stream_compact(text: str, chunk_size: int) -> str:
    chunks = (text[i : i + chunk_size] for i in range(0, len(text), chunk_size))
    return "".join(compact_stream(chunks, redact_secrets=False, aggressive=True))


def run_benchmarks(*, deep: bool = False) -> list[BenchmarkResult]:
    sizes = [1_000_000, 5_000_000, 10_000_000] if deep else [100_000]
    results: list[BenchmarkResult] = []

    for size in sizes:
        prose = ("The same project context appears here repeatedly.\n" * ((size // 50) + 1))[:size]
        results.append(_measure(f"large-context-{size // 1_000_000 or 0}mb", prose, lambda value: compact_text_with_metrics(value, redact_secrets=False).compacted))

    stream_text = ("hello world\n" * (50_000 if deep else 5_000))
    for chunk_size in (1, 10, 127):
        start = time.perf_counter()
        output = _stream_compact(stream_text, chunk_size)
        elapsed = (time.perf_counter() - start) * 1000.0
        results.append(BenchmarkResult(
            name=f"streaming-chunk-{chunk_size}",
            elapsed_ms=elapsed,
            input_chars=len(stream_text),
            output_chars=len(output),
            input_tokens=compact_text_with_metrics(stream_text, redact_secrets=False).in_tokens,
            output_tokens=compact_text_with_metrics(output, redact_secrets=False).out_tokens,
            reduction_percent=(1.0 - len(output) / max(1, len(stream_text))) * 100.0,
            passed=output == "hello world\n",
        ))

    code = "def build(value):\n    return value * 2\n\n" * 2
    code_result = compact_text_with_metrics(code, redact_secrets=False)
    results.append(BenchmarkResult(
        name="code-preservation",
        elapsed_ms=0.0,
        input_chars=len(code),
        output_chars=len(code_result.compacted),
        input_tokens=code_result.in_tokens,
        output_tokens=code_result.out_tokens,
        reduction_percent=code_result.token_change_percent,
        passed=code_result.compacted == code,
    ))

    secret_text = "api_key=fake-test-key-12345678901234567890\nBearer fakeBearerToken1234567890\nAIza123456789012345678901234"
    strict = compact_text_with_metrics(secret_text, redaction_mode="strict")
    results.append(BenchmarkResult(
        name="secret-redaction",
        elapsed_ms=0.0,
        input_chars=len(secret_text),
        output_chars=len(strict.compacted),
        input_tokens=strict.in_tokens,
        output_tokens=strict.out_tokens,
        reduction_percent=strict.token_change_percent,
        passed="fake-test-key" not in strict.compacted and "fakeBearerToken" not in strict.compacted and "AIza123" not in strict.compacted,
    ))

    tokenizer = lambda value: len(value.split())
    measured = compact_text_with_metrics("one two two two three", tokenizer=tokenizer, redact_secrets=False)
    results.append(BenchmarkResult(
        name="token-accuracy-with-supplied-counter",
        elapsed_ms=0.0,
        input_chars=len(measured.original),
        output_chars=len(measured.compacted),
        input_tokens=measured.in_tokens,
        output_tokens=measured.out_tokens,
        reduction_percent=measured.token_change_percent,
        passed=measured.token_count_is_exact and measured.token_count_source == "supplied-tokenizer",
    ))

    current = Memory(project="AI Token Saver", state=["streaming works", "streaming works"], history=["old state"])
    incoming = Memory(state=["streaming works", "deep benchmarks added"], next_steps=["run CI"])
    merged = merge_memory(current, incoming)
    results.append(BenchmarkResult(
        name="memory-fact-consolidation",
        elapsed_ms=0.0,
        input_chars=4,
        output_chars=len(str(merged.__dict__)),
        input_tokens=0,
        output_tokens=0,
        reduction_percent=0.0,
        passed=merged.state == ["streaming works", "deep benchmarks added"] and merged.history == ["old state"],
    ))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Token Saver deep benchmarks.")
    parser.add_argument("--deep", action="store_true", help="Run the 1 MB, 5 MB, and 10 MB context benchmarks.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON results.")
    args = parser.parse_args()

    results = run_benchmarks(deep=args.deep)
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(f"{status:4} {result.name:38} {result.elapsed_ms:9.2f} ms  {result.reduction_percent:7.2f}%")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
