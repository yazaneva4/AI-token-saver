import pytest
from delegate import delegate, main

ENV = {"AITS_MEDIUM_MODEL": "m/x"}


def fakes(log):
    def mk(name):
        def run(r, p):
            log.append((name, r.model, p))
            return f"{name} answer\n\n\n{name} answer"
        return run
    return {k: mk(k) for k in ("codex", "together", "anthropic")}


def test_small_goes_to_codex_and_compacts():
    log = []
    res = delegate("image", "make a logo", runners=fakes(log), env=ENV)
    assert log[0][0] == "codex" and res["tier"] == "small"
    assert res["result"] == "codex answer"


def test_ultra_drafts_then_verifies():
    log = []
    res = delegate("release", "ship it", runners=fakes(log), env=ENV)
    assert [l[0] for l in log] == ["together", "anthropic"]
    assert "together answer" in log[1][2] and res["model"].startswith("m/x+")


def test_missing_medium_model_and_cli(tmp_path, capsys):
    p = tmp_path / "p.txt"; p.write_text("hi")
    with pytest.raises(ValueError):
        delegate("edit", "x", runners=fakes([]), env={})
    assert main(["--kind", "edit", "--prompt-file", str(p)]) == 1
