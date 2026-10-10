"""Round 2: regression, preservation, security, concurrency and randomized tests."""
from __future__ import annotations

import ast
import concurrent.futures
import itertools
import json
import os
import random

import pytest

from ai_token_saver import RealtimeCompactor, compact_stream, compact_text
from realtime_usage_saver import RealtimeUsageSaver


def stream(text, sizes=(1,), **kwargs):
    chunks, pos, cycle = [], 0, itertools.cycle(sizes)
    while pos < len(text):
        step = next(cycle)
        chunks.append(text[pos:pos + step])
        pos += step
    return "".join(compact_stream(chunks, **kwargs))


def keep(text, **kwargs):
    """compact_text: structured input must come back unchanged unless ``dedupe`` says otherwise."""
    return compact_text(text, **kwargs)


# ======================================================== late code detection
@pytest.mark.parametrize("code", [
    "function f() {\n  if (a) {\n    foo();\n    foo();\n  }\n  }\n}\n",
    "for i in x:\n    pass\n    pass\n    break\n    break\n",
    "set -e\necho one\necho one\nfi\nfi\n",
    "int main() {\n  x++;\n  x++;\n  return 0;\n}\n",
    "make test\nmake test\n",
    "cd build\ncd build\n",
    "done\ndone\n",
    "end\nend\n",
])
def test_code_like_repeats_survive_before_any_code_hint(code):
    assert keep(code) == code
    assert stream(code) == code
    assert keep(code, aggressive=True) == code


def test_repeated_prose_before_code_is_still_deduplicated_and_code_is_kept():
    text = "We looked at it.\nWe looked at it.\nfoo();\nfoo();\n"
    assert keep(text, dedupe="adjacent") == "We looked at it.\nfoo();\nfoo();\n"


# ======================================================== repeated events
@pytest.mark.parametrize("record", [
    "Oct 10 12:00:00 host sshd[1]: Failed password for root",
    "level=error msg=timeout svc=db",
    "1760000000 request failed",
    "E1010 12:00:00.123 main.go:5] boom",
    "2026/10/10 12:00:00 retry",
    'x - - [10/Oct/2026:12:00:00 +0000] "GET / HTTP/1.1" 500 12',
    "tests/a.py::test_x FAILED",
    "2026-10-10T12:00:00Z INFO started",
    "ERROR db timeout",
    "12:00:00 retrying",
])
def test_identical_event_records_are_never_dropped(record):
    text = f"{record}\n{record}\n{record}\n"
    for aggressive in (False, True):
        assert keep(text, aggressive=aggressive) == text
        assert stream(text, (3,), redact_secrets=False, aggressive=aggressive) == text


# ======================================================== markdown
def test_markdown_structure_is_preserved_exactly():
    md = (
        "# Title\n\nIntro paragraph is here.\n\n## Notes\n\n- one\n- one\n- two\n\n1. a\n1. a\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n| 1 | 2 |\n\n| c | d |\n|---|---|\n| 3 | 4 |\n\n"
        "> quote\n> quote\n\n---\n\n## Notes\n\nLast paragraph.\n\n    indented code\n    indented code\n"
    )
    for aggressive in (False, True):
        assert keep(md, aggressive=aggressive) == md
        assert stream(md, (5,), redact_secrets=False, aggressive=aggressive) == md


def test_fenced_code_blocks_keep_blank_lines_and_duplicates():
    md = "Before the fence.\n\n```python\nx = 1\nx = 1\n\n\ny = 2\n```\n\nAfter the fence.\n"
    assert keep(md) == md
    assert stream(md, (2,), redact_secrets=False) == md


def test_markdown_paragraph_boundary_is_one_blank_line():
    text = "Para one is here.\n\n\n\nPara two is here.\n"  # Round 4: blank lines are no longer collapsed
    assert keep(text) == text and keep(text, dedupe="runs") == text


# ======================================================== JSON / YAML preservation
JSON_DOCS = [
    "[\n  1,\n  1,\n  2\n]\n", '[\n  "a",\n  "a"\n]\n', "[\n  true,\n  true\n]\n",
    '{\n  "xs": [\n    {"v": 1},\n    {"v": 1}\n  ]\n}\n', '{\n  "a": 1,\n  "b": 1\n}\n',
    json.dumps({"rows": [[1, 1], [1, 1], [2, 2]], "name": "x y z"}, indent=2) + "\n",
    json.dumps({"s": "line one", "t": "line one"}, indent=4) + "\n",
]
YAML_DOCS = [
    "xs:\n  - a b\n  - a b\n", "t: |\n  hello world\n  hello world\n", "a: &x\n  k: v v\nb: *x\n",
    "items:\n  - name: x\n    tags: [a, a]\n  - name: x\n    tags: [a, a]\n", "text: >\n  folded text here\n  folded text here\n",
]


