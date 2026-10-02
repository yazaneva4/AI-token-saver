import pytest
from model_router import route, classify, command, shell


def plan(kind, env=None):
    return [(s.cli, s.effort) for s in route(kind, env=env or {}).steps]


def test_tiers():
    assert classify("image_gen") == "low" and classify("implement") == "medium"
    assert classify("architecture") == "high" and classify("release") == "ultra"
    assert classify("mystery", tokens=100) == "low"
    assert classify("mystery", tokens=30000) == "high"
    assert classify("mystery", tokens=90000) == "ultra"


def test_pairs():
    assert plan("image") == [("codex", "low")]
    assert plan("edit") == [("codex", "medium"), ("claude", "medium")]
    assert plan("plan") == [("codex", "medium"), ("claude", "high")]
    assert plan("release") == [("codex", "high"), ("claude", "high")]


def test_commands_and_overrides():
    env = {"AITS_LUNA_MODEL": "gpt-luna", "AITS_SONNET_MODEL": "claude-sonnet-5-5"}
    c, s = route("edit", env=env).steps
    assert shell(c, "/tmp/o.txt") == (
        "codex exec --yolo --skip-git-repo-check -m gpt-luna "
        "-c 'model_reasoning_effort=\"medium\"' -o /tmp/o.txt -")
    assert command(s) == ["claude", "-p", "--model", "claude-sonnet-5-5", "--effort", "medium"]
    assert command(route("edit", env={}).steps[1])[3] == "sonnet"


def test_unknown_cli():
    from model_router import Step
    with pytest.raises(ValueError):
        command(Step("x", "m", "low"))
