from __future__ import annotations

import json
import subprocess
import sys

import pytest

from ai_token_saver import Memory, RealtimeCompactor, compact_stream, compact_text, compact_text_with_metrics, merge_memory
from benchmarks.benchmark_runner import run_benchmarks


def test_benchmark_runner_covers_all_required_categories():
    names = {result.name for result in run_benchmarks()}
    assert any(name.startswith("large-context-") for name in names)
    assert any(name.startswith("streaming-chunk-") for name in names)
    assert "code-preservation" in names
    assert "secret-redaction" in names
    assert "token-accuracy-with-supplied-counter" in names
    assert "memory-fact-consolidation" in names


def test_all_quick_benchmarks_pass():
    results = run_benchmarks()
    assert results
    assert all(result.passed for result in results), [result.name for result in results if not result.passed]


def test_compaction_is_idempotent_for_repeated_saver_invocations():
    source = "PROJECT: demo\n\nSTATE:\n- GitHub synced\n- Vercel deployed\n- GitHub synced\n"
    first = compact_text(source, redact_secrets=False)
    second = compact_text(first, redact_secrets=False)
    third = compact_text(second, redact_secrets=False)
    assert first == second == third


@pytest.mark.parametrize("repetitions", [10, 100, 1_000])
def test_large_context_compaction_preserves_a_canonical_line(repetitions: int):
    line = "The same project context appears here repeatedly.\n"
    text = line * repetitions
    result = compact_text_with_metrics(text, redact_secrets=False)
    assert result.compacted == line
    assert result.out_tokens <= result.in_tokens


@pytest.mark.parametrize("chunk_size", [1, 2, 10, 31, 127])
def test_streaming_is_chunk_boundary_independent(chunk_size: int):
    text = "alpha\nbeta\ngamma\n"
    chunks = (text[i : i + chunk_size] for i in range(0, len(text), chunk_size))
    assert "".join(compact_stream(chunks, redact_secrets=False)) == text


def test_streaming_many_tiny_chunks_does_not_lose_data():
    text = "x" * 5_000 + "\n"
    compactor = RealtimeCompactor(redact_secrets=False)
    emitted: list[str] = []
    for char in text:
        emitted.append(compactor.feed(char))
    emitted.append(compactor.finish())
    assert "".join(emitted) == text


@pytest.mark.parametrize(
    "source",
    [
        "def hello():\n    print('hello')\n",
        "const value = 42;\nconsole.log(value);\n",
        '{"name": "AI Token Saver", "enabled": true}\n',
        "SELECT id FROM users WHERE active = true;\n",
        "#!/bin/bash\necho hello\n",
    ],
)
def test_code_and_structured_content_is_not_globally_deduplicated(source: str):
    text = source + source
    result = compact_text_with_metrics(text, redact_secrets=False, aggressive=True)
    assert result.compacted == text


def test_secret_benchmark_uses_only_fake_values():
    text = "api_key=fake-test-key-12345678901234567890\nBearer fakeBearerToken1234567890\nAIza123456789012345678901234"
    result = compact_text_with_metrics(text, redaction_mode="strict")
    assert "fake-test-key" not in result.compacted
    assert "fakeBearerToken" not in result.compacted
    assert "AIza123" not in result.compacted


def test_common_redaction_keeps_google_style_key_visible_for_strict_mode_only():
    text = "AIza123456789012345678901234"
    common = compact_text_with_metrics(text, redaction_mode="common")
    strict = compact_text_with_metrics(text, redaction_mode="strict")
    assert "AIza123" in common.compacted
    assert "AIza123" not in strict.compacted


def test_supplied_token_counter_is_reported_as_supplied():
    counter = lambda value: len(value.split())
    result = compact_text_with_metrics("one two two", tokenizer=counter, redact_secrets=False)
    assert result.token_count_is_exact is True
    assert result.token_count_source == "supplied-tokenizer"
    assert result.in_tokens == 3


def test_memory_merge_deduplicates_facts_without_touching_history():
    current = Memory(state=["streaming works", "streaming works"], history=["old state"])
    incoming = Memory(state=["streaming works", "deep benchmarks added"], next_steps=["run CI"])
    merged = merge_memory(current, incoming)
    assert merged.state == ["streaming works", "deep benchmarks added"]
    assert merged.history == ["old state"]
    assert merged.next_steps == ["run CI"]


def test_benchmark_runner_json_output_is_machine_readable():
    completed = subprocess.run(
        [sys.executable, "-m", "benchmarks.benchmark_runner", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, list)
    assert all(item["passed"] is True for item in payload)


def test_benchmark_runner_cli_returns_success():
    completed = subprocess.run(
        [sys.executable, "-m", "benchmarks.benchmark_runner"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "PASS" in completed.stdout
