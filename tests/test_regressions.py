"""Permanent regression guards for behavior that must never regress."""

from ai_token_saver import RealtimeCompactor, compact_text


CODE_SAMPLE = '''def hello():
    print("hello")
    print("hello")
'''


def test_regression_code_duplicates_are_never_removed():
    """Repeated lines inside code must survive normal compaction."""
    assert compact_text(CODE_SAMPLE, redact_secrets=False) == CODE_SAMPLE


def test_regression_aggressive_mode_never_deduplicates_code():
    """Aggressive prose compaction must not alter detected technical content."""
    assert compact_text(CODE_SAMPLE, redact_secrets=False, aggressive=True) == CODE_SAMPLE


def test_regression_realtime_code_duplicates_are_never_removed():
    """Streaming compaction must preserve repeated code lines too."""
    compactor = RealtimeCompactor(redact_secrets=False, aggressive=True)
    output = compactor.feed(CODE_SAMPLE) + compactor.finish()
    assert output == CODE_SAMPLE


def test_regression_code_guard_is_stable_across_repeated_compaction():
    """Running compaction again must not progressively destroy code."""
    once = compact_text(CODE_SAMPLE, redact_secrets=False, aggressive=True)
    twice = compact_text(once, redact_secrets=False, aggressive=True)
    assert once == CODE_SAMPLE
    assert twice == CODE_SAMPLE
