"""Round 4: identity by default, exact ``runs`` round trips, credentials untouched, validation, streaming, memory."""
from __future__ import annotations

import itertools
import random
import tracemalloc

import pytest

from ai_token_saver import (
    DEDUPE_MODES, RealtimeCompactor, compact_stream, compact_text, compact_text_with_metrics, expand_runs,
)
from realtime_usage_saver import RealtimeUsageSaver, state_fingerprint


def stream(text, sizes=(1,), **kwargs):
    chunks, pos, cycle = [], 0, itertools.cycle(sizes)
    while pos < len(text):
        step = next(cycle)
        chunks.append(text[pos:pos + step])
        pos += step
    return "".join(compact_stream(chunks, **kwargs))


MARKER = "[previous line repeated 5 more times]"
SAMPLES = {
    "yaml block scalar": "key: |\n  line one\n\n  line one\n  line one\n\nnext: >-\n  folded  text  \n",
    "csv quoted": 'id,note\n1,"multi\nline  ,  field"\n1,"multi\nline  ,  field"\n',
    "markdown": "# T\n\n\n\n    code\n\n- a\n- a\n\n| a | b |\n|---|---|\nParagraph.  \nParagraph.  \n",
    "json": '{\n  "a":   [1,\n\n 1],\n  "s": "x  y"\n}\n',
    "python": "def f():\n    x = 1\n\n\n    return x\n\n\n\nprint('a')\nprint('a')\n",
    "javascript": "function f() {\n\n  return `a\n\n  b`;\n}\n\n\nf();\nf();\n",
    "ini/toml": "[core]\nname =   x \n\n\n[more]\nname =   x \n",
    "crlf and cr": "a\r\na\r\na\rb\n\r\n\r\nz",
    "unicode": "café 中文 \U0001F600\nx y\n\x0c\n",
    "empty-ish": "\n",
}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_default_compaction_is_the_identity(name):
    text = SAMPLES[name]
    assert compact_text(text) == text
    assert stream(text, (3,)) == text
    result = compact_text_with_metrics(text)
    assert result.compacted == text and not result.output_grew


@pytest.mark.parametrize("name", sorted(SAMPLES))
@pytest.mark.parametrize("mode", ["runs"])
def test_runs_round_trips_every_sample_exactly(name, mode):
    text = SAMPLES[name]
    assert expand_runs(compact_text(text, dedupe=mode)) == text


# ------------------------------------------------------------------ reversible runs
LOOKALIKES = [
    MARKER, "\\" + MARKER, "\\\\" + MARKER, MARKER + " ", " " + MARKER, "[previous line repeated 0 more times]",
    "[previous line repeated many more times]", "[previous line repeated 5 more times]x",
]


@pytest.mark.parametrize("lookalike", LOOKALIKES)
def test_text_resembling_the_marker_cannot_confuse_the_decoder(lookalike):
    for text in (f"{lookalike}\n", f"hello world\nhello world\n{lookalike}\n", f"{lookalike}\n" * 4,
                 f"same line here\n" * 9 + f"{lookalike}\nsame line here\n" * 3, f"{lookalike}", f"a\n{lookalike}\n{lookalike}\nb"):
        packed = compact_text(text, dedupe="runs")
        assert expand_runs(packed) == text, (text, packed)
        assert stream(text, (2,), dedupe="runs") == packed


def test_a_real_run_is_collapsed_and_a_lookalike_next_to_it_survives():
    text = "Deploy failed\n" * 30 + MARKER + "\n"
    packed = compact_text(text, dedupe="runs")
    assert packed == "Deploy failed\n[previous line repeated 29 more times]\n\\" + MARKER + "\n"
    assert expand_runs(packed) == text


def test_runs_keep_each_lines_own_ending():
    text = "retrying now\r\n" * 20 + "retrying now\n" * 20 + "retrying now\r" * 20 + "retrying now"
    packed = compact_text(text, dedupe="runs")
    assert len(packed) < len(text) and expand_runs(packed) == text


def test_runs_do_not_merge_lines_that_differ_in_trailing_space():
    text = "waiting for it \n" * 10 + "waiting for it\n" * 10
    assert expand_runs(compact_text(text, dedupe="runs")) == text


def test_expand_runs_is_bounded_when_asked():
    with pytest.raises(ValueError):
        expand_runs("x\n[previous line repeated 99999999999 more times]\n", max_chars=1000)
    assert expand_runs("x\n[previous line repeated 3 more times]\n", max_chars=8) == "x\nx\nx\nx\n"
    with pytest.raises(TypeError):
        expand_runs(b"x")  # type: ignore[arg-type]


