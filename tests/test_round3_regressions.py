"""Round 3: meaningful repetitions are preserved by default; structured redaction keeps JSON semantics."""
from __future__ import annotations

import ast
import itertools
import json
import random
import re

import pytest

from ai_token_saver import RealtimeCompactor, compact_stream, compact_text, compact_text_with_metrics
from redaction import redact_secrets


def stream(text, sizes=(1,), **kwargs):
    chunks, pos, cycle = [], 0, itertools.cycle(sizes)
    while pos < len(text):
        step = next(cycle)
        chunks.append(text[pos:pos + step])
        pos += step
    return "".join(compact_stream(chunks, **kwargs))


def keys_of(text):
    """Every object's key sequence, in document order, duplicates included."""
    found = []

    def hook(pairs):
        found.append([k for k, _ in pairs])
        return dict(pairs)

    json.loads(text, object_pairs_hook=hook)
    return found


# ===================================================================== Bug 1: default mode preserves repetition
REPEATED = [
    "Payment received", "Turn left", "The project is ready.", "Please restart the server.", "Deploy failed",
    "Connection refused", "alice", "retry", "Thanks!", "Done.", "Step complete", "Order shipped to customer",
    "User: ok", "Assistant: Done.", "Human: yes", "[12:00] bob: hi", "Error: disk full",
]


@pytest.mark.parametrize("line", REPEATED)
@pytest.mark.parametrize("count", [2, 3, 50])
def test_default_mode_keeps_every_repetition(line, count):
    text = (line + "\n") * count
    assert compact_text(text, redact_secrets=False) == text
    assert stream(text, (3,), redact_secrets=False) == text


def test_conversation_keeps_boundaries_speakers_and_order():
    text = ("User: Turn left\nAssistant: Turning left.\nUser: Turn left\nAssistant: Turning left.\n\n"
            "User: Turn left\nTurn left\nTurn left\nAssistant: Done.\nAssistant: Done.\n")
    assert compact_text(text) == text
    assert stream(text, (4,)) == text


def test_aggressive_flag_is_the_explicit_lossy_mode_and_still_drops_repeats():
    assert compact_text("Payment received\nPayment received\n", aggressive=True, redact_secrets=False) == "Payment received\n"


def test_metrics_report_no_reduction_for_preserved_repeats():
    result = compact_text_with_metrics("Payment received\n" * 4)
    assert result.compacted == "Payment received\n" * 4 and result.out_tokens == result.in_tokens


# ===================================================================== explicit dedupe modes
def test_adjacent_mode_is_explicitly_lossy_and_only_removes_neighbours():
    text = "Turn left\nTurn left\nTurn right\nTurn left\n"
    assert compact_text(text, dedupe="adjacent") == "Turn left\nTurn right\nTurn left\n"


def test_global_mode_matches_the_aggressive_flag():
    text = "Turn left\nTurn right\nTurn left\n"
    assert compact_text(text, dedupe="global") == compact_text(text, aggressive=True) == "Turn left\nTurn right\n"


def test_explicit_dedupe_overrides_the_aggressive_flag():
    text = "Turn left\nTurn right\nTurn left\n"
    assert compact_text(text, dedupe="off", aggressive=True) == text


def test_invalid_dedupe_mode_is_rejected():
    for call in (lambda: compact_text("x", dedupe="bogus"), lambda: RealtimeCompactor(dedupe="bogus"),
                 lambda: compact_text_with_metrics("x", dedupe="bogus")):
        with pytest.raises(ValueError):
            call()


RUN_MARKER = re.compile(r"^\[previous line repeated (\d+) more times\]$")


def expand_runs(text):
    """Invert dedupe='runs': rebuild the original lines from the count markers."""
    out, previous = [], None
    for line in text.split("\n"):
        m = RUN_MARKER.match(line)
        if m and previous is not None:
            out.extend([previous] * int(m.group(1)))
        else:
            out.append(line)
            previous = line
    return "\n".join(out)


def test_runs_mode_collapses_long_runs_and_keeps_the_count():
    text = "Payment received\n" * 100
    out = compact_text(text, dedupe="runs")
    assert out == "Payment received\n[previous line repeated 99 more times]\n"
    assert expand_runs(out) == text


