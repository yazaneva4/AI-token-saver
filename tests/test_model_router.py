import pytest
from model_router import route, classify, verifier


def test_tiers():
    assert classify("image_gen") == "small" and classify("architecture") == "high"
    assert classify("implement") == "medium"
    assert classify("mystery", tokens=100) == "small"
    assert classify("mystery", tokens=50000) == "high"


def test_routes_and_overrides():
    env = {"AITS_MEDIUM_MODEL": "m/x"}
    assert route("plan", env=env).model == "claude-sonnet-5-5"
    assert route("edit", env=env).provider == "together"
    s = route("image", env={"AITS_SMALL_MODEL": "gpt-luna"})
    assert s.provider == "codex"
    assert s.shell("/tmp/o.txt") == (
        "codex exec --yolo --skip-git-repo-check -m gpt-luna "
        "-c 'model_reasoning_effort=\"low\"' -o /tmp/o.txt -")


def test_medium_needs_model_and_codex_only():
    with pytest.raises(ValueError):
        route("edit", env={})
    with pytest.raises(ValueError):
        route("plan", env={}).codex_command("x")


def test_ultra_works_together():
    env = {"AITS_MEDIUM_MODEL": "m/x"}
    r = route("release", env=env)
    assert r.tier == "ultra" and r.model == "m/x"
    assert verifier(r, env) == "claude-sonnet-5-5"
    assert verifier(route("edit", env=env), env) is None
