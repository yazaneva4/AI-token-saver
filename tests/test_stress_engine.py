import time

from ai_token_saver import RealtimeCompactor, compact_stream


def test_realtime_compactor_handles_character_stream_without_quadratic_buffer_scan():
    # A streaming client may deliver one character at a time. This must not
    # repeatedly rescan an ever-growing unterminated line.
    text = "x" * 12000
    start = time.perf_counter()
    compactor = RealtimeCompactor(redact_secrets=False)
    for char in text:
        compactor.feed(char)
    assert compactor.finish() == text
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"character-by-character streaming took {elapsed:.3f}s"


def test_compact_stream_handles_many_small_chunks():
    chunks = ("hello world\n" for _ in range(5000))
    result = "".join(compact_stream(chunks, redact_secrets=False, aggressive=True))
    assert result == "hello world\n"


def test_realtime_compactor_handles_empty_and_mixed_newline_chunks():
    compactor = RealtimeCompactor(redact_secrets=False)
    output = []
    for chunk in ("", "a\r", "\nb\n", "c\r", "\nd"):
        output.append(compactor.feed(chunk))
    output.append(compactor.finish())
    assert "".join(output) == "a\nb\nc\nd"
