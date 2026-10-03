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


def test_low_is_sonnet_only_and_compacts():
    log = []
    res = delegate("image", "make a logo", runners=fakes(log))
    assert [l[0] for l in log] == ["claude"] and log[0][1] == "low" and res["tier"] == "low"
    assert res["result"] == "claude answer"


def test_tiers_route_to_requested_subscription_workers():
    for kind, expected_cli, efforts in (
        ("edit", ["codex"], ["medium"]),
        ("plan", ["claude"], ["high"]),
        ("release", ["codex", "claude"], ["medium", "high"]),
        ("large_feature", ["codex", "claude"], ["high", "medium"]),
    ):
        log = []
        res = delegate(kind, "do it", runners=fakes(log))
        assert [entry[0] for entry in log] == expected_cli
        assert [entry[1] for entry in log] == efforts
        if kind == "release":
            assert "codex answer" in log[1][2] and len(res["steps"]) == 2
        else:
            assert len(res["steps"]) == 1


def test_missing_cli_is_clean_error(tmp_path, monkeypatch):
    p = tmp_path / "p.txt"; p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert main(["--kind", "image", "--prompt-file", str(p)]) == 1
