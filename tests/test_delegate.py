import pytest
from delegate import delegate, main, run_claude
from model_router import Step


def fakes(log):
    def mk(name):
        def run(step, p):
            log.append((name, step.effort, p))
            return f"{name} answer\n\n\n{name} answer"
        return run
    return {k: mk(k) for k in ("codex", "claude")}


def test_low_is_luna_only_and_compacts():
    log = []
    res = delegate("image", "make a logo", runners=fakes(log))
    assert [l[0] for l in log] == ["codex"] and res["tier"] == "low"
    assert res["result"] == "codex answer"


def test_pairs_draft_then_verify():
    for kind, efforts in (("edit", ["medium", "medium"]), ("plan", ["medium", "high"]),
                          ("release", ["high", "high"])):
        log = []
        res = delegate(kind, "do it", runners=fakes(log))
        assert [l[0] for l in log] == ["codex", "claude"] and [l[1] for l in log] == efforts
        assert "codex answer" in log[1][2] and len(res["steps"]) == 2


def test_missing_cli_is_clean_error(tmp_path, monkeypatch):
    p = tmp_path / "p.txt"; p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert main(["--kind", "image", "--prompt-file", str(p)]) == 1