@pytest.mark.parametrize("line", REPEATED)
def test_runs_mode_round_trips_to_the_original(line):
    for count in (1, 2, 3, 4, 5, 9, 40, 400):
        text = (line + "\n") * count
        out = compact_text(text, dedupe="runs", redact_secrets=False)
        assert expand_runs(out) == text, (line, count)
        assert len(out) <= len(text), (line, count)  # never expands
        assert stream(text, (7,), dedupe="runs", redact_secrets=False) == out


def test_runs_mode_never_touches_code_events_or_structured_lines():
    for text in ("}\n" * 60, "pass\n" * 60, "2026-10-10 12:00:00 ERROR x\n" * 60, "- item\n" * 60, "| a |\n" * 60, "x = 1\n" * 60,
                 "src/a.py\n" * 60, "total 0\n" * 60):
        assert compact_text(text, dedupe="runs", redact_secrets=False) == text


def test_runs_mode_blank_line_ends_a_run_and_a_different_line_does_too():
    text = "Turn left\n" * 30 + "\n" + "Turn left\n" * 30 + "Turn right\n" + "Turn left\n" * 30
    out = compact_text(text, dedupe="runs")
    assert out.count("[previous line repeated 29 more times]") == 3 and expand_runs(out).replace("\n\n", "\n") == text.replace("\n\n", "\n")
    assert out.index("Turn right") < out.rindex("Turn left")


def test_runs_mode_output_is_stable_when_compacted_again():
    once = compact_text("Deploy failed\n" * 80, dedupe="runs")
    assert compact_text(once, dedupe="runs") == once


def test_runs_mode_final_line_without_newline():
    out = compact_text("Deploy failed\n" * 50 + "Deploy failed", dedupe="runs")
    assert out == "Deploy failed\n[previous line repeated 50 more times]"


FRAGMENTS = ["Payment received", "Payment received", "Turn left", "Turn left", "The project is ready.", "User: ok", "}", "pass",
             "ERROR x", "", "x = 1", "- item", "retry", "alice", "import os", "Thanks!"]


def random_text(rng):
    text = "".join(rng.choice(FRAGMENTS) * 1 + "\n" for _ in range(rng.randint(0, 40)))
    return text[: rng.randint(0, len(text))] if text and rng.random() < 0.3 else text


@pytest.mark.parametrize("seed", range(300))
def test_every_dedupe_mode_streams_exactly_like_batch(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    for mode in ("off", "runs", "adjacent", "global"):
        batch = compact_text(text, dedupe=mode)
        assert stream(text, (1,), dedupe=mode) == batch, (mode, text)
        assert stream(text, (rng.randint(2, 9),), dedupe=mode) == batch, (mode, text)


@pytest.mark.parametrize("seed", range(300, 500))
def test_default_and_runs_modes_never_lose_a_line(seed):
    rng = random.Random(seed)
    text = random_text(rng)
    lines = [line for line in text.split("\n") if line.strip()]
    assert [l for l in compact_text(text).split("\n") if l.strip()] == lines  # default: every line, same order
    out = compact_text(text, dedupe="runs")
    assert [l for l in expand_runs(out).split("\n") if l.strip()] == lines  # runs: lossless after expansion
    assert len(out) <= len(compact_text(text))


# ===================================================================== Bug 2: structured redaction
SECRET_JSON = {
    "object under secret key": '{"password": {"user": "bob", "pass": "x"}, "name": "keep"}',
    "no duplicate keys": '{"secret": {"a": "1", "b": "2", "c": "3"}, "other": 1}',
    "nested objects and arrays": '{"api_key": [{"id": 1, "k": "abc"}, {"id": 2, "k": "def", "deep": {"z": [1, 2, {"q": "r"}]}}], "name": "keep"}',
    "escaped characters": '{"password": ["a\\"b", "c\\\\d", "line\\nbreak", "\\u00e9"], "ok": "yes"}',
    "mixed secret and plain": '{"password": "p", "user": "bob", "note": "n", "items": [1, 2, 3], "flag": true}',
    "multiline": '{\n  "secret": {\n    "user": "bob",\n    "tokens": ["t1", "t2"]\n  },\n  "name": "keep",\n  "list": [1, 2]\n}',
    "array of arrays": '{"password": [["a", "b"], ["c"]], "x": [[1], [2]]}',
    "keys that look like secrets": '{"secret": {"password": "p", "api_key": "k"}}',
    "unicode": '{"password": ["中文", "\U0001F600"], "name": "üñî"}',
}


@pytest.mark.parametrize("name", sorted(SECRET_JSON))
def test_redacted_json_keeps_keys_shape_and_unrelated_fields(name):
    doc = SECRET_JSON[name]
    out = redact_secrets(doc)
    assert keys_of(out) == keys_of(doc), "object keys must be unchanged and in order"
    for keys in keys_of(out):
        assert len(keys) == len(set(keys)), "redaction must not introduce duplicate keys"
    original, redacted = json.loads(doc), json.loads(out)

    def shape(v):
        if isinstance(v, dict):
            return {k: shape(x) for k, x in v.items()}
        return [shape(x) for x in v] if isinstance(v, list) else None

    assert shape(redacted) == shape(original), "nesting and array lengths must be unchanged"


def walk(value, path=()):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + (i,))
    else:
        yield path, value


