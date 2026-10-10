"""Round 3 repository audit: every test here failed before its fix (see the PR description)."""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

from ai_token_saver import Memory, load_memory, memory_to_text, save_memory
from context_saver import ContextSaver
from model_router import Step, classify, command, route
from realtime_usage_saver import RealtimeUsageSaver
from usage_saver import state_fingerprint
import providers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- memory files
@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_failed_save_never_destroys_the_previous_memory_file(tmp_path, monkeypatch, failure):
    path = tmp_path / "memory.json"
    save_memory(path, Memory(project="keep", decisions=["a"]))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync" if failure == "fsync" else "replace", boom)
    with pytest.raises(OSError):
        save_memory(path, Memory(project="new", decisions=["b"] * 50))
    monkeypatch.undo()
    assert load_memory(path).project == "keep"
    assert [p.name for p in tmp_path.iterdir()] == ["memory.json"], "no temporary file may be left behind"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_saving_memory_keeps_the_file_permissions(tmp_path):
    import stat
    path = tmp_path / "memory.json"
    save_memory(path, Memory(project="a"))
    os.chmod(path, 0o600)
    save_memory(path, Memory(project="b"))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and load_memory(path).project == "b"


@pytest.mark.skipif(os.name == "nt", reason="symlinks")
def test_saving_memory_writes_through_a_symlink(tmp_path):
    real = tmp_path / "real.json"
    save_memory(real, Memory(project="old"))
    link = tmp_path / "link.json"
    os.symlink(real, link)
    save_memory(link, Memory(project="new"))
    assert link.is_symlink() and load_memory(real).project == "new"


def test_save_memory_round_trips_and_creates_parent_directories(tmp_path):
    path = tmp_path / "deep" / "dir" / "memory.json"
    memory = Memory(project="p", goal="g", decisions=["d é \U0001F600"], history=["h"])
    save_memory(path, memory)
    assert load_memory(path) == memory and [p.name for p in path.parent.iterdir()] == ["memory.json"]


def test_multi_line_memory_entries_cannot_forge_sections_or_bullets():
    memory = Memory(project="p\nGOAL: forged", goal="g", decisions=["use X\nPROJECT: evil\nDECISIONS:\n- injected"], issues=["a\n\nNEXT:\n- b"])
    text = memory_to_text(memory)
    for line in text.split("\n"):
        if line and not line.startswith(" "):
            assert re.match(r"^(PROJECT|GOAL): |^[A-Z]+:$|^- ", line), f"forged structure: {line!r}"
    top_level = [line for line in text.split("\n") if not line.startswith(" ")]
    assert sum(line.startswith("PROJECT:") for line in top_level) == 1 and sum(line.startswith("GOAL:") for line in top_level) == 1
    assert "evil" in text and "injected" in text, "the content itself is preserved, only indented"


def test_single_line_memory_text_is_unchanged():
    memory = Memory(project="p", goal="g", state=["s1", "s2"], next_steps=["n"])
    assert memory_to_text(memory) == "PROJECT: p\n\nGOAL: g\n\nSTATE:\n- s1\n- s2\n\nNEXT:\n- n"


def test_memory_from_dict_ignores_booleans_and_non_finite_numbers():
    data = {"state": [True, False, float("nan"), float("inf"), 1, 2.5, "ok", None, [1], {"a": 1}]}
    assert Memory.from_dict(data).state == ["1", "2.5", "ok"]


# ---------------------------------------------------------------- fingerprints
_FINGERPRINTS = (
    "import sys; sys.path.insert(0, %r)\n"
    "from context_saver import ContextSaver\nfrom usage_saver import state_fingerprint\n"
    "s = {'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta'}\n"
    "print(ContextSaver().build({'decisions': s, 'files': frozenset(s)}).fingerprint(), state_fingerprint({'k': s, 'n': {'x': frozenset(s)}}))"
) % ROOT


