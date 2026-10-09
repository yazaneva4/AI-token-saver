import os
import stat

import pytest

from delegate import delegate, main as delegate_main
from model_router import Step, command, route
from providers import catalog, provider_of_model, resolve, tier_of_model

GPT = {"codex": {"light": "gpt-mini", "standard": "gpt-std", "deep": "gpt-pro"}}


def steps(r):
    return [(s.cli, s.model, s.role) for s in r.steps]


# ---------------------------------------------------------------- tier and provider of a model id
@pytest.mark.parametrize("name,tier", [
    ("claude-opus-5-5", "opus"), ("sonnet", "sonnet"), ("claude-haiku-5-5", "haiku"), (None, "sonnet"),
    ("gpt-5", "sonnet"), ("gpt-5-mini", "haiku"), ("gpt-5-nano", "haiku"), ("gpt-5-pro", "opus"), ("o3", "opus"),
    ("gemini-2.5-flash", "haiku"), ("gemini-2.5-pro", "opus"), ("gemini-2.5", "sonnet"), ("deep", "opus"),
    ("light", "haiku"), ("standard", "sonnet"), ("some-local-model", "sonnet"), ("promax", "sonnet"),
])
def test_tier_of_model(name, tier):
    assert tier_of_model(name) == tier


@pytest.mark.parametrize("name,provider", [
    ("claude-opus-5-5", "claude"), ("haiku", "claude"), ("gpt-5-codex", "codex"), ("o3", "codex"),
    ("gemini-pro", None), (None, None), ("llama-3", None),
])
def test_provider_of_model(name, provider):
    assert provider_of_model(name) == provider


# ---------------------------------------------------------------- GPT main, GPT sub-agents, no Claude
def test_gpt_main_uses_same_tier_gpt_models():
    r = route("summary", main="gpt-5", providers=GPT, env={})
    assert steps(r) == [("codex", "gpt-mini", "executor")] and r.main == "sonnet" and r.main_provider == "codex"
    assert steps(route("edit", main="gpt-5-pro", providers=GPT, env={})) == [("codex", "gpt-std", "executor")]
    mixed = route("release", main="gpt-5", providers=GPT, env={})
    assert steps(mixed) == [("codex", "gpt-std", "executor"), ("codex", "gpt-pro", "verifier")]


def test_no_claude_model_is_used_when_claude_is_not_available():
    for kind in ("summary", "edit", "plan", "release"):
        for mode in ("auto", "one", "mix"):
            r = route(kind, main="gpt-5", mode=mode, providers=GPT, env={})
            assert all(s.cli == "codex" for s in r.steps), (kind, mode)


def test_missing_tier_maps_to_nearest_available_tier():
    only_standard = {"codex": {"standard": ""}}
    r = route("plan", main="gpt-5", mode="one", model="deep", providers=only_standard, env={})
    assert steps(r) == [("codex", "", "executor")]
    r = route("summary", main="gpt-5", providers=only_standard, env={})
    assert steps(r) == [("codex", "", "executor")] and r.detail["chosen"] == "one:sonnet"
    assert route("plan", main="gpt-5", providers=only_standard, env={}).detail["chosen"] == "solo:sonnet"
    assert resolve(catalog({}, only_standard), "opus") == ("codex", "", "sonnet")
    assert resolve(catalog({}, only_standard), "haiku") == ("codex", "", "sonnet")


def test_nearest_tier_prefers_higher_on_a_tie():
    cat = catalog({}, {"x": {"light": "a", "deep": "c"}})
    assert resolve(cat, "sonnet") == ("x", "c", "opus")


def test_auto_only_considers_tiers_that_exist():
    r = route("release", main="gpt-5", providers={"codex": {"standard": ""}}, env={})
    assert set(r.detail["scores"]) <= {"solo:sonnet", "one:sonnet"}


def test_main_providers_models_are_preferred_then_others():
    both = {"claude": {"light": "haiku", "standard": "sonnet", "deep": "opus"}, **GPT}
    assert steps(route("summary", main="gpt-5", providers=both, env={}))[0][0] == "codex"
    assert steps(route("summary", main="opus", providers=both, env={}))[0][0] == "claude"
    only_claude = {"claude": both["claude"]}
    assert steps(route("summary", main="gpt-5", providers=only_claude, env={})) == [("claude", "haiku", "executor")]


