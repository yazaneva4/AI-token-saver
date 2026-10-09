import pytest
from model_router import route, classify, command, shell, normalize_main, Step


def test_tiers():
    assert classify("image_gen") == "low" and classify("implement") == "medium"
    assert classify("architecture") == "high" and classify("release") == "ultra"
    assert classify("mystery", tokens=100) == "low"
    assert classify("mystery", tokens=30000) == "high"
    assert classify("mystery", tokens=90000) == "ultra"


def test_opus_main_opus_manages_sonnet_executes():
    r = route("edit", main="opus", env={})
    assert r.mode == "manager_executor" and r.manager == "opus"
    assert [(s.model, s.role, s.effort) for s in r.steps] == [("sonnet", "executor", "medium")]


def test_sonnet_main_sonnet_manages_haiku_executes():
    r = route("plan", main="sonnet", env={})
    assert r.manager == "sonnet"
    assert [(s.model, s.effort) for s in r.steps] == [("haiku", "high")]


def test_haiku_main_is_router_only():
    r = route("architecture", main="haiku", env={})
    assert r.mode == "router" and r.steps == () and "opus" in r.advice
    assert "haiku" in route("summary", main="haiku", env={}).advice
    assert "sonnet" in route("edit", main="haiku", env={}).advice


def test_main_model_aliases_and_env():
    assert normalize_main("claude-opus-5-5") == "opus"
    assert normalize_main("Haiku") == "haiku"
    assert normalize_main(None) == "sonnet"
    assert route("edit", env={"AITS_MAIN_MODEL": "opus"}).manager == "opus"


def test_model_overrides():
    env = {"AITS_SONNET_MODEL": "sonnet-custom", "AITS_HAIKU_MODEL": "haiku-custom"}
    assert route("edit", main="opus", env=env).steps[0].model == "sonnet-custom"
    assert route("edit", main="sonnet", env=env).steps[0].model == "haiku-custom"


def test_commands_use_claude_subscription():
    step = route("edit", main="opus", env={"AITS_SONNET_MODEL": "claude-sonnet-latest"}).steps[0]
    assert command(step) == ["claude", "-p", "--model", "claude-sonnet-latest", "--effort", "medium"]
    assert shell(step).startswith("claude -p --model claude-sonnet-latest")


def test_unknown_cli():
    with pytest.raises(ValueError):
        command(Step("x", "m", "low"))
