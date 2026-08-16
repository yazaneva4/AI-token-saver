from ai_token_saver import Memory, compact_text, compact_text_with_metrics, estimate_tokens, load_memory, memory_to_text, merge_memory, reduction, save_memory


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


def test_compaction_preserves_code_indentation():
    source = """def hello():
    print(\"hello\")
    print(\"hello\")
"""
    result = compact_text(source, redact_secrets=False)
    assert result == "def hello():\n    print(\"hello\")"
    assert result.startswith("def hello():\n    ")


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


def test_compact_text_with_metrics_shows_real_savings():
    repetitive = "duplicate\n" * 100 + "unique\n"
    result = compact_text_with_metrics(repetitive)
    assert result.reduction_percent > 0.9
    assert result.in_tokens > result.out_tokens