@pytest.mark.parametrize("doc", JSON_DOCS)
def test_json_documents_keep_their_meaning(doc):
    for aggressive in (False, True):
        out = keep(doc, aggressive=aggressive)
        assert json.loads(out) == json.loads(doc) and out == doc
        assert stream(doc, (1,), redact_secrets=False, aggressive=aggressive) == out


@pytest.mark.parametrize("doc", YAML_DOCS)
def test_yaml_documents_keep_their_meaning(doc):
    yaml = pytest.importorskip("yaml", reason="PyYAML is needed to compare YAML meaning (installed in CI)")
    for aggressive in (False, True):
        out = keep(doc, aggressive=aggressive)
        assert yaml.safe_load(out) == yaml.safe_load(doc) and out == doc


# ======================================================== redaction: syntax and coverage


def test_multiline_secret_block_does_not_swallow_following_content():
    doc = '{\n  "password": [\n    "a"\n  ],\n  "keep": "visible text",\n  "list": [1, 2]\n}'
    out = json.loads(compact_text(doc))
    assert out["keep"] == "visible text" and out["list"] == [1, 2]


def test_unclosed_private_key_stops_swallowing_after_a_cap():
    text = "-----BEGIN PRIVATE KEY-----\n" + "".join(f"line {i}\n" for i in range(800)) + "tail line here\n"
    assert "tail line here" in compact_text(text)


@pytest.mark.parametrize("line", [
    "apikey=keep-this", "mypassword=keep", "password = get_password()", "self.password = password",
    "token_count = 5", "secretary=Bob", "api_key_file = load()", "password = None", "max_tokens=100",
])
def test_non_secrets_are_not_touched(line):
    assert compact_text(line + "\n") == line + "\n"


# ======================================================== batch versus streaming
TRICKY = [
    "a\r\na\r\nb\r\n", "note\nnote\nimport os\n", "# T\r\n\r\nP is a paragraph\r\n", "```\nx\nx\n```\nafter\nafter\n",
    "-----BEGIN PRIVATE KEY-----\nAA\nBB\n-----END PRIVATE KEY-----\nz\n", '{"password": [\n"a"\n],\n"k": 1}\n',
    "| a |\n|---|\n| x |\n| x |\n", "ERROR x\nERROR x\n\n\nfoo();\nfoo();\n", "same line\nsame line\n\n\nsame line\n",
    "password=hunter2\r\nok\r\n", "x\u2028y\n\x0c\n",
]


def small_cut_sets(n):
    if n <= 12:
        for mask in range(1 << max(n - 1, 0)):
            yield [i + 1 for i in range(n - 1) if mask >> i & 1]
    else:
        for k in range(0, 3):
            yield from (list(c) for c in itertools.combinations(range(1, n), k))


@pytest.mark.parametrize("mode", ["off", "runs", "adjacent", "global"])
@pytest.mark.parametrize("text", TRICKY)
def test_every_split_matches_batch(text, mode):
    batch = compact_text(text, dedupe=mode)
    for cuts in small_cut_sets(len(text)):
        points = [0, *cuts, len(text)]
        chunks = [text[a:b] for a, b in zip(points, points[1:])]
        assert "".join(compact_stream(chunks, dedupe=mode)) == batch, (text, cuts)


FRAGMENTS = [
    "The project state is important.", "The project state is important.", "same line", "# Heading", "- item", "| a | b |",
    "import os", "def f(x):", "    return x + 1", "x = 1", "foo();", "}", "pass", "echo hi", "ERROR db timeout",
    '{"a": 1, "password": "p w"}', '"password": [', '  "z",', "  ]", "api_key=ABCDEF123456", "password = get_pw()",
    "-----BEGIN PRIVATE KEY-----", "MIIEvQIBADANBg", "-----END PRIVATE KEY-----", "```", "caf\u00e9 \u00fc\u00f1\u00ee",
    "\U0001F600 emoji", "key: value", "", "", "Bearer abcdefghijklmnop", "2026-10-10 12:00:00 INFO ok", "postgres://u:pw@h/d",
]


def random_text(rng):
    n = rng.randint(0, 16)
    text = "".join(rng.choice(FRAGMENTS) + rng.choice(["\n", "\n", "\r\n", "\r"]) for _ in range(n))
    return text[: rng.randint(0, len(text))] if text and rng.random() < 0.3 else text


