"""Regression tests for bugs found during deep bug-hunter reviews."""

from ai_token_saver import RealtimeCompactor, compact_text, compact_text_with_metrics, deduplicate


def test_direct_deduplicate_protects_code_even_in_aggressive_mode():
    code = [
        "print('hello')",
        "print('hello')",
        "def hello():",
        "print('hello')",
    ]
    assert deduplicate(code, aggressive=True) == code


def test_realtime_does_not_drop_early_duplicate_before_later_code_marker():
    text = "print('hello')\nprint('hello')\ndef hello():\n    return 1\n"
    compactor = RealtimeCompactor(redact_secrets=False, aggressive=True)
    output = compactor.feed(text) + compactor.finish()
    assert output == text


def test_realtime_code_guard_works_when_code_marker_arrives_in_later_chunk():
    first = "print('hello')\nprint('hello')\n"
    second = "def hello():\n    return 1\n"
    compactor = RealtimeCompactor(redact_secrets=False, aggressive=True)
    output = compactor.feed(first) + compactor.feed(second) + compactor.finish()
    assert output == first + second


def test_metrics_report_output_growth_after_redaction():
    text = "secret=abc"
    result = compact_text_with_metrics(text, redact_secrets=True)
    assert result.output_grew
    assert result.token_change_percent <= 0


def test_metrics_report_real_savings_as_positive_change():
    text = "hello\nhello\nhello\n"
    result = compact_text_with_metrics(text, redact_secrets=False)
    assert not result.output_grew
    assert result.token_change_percent > 0
    assert result.reduction_percent > 0
