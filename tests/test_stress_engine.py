import time

from ai_token_saver import RealtimeCompactor, compact_stream


def test_realtime_compactor_handles_character_stream_without_quadratic_buffer_scan():
    # A streaming client may deliver one character at a time. This must not
    # repeatedly rescan an ever-growing unterminated line.
    text = "x" * 12000
    start = time.perf_counter()
    compactor = RealtimeCompactor(dedupe="runs")  # the line-based path; "off" is a plain pass-through
    out = []
    for char in text:
        out.append(compactor.feed(char))
    out.append(compactor.finish())
    assert "".join(out) == text
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"character-by-character streaming took {elapsed:.3f}s"


def test_compact_stream_handles_many_small_chunks():
    chunks = ("hello world\n" for _ in range(5000))
    result = "".join(compact_stream(chunks, redact_secrets=False, aggressive=True))
    assert result == "hello world\n"


def test_realtime_compactor_handles_empty_and_mixed_newline_chunks():
    compactor = RealtimeCompactor(dedupe="runs")
    output = []
    for chunk in ("", "a\r", "\nb\n", "c\r", "\nd"):
        output.append(compactor.feed(chunk))
    output.append(compactor.finish())
    assert "".join(output) == "a\r\nb\nc\r\nd"  # Round 4: every line ending is kept as it was
