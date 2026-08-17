from ai_token_saver import Memory, compact_text, estimate_tokens, load_memory, memory_to_text, merge_memory, reduction, save_memory


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
    source = "api_key=SECRET123 password=hunter2 Bearer abcdefghijklmnop sk-abcdefghijklmnopqrstuvwxyz"
    result = compact_text(source)
    assert "SECRET123" not in result
    assert "hunter2" not in result
    assert "abcdefghijklmnop" not in result
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in result
    assert "[REDACTED]" in result
