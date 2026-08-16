from ai_token_saver import (
    Memory,
    RealtimeCompactor,
    compact_stream,
    compact_text,
    compact_text_with_metrics,
    estimate_tokens,
    load_memory,
    memory_to_text,
    merge_memory,
    reduction,
    save_memory,
)


def test_compact_removes_duplicates_without_deleting_meaning():
    source = """Now, we need to save the project state.
We need to save the project state.
The current router is OpenSpark.
The current router is OpenSpark.
"""
    result = compact_text(source)
    assert result.count("OpenSpark") == 1
    assert "need to save the project state" in result
    assert estimate_tokens(result) < estimate_tokens(source)
    assert result.endswith("\n")


def test_compaction_preserves_code_indentation_and_final_newline():
    source = """def hello():
    print(\"hello\")
    print(\"hello\")
"""
    result = compact_text(source, redact_secrets=False)
    assert result == "def hello():\n    print(\"hello\")\n"
    assert result.startswith("def hello():\n    ")


def test_compaction_preserves_no_final_newline():
    source = "same\nsame"
    assert compact_text(source, redact_secrets=False) == "same"


def test_reduction_is_bounded():
    source = "same line\nsame line\n"
    result = compact_text(source)
    value = reduction(source, result)
    assert 0.0 <= value <= 1.0


def test_merge_memory_deduplicates():
    a = Memory(project="OpenSpark", state=["router works"])
    b = Memory(state=["router works", "provider system added"])
    merged = merge_memory(a, b)
    assert merged.project == "OpenSpark"
    assert merged.state == ["router works", "provider system added"]


def test_memory_render_is_compact_and_structured():
    memory = Memory(
        project="OpenSpark",
        goal="AI auto-router",
        state=["provider system added"],
        next_steps=["add tests"],
    )
    text = memory_to_text(memory)
    assert "PROJECT: OpenSpark" in text
    assert "STATE:" in text
    assert "NEXT:" in text


def test_memory_round_trip(tmp_path):
    path = tmp_path / "memory.json"
    original = Memory(project="OpenSpark", goal="AI router", state=["working"])
    save_memory(path, original)
    assert load_memory(path) == original


def test_malformed_memory_has_safe_defaults(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text('{"project": 123, "state": "not-a-list", "unknown": true}', encoding="utf-8")
    memory = load_memory(path)
    assert memory.project == ""
    assert memory.state == []


def test_secret_redaction():
    source = "api_key=SECRET123 password=hunter2 Bearer abc123 sk-abcdefghijklmnopqrstuvwxyz"
    result = compact_text(source)
    assert "SECRET123" not in result
    assert "hunter2" not in result
    assert "abc123" not in result
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in result
    assert "[REDACTED]" in result


def test_compact_text_with_metrics_returns_all_fields():
    source = "same line\nsame line\nunique line\n"
    result = compact_text_with_metrics(source)
    assert result.original == source
    assert "same line" in result.compacted
    assert "unique line" in result.compacted
    assert result.in_tokens > 0
    assert result.out_tokens > 0
    assert result.out_tokens <= result.in_tokens
    assert 0.0 <= result.reduction_percent <= 1.0
    assert result.token_count_is_exact is False


def test_compact_text_with_metrics_shows_real_savings():
    repetitive = "duplicate\n" * 100 + "unique\n"
    result = compact_text_with_metrics(repetitive)
    assert result.reduction_percent > 0.9
    assert result.in_tokens > result.out_tokens


def test_exact_token_counter_is_used_and_marked_exact():
    def counter(text: str) -> int:
        return len(text.split())

    result = compact_text_with_metrics(
        "one two\none two\nthree\n",
        tokenizer=counter,
    )
    # Five whitespace-delimited words become three after duplicate-line removal.
    assert result.in_tokens == 5
    assert result.out_tokens == 3
    assert result.token_count_is_exact is True
    assert result.reduction_percent == 0.4


def test_realtime_compactor_handles_split_chunks_and_deduplicates():
    compactor = RealtimeCompactor(redact_secrets=False)
    assert compactor.feed("hello\nhel") == "hello\n"
    assert compactor.feed("lo\nhello\nworld") == "world\n"
    assert compactor.finish() == ""
    assert compactor.compacted == "hello\nworld\n"
    assert compactor.original == "hello\nhello\nhello\nworld"


def test_realtime_compactor_preserves_code_indentation():
    compactor = RealtimeCompactor(redact_secrets=False)
    emitted = compactor.feed("def hello():\n    print(\"hello\")\n    print(\"hello\")")
    emitted += compactor.finish()
    assert emitted == "def hello():\n    print(\"hello\")"


def test_realtime_compactor_reports_metrics_after_finish():
    compactor = RealtimeCompactor(redact_secrets=False)
    compactor.feed("same\nsame\nunique")
    compactor.finish()
    result = compactor.result()
    assert result.original == "same\nsame\nunique"
    assert result.compacted == "same\nunique"
    assert result.in_tokens > result.out_tokens
    assert result.reduction_percent > 0


def test_compact_stream_is_incremental_and_matches_compaction():
    chunks = ["one\n", "two\n", "two\nthree", "\n"]
    output = "".join(compact_stream(chunks, redact_secrets=False))
    assert output == "one\ntwo\nthree\n"
    assert output == compact_text("one\ntwo\ntwo\nthree\n", redact_secrets=False)


def test_realtime_handles_split_crlf_without_extra_blank_output():
    output = "".join(compact_stream(["one\r", "\ntwo\r\n", "three"], redact_secrets=False))
    assert output == "one\ntwo\nthree"


def test_realtime_rejects_feed_after_finish():
    compactor = RealtimeCompactor(redact_secrets=False)
    compactor.feed("done")
    assert compactor.finish() == "done"
    assert compactor.finish() == ""
    try:
        compactor.feed("more")
    except RuntimeError as exc:
        assert "already been finished" in str(exc)
    else:
        raise AssertionError("feed() must reject chunks after finish()")


def test_realtime_result_requires_finish():
    compactor = RealtimeCompactor(redact_secrets=False)
    compactor.feed("hello\n")
    try:
        compactor.result()
    except RuntimeError as exc:
        assert "Call finish()" in str(exc)
    else:
        raise AssertionError("result() must require finish()")
    compactor.finish()
    assert compactor.result().compacted == "hello\n"


def test_realtime_secret_redaction_across_chunks():
    output = list(compact_stream(["api_key=SEC", "RET123\n", "Bearer ", "abc123\n"]))
    combined = "".join(output)
    assert "SECRET123" not in combined
    assert "abc123" not in combined
    assert "[REDACTED]" in combined


def test_invalid_stream_chunk_type_is_rejected():
    compactor = RealtimeCompactor(redact_secrets=False)
    try:
        compactor.feed(123)  # type: ignore[arg-type]
    except TypeError as exc:
        assert "chunk must be a string" in str(exc)
    else:
        raise AssertionError("non-string chunks must be rejected")


def test_invalid_text_type_is_rejected():
    try:
        compact_text(123)  # type: ignore[arg-type]
    except TypeError as exc:
        assert "text must be a string" in str(exc)
    else:
        raise AssertionError("non-string text must be rejected")
