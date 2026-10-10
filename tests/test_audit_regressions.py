"""Regression, equivalence and randomized tests for the independent audit findings."""
from __future__ import annotations

import ast
import itertools
import json
import random

import pytest

from ai_token_saver import RealtimeCompactor, compact_stream, compact_text
from realtime_usage_saver import RealtimeUsageSaver


def stream(text: str, sizes=(1,), **kwargs) -> str:
    """Stream ``text`` using repeating chunk sizes."""
    chunks, position, cycle = [], 0, itertools.cycle(sizes)
    while position < len(text):
        step = next(cycle)
        chunks.append(text[position:position + step])
        position += step
    return "".join(compact_stream(chunks, **kwargs))


def split_at(text: str, cuts) -> list[str]:
    points = [0, *sorted(cuts), len(text)]
    return [text[a:b] for a, b in zip(points, points[1:])]


# ---------------------------------------------------------------- 1. batch == stream
def test_technical_line_after_repeated_prose_is_identical_in_batch_and_stream():
    text = "note\nnote\nimport os\n"
    assert compact_text(text, dedupe="adjacent") == "note\nimport os\n"
    assert stream(text, dedupe="adjacent") == compact_text(text, dedupe="adjacent")


def test_code_after_prose_is_never_deduplicated():
    text = "intro\nintro\ndef f():\n    x = 1\n    x = 1\n"
    out = compact_text(text, redact_secrets=False)
    assert out.endswith("    x = 1\n    x = 1\n")


# ---------------------------------------------------------------- 2. markdown
def test_markdown_paragraph_boundaries_are_kept():
    text = "# Title\n\nPara one.\n\nPara two.\n"
    assert compact_text(text) == text
    assert stream(text) == text


def test_blank_line_runs_are_kept_in_prose():
    # Round 4: blank lines are content (Markdown, poems, YAML block scalars); nothing collapses them any more.
    for mode in ("off", "runs", "adjacent", "global"):
        assert compact_text("a\n\n\n\nb\n", dedupe=mode) == "a\n\n\n\nb\n"


def test_code_keeps_blank_lines_exactly():
    code = "def a():\n    pass\n\n\ndef b():\n    pass\n"
    assert compact_text(code, redact_secrets=False) == code
    assert stream(code, redact_secrets=False) == code


def test_leading_and_trailing_blank_lines_are_kept_in_prose():
    for mode in ("off", "runs", "adjacent", "global"):
        assert compact_text("\n\nhello\n\n\n", dedupe=mode) == "\n\nhello\n\n\n"


# ---------------------------------------------------------------- 3. JSON secrets


# ---------------------------------------------------------------- 4. python semantics


# ---------------------------------------------------------------- 5. event records
def test_adjacent_identical_log_events_are_kept():
    text = "2024-01-01 12:00:00 ERROR db timeout\n2024-01-01 12:00:00 ERROR db timeout\nERROR retry\nERROR retry\n"
    assert compact_text(text) == text
    assert stream(text) == text
    assert compact_text(text, aggressive=True) == text


def test_prose_duplicates_are_still_removed():
    assert compact_text("The state is important.\nThe state is important.\n", dedupe="adjacent") == "The state is important.\n"


def test_yaml_sequence_entries_and_list_items_are_kept():
    yaml = "items:\n  - 1\n  - 1\n"
    assert compact_text(yaml) == yaml
    assert compact_text("- a\n- a\n1. b\n1. b\n") == "- a\n- a\n1. b\n1. b\n"


def test_lowercase_error_prose_is_not_treated_as_an_event():
    assert compact_text("an error occurred\nan error occurred\n", dedupe="adjacent") == "an error occurred\n"


# ---------------------------------------------------------------- 6. realtime saver
def test_suppress_unchanged_emits_nothing_for_repeated_input(tmp_path):
    path = tmp_path / "s.json"
    first = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    assert "".join(first.process(["hello\n", "world\n"])) == "hello\nworld\n"
    second = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    emitted = [second.feed("hello\n"), second.feed("world\n")]
    final, result = second.finish()
    assert emitted == ["", ""] and final == "" and result.changed is False


def test_suppress_unchanged_still_emits_changed_input(tmp_path):
    path = tmp_path / "s.json"
    list(RealtimeUsageSaver(state_path=path, suppress_unchanged=True).process(["one\n"]))
    saver = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    assert "".join(saver.process(["two\n"])) == "two\n" and saver.result.changed is True


def test_default_realtime_saver_keeps_existing_behaviour(tmp_path):
    path = tmp_path / "s.json"
    list(RealtimeUsageSaver(state_path=path).process(["same\n"]))
    again = RealtimeUsageSaver(state_path=path)
    assert "".join(again.process(["same\n"])) == "same\n" and again.result.changed is False


# ---------------------------------------------------------------- 7. CRLF / chunk boundaries
TRICKY = [
    "a\r\na\r\nb\r\n", "a\ra\rb", "a\r\n\r\nb", "x y\n", "p\x0cq\n", "\r\n\r\n", "\r", "\n\r", "a\r\r\nb",
    "café\r\ncafé\r\n", "\U0001F600\n\U0001F600\n", "note\nnote\nimport os\n", "# T\r\n\r\nP\r\n",
    "ERROR x\nERROR x\n", "password=hunter2\r\nok\r\n", "a\n\n\nb", "def f():\n\n    return 1\n\n",
]