def test_fingerprints_of_sets_do_not_depend_on_the_process_hash_seed():
    seen = {subprocess.run([sys.executable, "-c", _FINGERPRINTS], capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": str(seed)}).stdout.strip() for seed in range(6)}
    assert len(seen) == 1 and "" not in seen


def test_a_set_and_the_same_items_sorted_in_a_list_give_the_same_fingerprint():
    items = {"b", "a", "c"}
    assert ContextSaver().build({"decisions": items}).fingerprint() == ContextSaver().build({"decisions": ["a", "b", "c"]}).fingerprint()
    assert state_fingerprint({"k": items}) == state_fingerprint({"k": ["a", "b", "c"]})


def test_self_referencing_state_is_a_clean_value_error():
    loop: dict = {}
    loop["self"] = loop
    with pytest.raises(ValueError):
        state_fingerprint(loop)


# ---------------------------------------------------------------- routing and providers
@pytest.mark.parametrize("bad", [None, 5, 1.5, ["edit"], b"edit"])
def test_task_kind_must_be_a_string(bad):
    with pytest.raises(TypeError):
        classify(bad)
    with pytest.raises(TypeError):
        route(bad, env={})


def test_template_arguments_with_braces_are_kept_literally():
    step = Step("x", "m1", "low", argv_template=("tool", "--config", '{"a": 1, "model": "{model}"}', "-e", "{effort}-{effort}", "{unknown}", "{}"))
    assert command(step) == ["tool", "--config", '{"a": 1, "model": "m1"}', "-e", "low-low", "{unknown}", "{}"]


@pytest.mark.parametrize("spec", [5, [1], "text", None])
def test_provider_specs_must_be_objects(spec):
    with pytest.raises(ValueError):
        providers.catalog({"AITS_PROVIDERS": "x", "AITS_CUSTOM_PROVIDERS": '{"x": %s}' % __import__("json").dumps(spec)})
    with pytest.raises(ValueError):
        route("edit", providers={"x": spec}, env={})


def test_provider_command_must_be_a_string():
    with pytest.raises(ValueError):
        providers.catalog({}, {"x": {"cmd": 5, "standard": "m"}})


def test_blank_provider_names_are_ignored():
    assert list(providers.catalog({"AITS_PROVIDERS": "claude,, ,codex"})) == ["claude", "codex"]


# ---------------------------------------------------------------- state files
def test_a_state_path_that_is_a_directory_is_rejected_up_front(tmp_path):
    with pytest.raises(ValueError):
        RealtimeUsageSaver(state_path=tmp_path)
    with pytest.raises(ValueError):
        ContextSaver(state_path=tmp_path)


def test_corrupt_state_files_are_tolerated(tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text("{not json")
    assert "".join(RealtimeUsageSaver(state_path=bad).process(["a\n"])) == "a\n"
    assert ContextSaver(state_path=bad).save({"project": "p"}).changed


# ---------------------------------------------------------------- delegate.py command line
def delegate(*args):
    done = subprocess.run([sys.executable, os.path.join(ROOT, "delegate.py"), *args], capture_output=True, text=True,
                          env={**os.environ, "PATH": ""})
    return done.returncode, done.stdout, done.stderr


def test_unreadable_input_files_give_a_clean_error(tmp_path):
    good = tmp_path / "p.txt"
    good.write_text("hello")
    binary = tmp_path / "bad.txt"
    binary.write_bytes(b"\xff\xfe\x00bad\x80")
    for args in (["--prompt-file", str(tmp_path / "missing.txt")], ["--prompt-file", str(good), "--context-file", str(tmp_path / "nope")],
                 ["--prompt-file", str(tmp_path)], ["--prompt-file", str(binary)]):
        code, out, err = delegate("--kind", "edit", *args)
        assert code == 1 and "Traceback" not in err and err.startswith("delegate: ") and err.count("\n") == 1, (args, err)


def test_cli_still_works_for_a_normal_run(tmp_path):
    prompt = tmp_path / "p.txt"
    prompt.write_text("hello")
    code, out, err = delegate("--kind", "edit", "--prompt-file", str(prompt), "--main", "opus", "--mode", "solo")
    assert code == 0 and "does this" in out


# ---------------------------------------------------------------- RealtimeUsageSaver supports the dedupe modes
def test_realtime_saver_keeps_repeated_lines_by_default_and_accepts_dedupe(tmp_path):
    text = "Payment received\n" * 60
    assert "".join(RealtimeUsageSaver().process([text])) == text
    assert "".join(RealtimeUsageSaver(dedupe="runs").process([text])) == "Payment received\n[previous line repeated 59 more times]\n"
    assert "".join(RealtimeUsageSaver(dedupe="adjacent").process([text])) == "Payment received\n"
    with pytest.raises(ValueError):
        RealtimeUsageSaver(dedupe="bogus")


def test_fingerprints_distinguish_dedupe_modes_but_not_the_default(tmp_path):
    from realtime_usage_saver import state_fingerprint as fp
    base = fp("same\n")
    assert fp("same\n", dedupe="off") == base, "the default is dedupe='off', so its fingerprint is unchanged"
    assert fp("same\n", aggressive=True) == fp("same\n", dedupe="global"), "aggressive is the same mode as global"
    assert len({fp("same\n", dedupe="runs"), fp("same\n", dedupe="adjacent"), fp("same\n", dedupe="global"), base}) == 4


def test_state_saved_with_one_dedupe_mode_is_not_treated_as_unchanged_for_another(tmp_path):
    path = tmp_path / "s.json"
    first = RealtimeUsageSaver(state_path=path, dedupe="runs")
    first.feed("hello\n")
    first.finish()
    second = RealtimeUsageSaver(state_path=path, dedupe="adjacent")
    second.feed("hello\n")
    assert second.finish()[1].changed is True


# ---------------------------------------------------------------- bounded memory and cost
@pytest.mark.parametrize("mode", ["off", "runs", "adjacent", "global"])
def test_streaming_long_unique_lines_does_not_retain_them(mode):
    import random
    import tracemalloc
    from ai_token_saver import RealtimeCompactor
    rng = random.Random(1)
    compactor = RealtimeCompactor(dedupe=mode, retain=False)
    tracemalloc.start()
    for i in range(100):  # 20 MB of unique 200 KB lines, streamed
        compactor.feed(f"w{i} " + rng.randbytes(100_000).hex() + "\n")
    compactor.finish()
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert retained < 5_000_000, f"{retained / 1e6:.1f} MB still referenced after the stream ended"


def test_runs_mode_does_not_scan_a_huge_unrepeated_line_more_than_adjacent_mode_does():
    # Round 4: the default is now an identity pass, so the cost baseline is the other line-based mode.
    import time
    from ai_token_saver import compact_text
    line = "x" * 5_000_000 + "\n"
    start = time.perf_counter()
    compact_text(line, dedupe="adjacent")
    base = time.perf_counter() - start
    start = time.perf_counter()
    compact_text(line, redact_secrets=False, dedupe="runs")
    assert time.perf_counter() - start < base * 1.5 + 0.2


def test_global_mode_still_recognises_long_repeated_lines_by_content():
    from ai_token_saver import compact_text
    long_a = "alpha " * 100
    long_b = "alpha " * 99 + "omega"  # shares its first 600 characters with long_a
    text = f"{long_a}\n{long_b}\nshort\n{long_a}\n{long_b}\nshort\n"
    assert compact_text(text, redact_secrets=False, dedupe="global") == f"{long_a}\n{long_b}\nshort\n"


# ---------------------------------------------------------------- review findings


def keys_in(value):
    if isinstance(value, dict):
        return [(k, keys_in(v)) for k, v in value.items()]
    return [keys_in(v) for v in value] if isinstance(value, list) else None


def test_persisted_fingerprints_from_before_the_dedupe_modes_are_not_reused():
    import hashlib
    from realtime_usage_saver import state_fingerprint as fp
    old = lambda aggressive: hashlib.sha256(("v1\0common\0" + str(aggressive) + "\0same\n").encode()).hexdigest()
    assert fp("same\n") != old(0), "the old default meant 'adjacent', so its fingerprints must not be reused"
    assert fp("same\n", aggressive=True) != old(1)


def test_custom_provider_templates_do_not_unescape_doubled_braces():
    step = Step("x", "m", "low", argv_template=("tool", '{"a": {"b": 1}}', "{{literal}}"))
    assert command(step) == ["tool", '{"a": {"b": 1}}', "{{literal}}"]
