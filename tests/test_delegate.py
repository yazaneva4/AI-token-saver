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


def test_low_summary_uses_sonnet_and_compacts():
    log = []
    res = delegate("summary", "summarize this", runners=fakes(log))
    assert [entry[:2] for entry in log] == [("claude", "low")] and res["tier"] == "low"
    assert res["result"] == "claude answer"
    assert "omit filler" in log[0][2]
    assert "requested code" in log[0][2]
    assert res["tokens_out_generated_estimate"] >= res["tokens_out_returned_estimate"]
    assert res["token_count_source"] == "approximate"


def test_image_generation_uses_gpt_luna_low():
    log = []
    res = delegate("image_gen", "make a logo", runners=fakes(log))
    assert [entry[:2] for entry in log] == [("codex", "low")] and res["tier"] == "low"
    assert res["result"] == "codex answer"


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
        assert "OUTPUT RULES:" in log[0][2]
        assert "requested detail and format exactly" in log[0][2]
        if kind in {"release", "large_feature"}:
            assert "codex answer" in log[1][2] and len(res["steps"]) == 2
            assert "OUTPUT RULES:" in log[1][2]
        else:
            assert len(res["steps"]) == 1


def test_missing_cli_is_clean_error(tmp_path, monkeypatch):
    p = tmp_path / "p.txt"; p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert main(["--kind", "image", "--prompt-file", str(p)]) == 1