def test_only_scalars_inside_a_secret_value_change():
    doc = '{"password": ["hunter2", {"k": "v"}], "user": "bob", "n": 5, "b": false, "tail": [1, "two"]}'
    before, after = dict(walk(json.loads(doc))), dict(walk(json.loads(redact_secrets(doc))))
    for path, value in before.items():
        if path[0] == "password":
            assert after[path] == "[REDACTED]", path
        else:
            assert after[path] == value, f"unrelated field changed: {path}"


SECRETS_IN = {  # the values that sit under a secret key in each SECRET_JSON document
    "object under secret key": ["bob", '"x"'],
    "no duplicate keys": ['"1"', '"2"', '"3"'],
    "nested objects and arrays": ['"abc"', '"def"', '"r"'],
    "escaped characters": ['a\\"b', "c\\\\d", "line\\nbreak", "\\u00e9"],
    "mixed secret and plain": ['"p"'],
    "multiline": ['"bob"', '"t1"', '"t2"'],
    "array of arrays": ['"a"', '"b"', '"c"'],
    "keys that look like secrets": ['"p"', '"k"'],
    "unicode": ["\u4e2d\u6587", "\U0001F600"],
}


@pytest.mark.parametrize("name", sorted(SECRET_JSON))
def test_secret_values_are_gone_and_plain_values_remain(name):
    out = redact_secrets(SECRET_JSON[name])
    for secret in SECRETS_IN[name]:
        assert secret not in out, (name, secret, out)
    for plain in ('"keep"', '"yes"', '"bob"', '"n"', "true") if name in ("nested objects and arrays", "escaped characters", "mixed secret and plain") else ():
        if plain in SECRET_JSON[name] and plain not in SECRETS_IN[name]:
            assert plain in out, (name, plain)


def test_multiline_structure_masks_values_not_keys_across_lines():
    doc = '{\n  "secret": {\n    "user": "bob",\n    "tokens": ["t1", "t2"]\n  },\n  "name": "keep"\n}'
    out = redact_secrets(doc)
    assert out == ('{\n  "secret": {\n    "user": "[REDACTED]",\n    "tokens": ["[REDACTED]", "[REDACTED]"]\n  },\n  "name": "keep"\n}')
    assert stream(doc, (1,)) == out == compact_text(doc)


def test_python_dict_literals_stay_valid_and_keep_keys():
    for src in ('cfg = {"password": {"user": "bob", "pass": "x"}, "n": 1}\n', "cfg = {'secret': ['a', 'b'], 'k': 2}\n"):
        out = redact_secrets(src)
        tree = ast.parse(out)
        before = ast.literal_eval(src.split("=", 1)[1].strip())
        after = ast.literal_eval(out.split("=", 1)[1].strip())
        assert list(after) == list(before) and len(after) == len(before)
        assert after["n" if "n" in after else "k"] == before["n" if "n" in before else "k"]
        assert tree is not None


def test_yaml_flow_collections_keep_keys():
    yaml = pytest.importorskip("yaml", reason="PyYAML is needed to compare YAML structure (installed in CI)")
    doc = "password: {user: bob, pass: x}\nsecret: [a, b, c]\nname: keep\n"
    out = redact_secrets(doc)
    data, original = yaml.safe_load(out), yaml.safe_load(doc)
    assert list(data["password"]) == list(original["password"]) and len(data["secret"]) == 3 and data["name"] == "keep"
    assert "bob" not in out and "[a" not in out


def test_masked_structures_are_idempotent():
    for doc in SECRET_JSON.values():
        once = redact_secrets(doc)
        assert redact_secrets(once) == once
