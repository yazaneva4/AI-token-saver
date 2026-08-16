from ai_token_saver import Memory, compact_text, estimate_tokens, memory_to_text, merge_memory, reduction


def test_compact_removes_duplicates_and_filler():
    source = """Now, we need to save the project state.
We need to save the project state.
The current router is OpenSpark.
The current router is OpenSpark.
"""
    result = compact_text(source)
    assert result.count("OpenSpark") == 1
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
