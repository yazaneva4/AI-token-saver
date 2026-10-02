import pytest
from model_router import route, classify, codex_command

ENV = {"AITS_MEDIUM_MODEL": "m/x"}


def pair(kind, env=ENV):
    return [(s.provider, s.model) for s in route(kind, env=env).steps]


def test_tiers():
    assert classify("image_gen") == "low" and classify("implement") == "medium"
    assert classify("architecture") == "high" and classify("release") == "ultra"
    assert classify("mystery", tokens=100) == "low"
    assert classify("mystery", tokens=30000) == "high"
    assert classify("mystery", tokens=90000) == "ultra"


def test_step_composition():
    assert pair("edit") == [("together", "m/x")] * 2
    assert pair("plan") == [("together", "m/x"), ("anthropic", "claude-sonnet-5-5")]
    assert pair("release") == [("anthropic", "claude-sonnet-5-5")] * 2
    assert pair("image") == [("codex", "luna")]


def test_overrides_and_codex_command():
    s = route("image", env={"AITS_LOW_MODEL": "gpt-luna"}).steps[0]
    assert " ".join(codex_command(s, "/tmp/o.txt")) == (
        "codex exec --yolo --skip-git-repo-check -m gpt-luna -c model_reasoning_effort=\"low\" -o /tmp/o.txt -")


def test_errors():
    with pytest.raises(ValueError):
        route("edit", env={})
    with pytest.raises(ValueError):
        codex_command(route("release", env={}).steps[0], "x")
    assert route("release", env={}).tier == "ultra"  # ultra needs no Together model
