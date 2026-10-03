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


def test_subscription_routing():
    assert plan("image_gen") == [("codex", "low")]
    assert plan("edit") == [("codex", "medium")]
    assert plan("plan") == [("claude", "high")]
    assert plan("release") == [("codex", "high"), ("claude", "high")]


def test_model_overrides_and_legacy_luna_alias():
    env = {"AITS_GPT_MODEL": "gpt-custom", "AITS_SONNET_MODEL": "sonnet-custom"}
    gpt = route("edit", env=env).steps[0]
    sonnet = route("plan", env=env).steps[0]
    assert gpt.model == "gpt-custom"
    assert sonnet.model == "sonnet-custom"
    assert route("image_gen", env={}).steps[0].model == "luna"
    assert route("edit", env={"AITS_LUNA_MODEL": "legacy-gpt"}).steps[0].model == "legacy-gpt"


def test_commands_use_cli_subscriptions():
    env = {"AITS_GPT_MODEL": "gpt-luna", "AITS_SONNET_MODEL": "claude-sonnet-latest"}
    gpt = route("edit", env=env).steps[0]
    sonnet = route("plan", env=env).steps[0]
    assert shell(gpt, "/tmp/o.txt") == (
        "codex exec --yolo --skip-git-repo-check -m gpt-luna "
        "-c 'model_reasoning_effort=\"medium\"' -o /tmp/o.txt -")
    assert command(sonnet) == [
        "claude", "-p", "--model", "claude-sonnet-latest", "--effort", "high"
    ]
    ultra = route("release", env={})
    assert ultra.paired
    assert [s.cli for s in ultra.steps] == ["codex", "claude"]


def test_unknown_cli():
    from model_router import Step
    with pytest.raises(ValueError):
        command(Step("x", "m", "low"))