@pytest.mark.parametrize("seed", range(400))
def test_random_streams_equal_batch(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    for mode in ("off", "runs", "adjacent", "global"):
        batch = compact_text(text, dedupe=mode)
        sizes = [rng.randint(1, 11) for _ in range(rng.randint(1, 4))]
        assert stream(text, sizes, dedupe=mode) == batch
        assert stream(text, (1,), dedupe=mode) == batch


PROTECTED = ("ERROR db timeout", "foo();", "}", "pass", "echo hi", "- item", "| a | b |", "    return x + 1", "```", "key: value",
             "2026-10-10 12:00:00 INFO ok", "x = 1", "import os", "def f(x):")


@pytest.mark.parametrize("seed", range(400, 700))
def test_random_properties_idempotent_protected_and_no_invention(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    norm_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for aggressive in (False, True):
        mode = "global" if aggressive else "adjacent"
        once = keep(text, dedupe=mode)
        out_lines = once.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        again = keep(once, dedupe=mode)
        if aggressive:  # decided over a 4-line lookahead window: a second pass may only remove more
            assert set(again.replace("\r\n", "\n").replace("\r", "\n").split("\n")) <= set(out_lines) and len(again) <= len(once)
        else:
            assert again == once  # conservative mode is idempotent
        assert all(line in set(norm_lines) for line in out_lines if line.strip())  # nothing is invented
        for marker in PROTECTED:  # lines that are never dropped keep their exact count
            assert out_lines.count(marker) == norm_lines.count(marker), (marker, aggressive)


@pytest.mark.parametrize("seed", range(800, 860))
def test_arbitrary_unicode_and_control_characters_never_crash(seed):
    rng = random.Random(seed)
    alphabet = "ab \t\r\n\u2028\u0085\u00e9\u4e2d\U0001F600\x00\x0b\x0c=:{}[]\"'\\-#|>`ud800"
    text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120))) + rng.choice(["", "\ud800", "\udfff"])
    assert stream(text, (rng.randint(1, 8),)) == compact_text(text)


# ======================================================== idempotency, concurrency, interruption
def _finish(path):
    saver = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    saver.feed("shared state\n")
    out, result = saver.finish()
    return result.changed, out


def test_suppress_unchanged_streams_normally_without_a_saved_fingerprint(tmp_path):
    saver = RealtimeUsageSaver(state_path=tmp_path / "s.json", suppress_unchanged=True)
    assert saver.feed("hello world\n") == "hello world\n"
    out, result = saver.finish()
    assert out == "" and result.changed


def test_suppress_unchanged_second_run_and_changed_run(tmp_path):
    path = tmp_path / "s.json"
    first = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    first.feed("hello world\n")
    first.finish()
    again = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    assert again.feed("hello world\n") == "" and again.finish() == ("", again.result)
    assert again.result.changed is False
    changed = RealtimeUsageSaver(state_path=path, suppress_unchanged=True)
    got = changed.feed("hello world\n") + changed.feed("more\n") + changed.finish()[0]
    assert got == "hello world\nmore\n" and changed.result.changed


def test_concurrent_processes_record_exactly_one_change(tmp_path):
    path = str(tmp_path / "s.json")
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_finish, [path] * 8))
    assert sum(1 for changed, _ in results if changed) == 1
    assert [out for changed, out in results if changed] == ["shared state\n"] or all(out == "" or out == "shared state\n" for _, out in results)


def test_concurrent_threads_record_exactly_one_change(tmp_path):
    path = str(tmp_path / "t.json")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_finish, [path] * 12))
    assert sum(1 for changed, _ in results if changed) == 1


def test_closing_a_stream_early_persists_nothing_and_leaves_no_lock(tmp_path):
    path = tmp_path / "s.json"
    generator = RealtimeUsageSaver(state_path=path).process(iter(["a\n", "b\n", "c\n"]))
    next(generator)
    generator.close()
    assert not path.exists() and not list(tmp_path.glob("*.lock"))


def test_error_in_the_chunk_source_persists_nothing(tmp_path):
    path = tmp_path / "s.json"

    def chunks():
        yield "a\n"
        raise ConnectionError("dropped")

    with pytest.raises(ConnectionError):
        list(RealtimeUsageSaver(state_path=path).process(chunks()))
    assert not path.exists() and not list(tmp_path.glob("*.lock"))


