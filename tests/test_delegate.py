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


def test_low_goes_to_codex_and_compacts():
    log = []
    res = delegate("image", "make a logo", runners=fakes(log), env=ENV)
    assert [l[0] for l in log] == ["codex"] and res["tier"] == "low"
    assert res["result"] == "codex answer"


def test_pairs():
    for kind, want in (("edit", ["together"] * 2), ("plan", ["together", "anthropic"]),
                       ("release", ["anthropic"] * 2)):
        log = []
        res = delegate(kind, "do it", runners=fakes(log), env=ENV)
        assert [l[0] for l in log] == want and len(res["models"]) == 2
        assert log[0][0] + " answer" in log[1][2]


def test_missing_medium_model_and_cli(tmp_path, capsys):
    p = tmp_path / "p.txt"; p.write_text("hi")
    with pytest.raises(ValueError):
        delegate("edit", "x", runners=fakes([]), env={})
    assert main(["--kind", "edit", "--prompt-file", str(p)]) == 1