def all_cut_sets(n: int):
    """Every way to cut a length-n text into chunks when n is small (2**(n-1) of them),
    otherwise every set of up to three cut points (all single, double and triple splits)."""
    if n <= 12:
        for mask in range(1 << max(n - 1, 0)):
            yield [i + 1 for i in range(n - 1) if mask >> i & 1]
    else:
        for k in range(0, 4):
            yield from (list(c) for c in itertools.combinations(range(1, n), k))


@pytest.mark.parametrize("aggressive", [False, True])
@pytest.mark.parametrize("text", TRICKY)
def test_every_possible_split_matches_batch(text, aggressive):
    batch = compact_text(text, aggressive=aggressive)
    for cuts in all_cut_sets(len(text)):
        assert "".join(compact_stream(split_at(text, cuts), aggressive=aggressive)) == batch, (text, cuts)


def test_unicode_separators_are_not_line_breaks():
    for text in ("x y\n", "p\x0cq\n", "a\x85b\n", "a b\n"):
        assert compact_text(text, redact_secrets=False) == text


def test_crlf_and_cr_are_preserved_not_normalised():
    # Round 4: the engine no longer rewrites line endings in any mode.
    for mode in ("off", "runs", "adjacent", "global"):
        assert compact_text("a\r\nb\rc\n", dedupe=mode) == "a\r\nb\rc\n"


def test_empty_chunks_and_lone_cr_chunks():
    c = RealtimeCompactor()
    out = c.feed("a") + c.feed("") + c.feed("\r") + c.feed("") + c.feed("\n") + c.feed("b") + c.finish()
    assert out == compact_text("a\r\nb")


# ---------------------------------------------------------------- randomized properties
FRAGMENTS = [
    "The project state is important.", "The project state is important.", "same line", "# Heading", "- item",
    "import os", "def f(x):", "    return x + 1", "x = 1", '{"a": 1, "password": "p w"}', "api_key=ABCDEF123456",
    "password = get_pw()", "ERROR db timeout", "2024-05-01 10:00:00 INFO ok", "café üñî",
    "\U0001F600 emoji", "key: value", "  indented: yaml", "", "", "Bearer abcdefghijklmnop", "if password == 'x':",
]
SEPARATORS = ["\n", "\n", "\r\n", "\r"]


def random_text(rng: random.Random) -> str:
    n = rng.randint(0, 14)
    parts = [rng.choice(FRAGMENTS) + rng.choice(SEPARATORS) for _ in range(n)]
    text = "".join(parts)
    return text[: rng.randint(0, len(text))] if text and rng.random() < 0.3 else text


@pytest.mark.parametrize("seed", range(300))
def test_random_streams_equal_batch_for_random_chunking(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    for mode in ("off", "runs", "adjacent", "global"):
        batch = compact_text(text, dedupe=mode)
        sizes = [rng.randint(1, 9) for _ in range(rng.randint(1, 5))]
        assert stream(text, sizes, dedupe=mode) == batch
        assert stream(text, (1,), dedupe=mode) == batch


@pytest.mark.parametrize("seed", range(300, 450))
def test_random_output_is_idempotent_and_never_invents_lines(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    assert compact_text(text) == text  # the default is the identity
    once = compact_text(text, dedupe="adjacent")
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    source_lines = set(normalised.split("\n"))
    assert all(line in source_lines for line in once.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    assert compact_text(once, dedupe="adjacent") == once


@pytest.mark.parametrize("seed", range(450, 600))
def test_random_event_and_code_lines_are_preserved(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    out = compact_text(text, dedupe="global" if seed % 2 else "adjacent").replace("\r\n", "\n").replace("\r", "\n")
    for marker in ("ERROR db timeout", "2024-05-01 10:00:00 INFO ok", "    return x + 1", "x = 1"):
        assert out.count(marker) == normalised.count(marker), marker


@pytest.mark.parametrize("seed", range(700, 760))
def test_arbitrary_unicode_never_crashes_and_streams_equal_batch(seed):
    rng = random.Random(seed)
    alphabet = "ab \t\r\n \u0085é中\U0001F600\x00\x0b\x0c=:{}\"'"
    text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
    assert stream(text, (rng.randint(1, 7),)) == compact_text(text)


# ---------------------------------------------------------------- formats and size
def test_json_yaml_python_markdown_logs_survive_unchanged_without_secrets():
    docs = {
        "json": '{\n  "name": "x",\n  "items": [1, 2, 2]\n}\n',
        "yaml": "name: x\nitems:\n  - 1\n  - 1\n",
        "python": "import os\n\n\ndef f():\n    return os.name\n\n\nprint(f())\n",
        "markdown": "# T\n\n- a\n- a\n\n```py\nx = 1\n```\n",
        "logs": "2024-01-01 INFO start\n2024-01-01 INFO start\n2024-01-01 WARN slow\n",
    }
    for name, text in docs.items():
        assert compact_text(text, redact_secrets=False) == text, name
        assert stream(text, (3,), redact_secrets=False) == text, name


def test_large_input_streams_equal_batch_and_unbroken_line_is_linear():
    text = ("Paragraph about the project state.\n" * 3 + "\n") * 2000
    assert stream(text, (4096,)) == compact_text(text)
    long_line = "x" * 300_000
    assert stream(long_line, (1,)) == long_line  # 1-character chunks, one unterminated line


# ---------------------------------------------------------------- shared redaction in the savers

