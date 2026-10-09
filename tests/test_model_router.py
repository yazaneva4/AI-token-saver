import pytest
from model_router import route, classify, command, shell, normalize_main, Step


def models(r):
    return [(s.model, s.role) for s in r.steps]


def test_tiers():
    assert classify("image_gen") == "low" and classify("implement") == "medium"
    assert classify("architecture") == "high" and classify("release") == "ultra"
    assert classify("mystery", tokens=100) == "low"
    assert classify("mystery", tokens=90000) == "ultra"


def test_auto_is_the_default_for_every_main_model():
    for main in ("opus", "sonnet", "haiku"):
        assert route("edit", main=main, env={}).mode == "auto"


def test_auto_picks_cheapest_model_that_meets_quality():
    assert models(route("summary", main="opus", env={})) == [("haiku", "executor")]
    assert models(route("edit", main="opus", env={})) == [("sonnet", "executor")]
    assert models(route("edit", main="haiku", env={})) == [("sonnet", "executor")]


def test_auto_mixes_for_hard_work_and_quality_pref_uses_opus():
    r = route("release", main="sonnet", env={})
    assert models(r) == [("sonnet", "executor"), ("opus", "verifier")] and r.detail["chosen"] == "mix:sonnet+opus"
    assert models(route("plan", main="sonnet", prefer="quality", env={})) == [("opus", "executor")]


def test_auto_quality_floor_rules_out_weak_solo():
    r = route("architecture", main="haiku", env={})
    assert r.steps and "solo:haiku" not in r.detail["scores"]


def test_auto_reports_scores_and_main_tokens_saved():
    r = route("edit", main="opus", tokens=10000, env={})
    assert r.detail["prefer"] == "balanced" and r.detail["main_tokens_saved"] == 8500
    assert r.detail["chosen"] in r.detail["scores"]


def test_auto_prefer_env_and_validation():
    assert route("plan", main="sonnet", env={"AITS_PREFER": "quality"}).detail["prefer"] == "quality"
    with pytest.raises(ValueError):
        route("edit", prefer="bogus", env={})


def test_router_mode_still_advises():
    r = route("architecture", main="haiku", mode="router", env={})
    assert r.mode == "router" and r.steps == () and "opus" in r.advice


@pytest.mark.parametrize("main", ["opus", "sonnet", "haiku"])
def test_solo_runs_nothing(main):
    r = route("edit", main=main, mode="solo", env={})
    assert r.mode == "solo" and r.steps == ()


def test_one_model_any_main_can_use_any_model():
    assert models(route("edit", main="opus", mode="one", model="haiku", env={})) == [("haiku", "executor")]
    assert models(route("edit", main="sonnet", mode="one", model="opus", env={})) == [("opus", "executor")]
    assert models(route("edit", main="haiku", mode="one", model="sonnet", env={})) == [("sonnet", "executor")]


def test_mix_picks_best_model_per_tier():
    assert models(route("summary", main="opus", mode="mix", env={})) == [("haiku", "executor")]
    assert models(route("edit", main="sonnet", mode="mix", env={})) == [("sonnet", "executor")]
    assert models(route("plan", main="haiku", mode="mix", env={})) == [("opus", "executor")]
    assert models(route("release", main="opus", mode="mix", env={})) == [("sonnet", "executor"), ("opus", "verifier")]


def test_bad_mode_and_env_mode():
    with pytest.raises(ValueError):
        route("edit", mode="bogus", env={})
    assert route("edit", main="opus", env={"AITS_SUBAGENT_MODE": "solo"}).mode == "solo"


def test_main_aliases_env_and_overrides():
    assert normalize_main("claude-opus-5-5") == "opus" and normalize_main(None) == "sonnet"
    assert route("edit", env={"AITS_MAIN_MODEL": "opus"}).main == "opus"
    assert route("edit", main="opus", mode="one", env={"AITS_SONNET_MODEL": "s-custom"}).steps[0].model == "s-custom"


def test_commands_use_claude_subscription():
    step = route("edit", main="opus", env={"AITS_SONNET_MODEL": "claude-sonnet-latest"}).steps[0]
    assert command(step) == ["claude", "-p", "--model", "claude-sonnet-latest", "--effort", "medium"]
    assert shell(step).startswith("claude -p --model claude-sonnet-latest")
    with pytest.raises(ValueError):
        command(Step("x", "m", "low"))