ALPHABET = ["same line here", "same line here", "other words", "", " ", "x = 1", "- item", "[", "\\",
            MARKER, "\\" + MARKER, "[previous line repeated 2 more times]", "a,b", "tab\there", "ERROR boom"]
ENDINGS = ["\n", "\n", "\r\n", "\r", ""]


@pytest.mark.parametrize("seed", range(400))
def test_random_round_trip_and_chunking_invariance(seed):
    rng = random.Random(seed)
    parts = []
    for _ in range(rng.randint(0, 60)):
        line = rng.choice(ALPHABET)
        parts.extend([line + rng.choice(ENDINGS)] * rng.choice([1, 1, 2, 5, 40]))
    text = "".join(parts)
    packed = compact_text(text, dedupe="runs")
    assert expand_runs(packed) == text
    assert stream(text, [rng.randint(1, 13) for _ in range(rng.randint(1, 3))], dedupe="runs") == packed
    assert stream(text, (1,), dedupe="runs") == packed


@pytest.mark.parametrize("seed", range(150))
def test_arbitrary_characters_round_trip(seed):
    rng = random.Random(seed)
    alphabet = "ab \t\r\n[]\\prevousliner0123456789 \u0085\x00\ud800"
    text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 300)))
    assert expand_runs(compact_text(text, dedupe="runs")) == text


# ------------------------------------------------------------------ credentials are data, not secrets
CREDENTIALS = (
    "api_key=sk-abcdefghijklmnopqrstuvwxyz0123\npassword=hunter2\nBearer abcdefghijklmnop\nAIzaSyA-1234567890123456789012345678901\n"
    '{"secret": "s3cr3t", "token": ["a", "b"]}\nDB_PASSWORD: "p w"\npostgres://user:pw@host/db\n'
    "-----BEGIN PRIVATE KEY-----\nQUJD\nQUJD\n-----END PRIVATE KEY-----\n"
)


@pytest.mark.parametrize("mode", ["off", "runs", "adjacent", "global"])
def test_credentials_and_configuration_values_pass_through_verbatim(mode):
    out = compact_text(CREDENTIALS, dedupe=mode)
    assert out == CREDENTIALS and "[REDACTED]" not in out
    assert stream(CREDENTIALS, (5,), dedupe=mode) == CREDENTIALS


def test_legacy_redaction_arguments_are_accepted_and_ignored():
    for kwargs in ({"redact_secrets": True}, {"redact_secrets": False}, {"redaction_mode": "strict"},
                   {"redaction_mode": "anything"}):
        assert compact_text(CREDENTIALS, **kwargs) == CREDENTIALS
        assert "".join(compact_stream([CREDENTIALS], **kwargs)) == CREDENTIALS
        compactor = RealtimeCompactor(**kwargs)
        assert compactor.feed(CREDENTIALS) + compactor.finish() == CREDENTIALS


def test_the_redaction_module_is_gone():
    import importlib
    with pytest.raises(ImportError):
        importlib.import_module("redaction")


def test_savers_keep_values_as_given(tmp_path):
    from context_saver import ContextSaver
    from usage_saver import ServiceState, UsageCheckpoint
    checkpoint = UsageCheckpoint(project="demo", services=[ServiceState("Gmail", {"api_key": "abc-123", "token": "t0k"})],
                                 next_steps=["use password=hunter2"])
    text = str(checkpoint.normalized())
    assert "abc-123" in text and "t0k" in text and "hunter2" in text and "REDACTED" not in text
    state = {"project": "p", "current_task": "t", "commands": ["api_key=SECRET", "Bearer abcdefghijklmnop"]}
    snapshot = ContextSaver().save(state).snapshot
    assert "api_key=SECRET" in snapshot.commands and "Bearer abcdefghijklmnop" in snapshot.commands


def test_credential_changes_change_the_fingerprint():
    assert state_fingerprint("api_key=one") != state_fingerprint("api_key=two")
    saver = RealtimeUsageSaver()
    saver.start(); saver.feed("api_key=one\n"); saver.finish()
    assert saver.is_same_input("api_key=one\n") and not saver.is_same_input("api_key=two\n")


# ------------------------------------------------------------------ option validation
BAD_OPTIONS = [{"dedupe": "bogus"}, {"dedupe": 3}, {"dedupe": ["off"]}, {"tokenizer": 5}]