def test_empty_provider_list_means_the_main_model_works_alone():
    for mode in ("auto", "one", "mix"):
        r = route("edit", main="gpt-5", mode=mode, providers={}, env={})
        assert r.steps == () and r.detail.get("chosen", "solo:sonnet") == "solo:sonnet"


# ---------------------------------------------------------------- configuration from the environment
def fake_bin(tmp_path, *names):
    for name in names:
        path = tmp_path / name
        path.write_text("#!/bin/sh\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(tmp_path)


def test_installed_clis_are_detected_from_path(tmp_path):
    path = fake_bin(tmp_path, "codex")
    assert list(catalog({"PATH": path})) == ["codex"]
    both = fake_bin(tmp_path, "claude", "codex")
    assert list(catalog({"PATH": both})) == ["claude", "codex"]


def test_falls_back_to_claude_when_nothing_is_detected():
    assert list(catalog({})) == ["claude"] and list(catalog({"PATH": ""})) == ["claude"]


def test_aits_providers_orders_and_limits_the_catalog():
    assert list(catalog({"AITS_PROVIDERS": "codex, claude"})) == ["codex", "claude"]
    with pytest.raises(ValueError):
        catalog({"AITS_PROVIDERS": "nope"})


def test_per_tier_model_environment_overrides():
    env = {"AITS_PROVIDERS": "codex", "AITS_CODEX_LIGHT_MODEL": "gpt-mini", "AITS_CODEX_DEEP_MODEL": "gpt-pro"}
    assert catalog(env)["codex"]["tiers"] == {"sonnet": "", "haiku": "gpt-mini", "opus": "gpt-pro"}
    legacy = {"AITS_PROVIDERS": "claude", "AITS_SONNET_MODEL": "s-custom", "AITS_CLAUDE_DEEP_MODEL": "o-custom"}
    assert catalog(legacy)["claude"]["tiers"] == {"haiku": "haiku", "sonnet": "s-custom", "opus": "o-custom"}


def test_custom_provider_from_environment_json():
    env = {"AITS_PROVIDERS": "mycli", "AITS_CUSTOM_PROVIDERS":
           '{"mycli": {"cmd": "mycli --model {model} --effort {effort}", "light": "m1", "deep": "m3"}}'}
    r = route("summary", main="gemini-pro", env=env)
    assert steps(r) == [("mycli", "m1", "executor")]
    assert command(r.steps[0]) == ["mycli", "--model", "m1", "--effort", "low"]
    with pytest.raises(ValueError):
        catalog({"AITS_CUSTOM_PROVIDERS": "not json"})
    with pytest.raises(ValueError):
        catalog({"AITS_CUSTOM_PROVIDERS": "[1]"})


# ---------------------------------------------------------------- commands and running
def test_codex_command_with_and_without_model():
    named = Step("codex", "gpt-x", "high")
    assert command(named, "/tmp/o.txt") == ["codex", "exec", "--skip-git-repo-check", "-m", "gpt-x",
                                            "-c", 'model_reasoning_effort="high"', "-o", "/tmp/o.txt", "-"]
    default = Step("codex", "", "low")
    assert command(default) == ["codex", "exec", "--skip-git-repo-check", "-c", 'model_reasoning_effort="low"', "-"]
    assert "--yolo" not in command(named)


def test_delegate_runs_non_claude_provider_with_injected_runner():
    log = []

    def run(step, prompt):
        log.append((step.cli, step.model, step.effort))
        return "done"

    res = delegate("summary", "x", main="gpt-5", providers=GPT, runners={"codex": run}, env={})
    assert log == [("codex", "gpt-mini", "low")] and res["result"] == "done" and res["main"] == "sonnet"
    assert res["detail"]["resolved"] == ["codex:gpt-mini"]


def test_delegate_runs_custom_provider_through_its_template(monkeypatch):
    import delegate as module
    calls = []
    monkeypatch.setattr(module, "_run", lambda argv, prompt: calls.append(argv) or type("P", (), {"stdout": "out"})())
    providers = {"mycli": {"cmd": "mycli --model {model}", "standard": "m2"}}
    res = delegate("edit", "x", main="gpt-5", providers=providers, env={})
    assert calls == [["mycli", "--model", "m2"]] and res["result"] == "out"


def test_cli_providers_flag(tmp_path, monkeypatch, capsys):
    p = tmp_path / "p.txt"
    p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert delegate_main(["--kind", "summary", "--main", "gpt-5", "--providers", "codex", "--prompt-file", str(p)]) == 1
    assert "codex" in capsys.readouterr().err  # missing CLI is reported by name