def test_failed_persist_releases_the_lock_and_next_run_still_counts_as_changed(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    saver = RealtimeUsageSaver(state_path=path)
    saver.feed("hello\n")
    monkeypatch.setattr(RealtimeUsageSaver, "_persist_fingerprint", lambda self, fp: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        saver.finish()
    assert not list(tmp_path.glob("*.lock")) and not path.exists()
    monkeypatch.undo()
    retry = RealtimeUsageSaver(state_path=path)
    retry.feed("hello\n")
    assert retry.finish()[1].changed is True


def test_lone_surrogates_do_not_break_fingerprinting_or_saving(tmp_path):
    from context_saver import ContextSaver
    saver = RealtimeUsageSaver(state_path=tmp_path / "s.json")
    saver.feed("bad \ud800 text\n")
    assert saver.finish()[1].changed
    assert ContextSaver(state_path=tmp_path / "c.json").save({"project": "p\ud800"}).changed


# ======================================================== predictable errors
def test_error_handling_is_predictable():
    for bad in (None, 123, b"bytes", ["a"]):
        with pytest.raises(TypeError):
            compact_text(bad)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            RealtimeCompactor().feed(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        compact_text("x", dedupe="bogus")
    assert compact_text("") == "" and compact_text("\n\n\n") == "\n\n\n"  # identity by default
    c = RealtimeCompactor()
    c.feed("a\n")
    assert c.finish() == "" and c.finish() == ""
    with pytest.raises(RuntimeError):
        c.feed("more")
    with pytest.raises(RuntimeError):
        RealtimeCompactor().result()


# ======================================================== adversarial input: no crash, no quadratic blow-up
ADVERSARIAL = {
    "dotted chain": ".".join("ab" for _ in range(30_000)) + ".secret = 1\n",
    "underscore chain": "_".join("ab" for _ in range(30_000)) + "_password=x\n",
    "annotation chain": "password: " + "A." * 30_000 + "x = 1\n",
    "unterminated quote": 'password="' + "a" * 300_000 + "\n",
    "spaces before =": "password" + " " * 300_000 + "=x\n",
    "open brackets after key": "password = " + "[" * 300_000 + "\n",
    "url scheme chain": "a." * 100_000 + "\n",
    "backslashes": 'password = "' + "\\" * 300_000 + '"\n',
    "unclosed private keys": "-----BEGIN PRIVATE KEY-----\n" * 20_000,
    "trigger words": "key " * 100_000 + "\n",
    "deep json": '{"password": ' + "[" * 50_000 + "]" * 50_000 + "}\n",
    "deep json value line": "[" * 5_000 + "]" * 5_000 + "\n",
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_adversarial_inputs_finish_quickly_without_crashing(name):
    import time
    text = ADVERSARIAL[name]
    start = time.perf_counter()
    out = compact_text(text)
    assert time.perf_counter() - start < 5.0, f"{name} took too long"
    assert isinstance(out, str)
    assert stream(text[:20_000], (7,)) == compact_text(text[:20_000])


def test_deeply_nested_json_line_does_not_raise_recursion_error():
    line = "[" * 100_000 + "]" * 100_000
    assert compact_text(line + "\n" + line + "\n") == line + "\n" + line + "\n"


# ======================================================== a line is dropped only when it repeats an earlier one
def _only_repeats_removed(text, aggressive):
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    source = [line for line in norm.split("\n") if line.strip()]
    kept = [line for line in keep(text, dedupe="global" if aggressive else "adjacent").replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    i = 0
    seen: set[str] = set()
    previous = None
    for line in source:
        if i < len(kept) and kept[i] == line:
            i += 1
        else:  # this input line was dropped: it must repeat a prior line, adjacent (conservative) or anywhere (aggressive)
            key = line.rstrip(" \t")
            earlier = key in seen if aggressive else key == previous
            assert earlier, f"dropped a line that is not a repeat: {line!r}"
        seen.add(line.rstrip(" \t"))
        previous = line.rstrip(" \t")
    assert i == len(kept), "output contains lines that are not in the input in order"


@pytest.mark.parametrize("seed", range(1000, 1300))
def test_only_repeated_lines_are_ever_dropped_and_order_is_kept(seed):
    text = random_text(random.Random(seed))
    for aggressive in (False, True):
        _only_repeats_removed(text, aggressive)


# ======================================================== findings from the independent review
def test_quoted_private_key_constants_in_source_do_not_swallow_code():
    src = 'H = "-----BEGIN PRIVATE KEY-----"\ndef f(): ...\nprint(2)\nF = "-----END PRIVATE KEY-----"\n'
    assert compact_text(src) == src


@pytest.mark.parametrize("text", ["src/a.py\nsrc/a.py\n", "README.md\nREADME.md\n", "foo.bar\nfoo.bar\n", "all:\nall:\n",
                                  "0 errors\n0 errors\n", "a\\b\na\\b\n", "build 42\nbuild 42\n"])
def test_paths_labels_and_counts_are_never_deduplicated(text):
    assert keep(text) == text and keep(text, aggressive=True) == text


def test_plain_text_without_a_timestamp_or_level_is_still_treated_as_prose():
    # Documented limit: "Connection refused" looks like a sentence, so adjacent repeats collapse.
    assert keep("Connection refused\nConnection refused\n", dedupe="adjacent") == "Connection refused\n"


def test_apostrophes_in_comments_do_not_leave_a_secret_block_open():
    doc = '{"password": [\n  "a" # don\'t\n],\n"keep": 1\n}\n'
    out = compact_text(doc)
    assert '"keep": 1' in out and "}" in out