@pytest.mark.parametrize("options", BAD_OPTIONS)
def test_bad_options_fail_the_same_way_with_empty_and_real_input(options):
    errors = (ValueError, TypeError)
    for text in ("", "a\n", "x\ny\n"):
        if "tokenizer" not in options:
            with pytest.raises(errors):
                compact_text(text, **options)
        with pytest.raises(errors):
            compact_text_with_metrics(text, **options)
    with pytest.raises(errors):
        compact_stream([], **options)  # eagerly, before the first next()
    with pytest.raises(errors):
        compact_stream(["a\n"], **options)
    with pytest.raises(errors):
        RealtimeCompactor(**options)


def test_every_dedupe_mode_accepts_empty_input_and_nothing_else_changes():
    for mode in DEDUPE_MODES:
        assert compact_text("", dedupe=mode) == "" and list(compact_stream([], dedupe=mode)) == []
        assert list(compact_stream(["", ""], dedupe=mode)) == []
        assert compact_text_with_metrics("", dedupe=mode).compacted == ""


# ------------------------------------------------------------------ streaming consistency
STREAM_TEXTS = [t for t in SAMPLES.values()] + ["same line here\r\nsame line here\r\nsame line here\r\nend\r", "a\r", "\r\n", "x" * 50]


@pytest.mark.parametrize("mode", DEDUPE_MODES)
@pytest.mark.parametrize("text", STREAM_TEXTS)
def test_every_two_way_and_three_way_split_matches_batch(text, mode):
    batch = compact_text(text, dedupe=mode)
    n = len(text)
    cuts = [[i] for i in range(n + 1)]
    if n <= 40:
        cuts += [[i, j] for i in range(n + 1) for j in range(i, n + 1)]
    for cut in cuts:
        points = [0, *cut, n]
        chunks = [text[a:b] for a, b in zip(points, points[1:])]
        assert "".join(compact_stream(chunks, dedupe=mode)) == batch, (mode, cut)


def test_compactor_streams_incrementally_not_only_at_the_end():
    compactor = RealtimeCompactor(dedupe="adjacent")
    assert compactor.feed("first line here\nsecond ") == "first line here\n"
    assert compactor.feed("line here\n") == "second line here\n"
    assert compactor.finish() == ""


# ------------------------------------------------------------------ memory
def test_retain_false_keeps_nothing_and_says_so():
    compactor = RealtimeCompactor(dedupe="runs", retain=False)
    compactor.feed("hello world\n")
    compactor.finish()
    for attribute in ("original", "compacted"):
        with pytest.raises(RuntimeError):
            getattr(compactor, attribute)
    with pytest.raises(RuntimeError):
        compactor.result()


@pytest.mark.parametrize("mode", DEDUPE_MODES)
def test_large_stream_uses_bounded_memory(mode):
    line = "this line is repeated again and again\n"

    def chunks():
        for i in range(2000):
            yield (line * 500) + f"unique tail {i} {'z' * 100}\n"

    tracemalloc.start()
    emitted = 0
    for piece in compact_stream(chunks(), dedupe=mode):
        emitted += len(piece)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 8_000_000, f"{mode}: peak {peak / 1e6:.1f} MB for a ~40 MB stream"
    assert emitted > 0


def test_incremental_fingerprint_equals_the_whole_text_fingerprint():
    text = "alpha\r\nbeta \u4e2d\ud800\n" * 7 + "tail"
    for retain in (True, False):
        for mode in DEDUPE_MODES:
            saver = RealtimeUsageSaver(dedupe=mode, retain=retain)
            saver.start()
            for i in range(0, len(text), 5):
                saver.feed(text[i:i + 5])
            _, result = saver.finish()
            assert result.fingerprint == state_fingerprint(text, dedupe=mode)
            assert (result.result is None) == (not retain)


def test_usage_saver_with_retain_false_holds_no_copy_of_the_stream():
    saver = RealtimeUsageSaver(dedupe="runs", retain=False)
    saver.start()
    tracemalloc.start()
    for i in range(1000):
        saver.feed(("context line number %d\n" % i) * 400)
    saver.finish()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 6_000_000, f"peak {peak / 1e6:.1f} MB"


def test_nan_lock_timeout_and_unbounded_hold_combination_are_rejected():
    for bad in (float("nan"), 0, -1):
        with pytest.raises(ValueError):
            RealtimeUsageSaver(lock_timeout=bad)
    with pytest.raises(ValueError):
        RealtimeUsageSaver(retain=False, suppress_unchanged=True)
