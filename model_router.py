"""Main-model-aware sub-agent routing over signed-in CLIs (Claude, Codex/GPT, or custom).

No API keys are used. The main model is always the manager. Quality tiers are
provider-neutral (haiku=light, sonnet=standard, opus=deep): a GPT or Gemini main model
gets sub-agents from whatever models its machine can reach in the same tiers, falling
back to the nearest available tier. See providers.py for configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import shlex

import providers as _providers

_PLACEHOLDER = re.compile(r"\{(model|effort)\}")
LOW, MEDIUM, HIGH, ULTRA = "low", "medium", "high", "ultra"
LOW_KINDS = {"search", "lookup", "fetch", "rename", "format", "summary", "image", "image_gen"}
MEDIUM_KINDS = {"edit", "implement", "tests", "docs", "analysis", "review"}
HIGH_KINDS = {"architecture", "plan", "debug", "security", "multi_file_refactor", "refactor", "research"}
ULTRA_KINDS = {"critical", "release", "migration", "large_feature", "large_codebase"}

AUTO, SOLO, ONE, MIX, ROUTER = "auto", "solo", "one", "mix", "router"
MODES = (AUTO, SOLO, ONE, MIX, ROUTER)
MODELS = ("opus", "sonnet", "haiku")
# Default sub-agent model per main model for "one" mode.
DEFAULT_ONE = {"opus": "sonnet", "sonnet": "haiku", "haiku": "haiku"}
DEFAULT_MODE = {"opus": AUTO, "sonnet": AUTO, "haiku": AUTO}
# Best model per tier: advice for routers and the per-tier pick in "mix" mode.
BEST_MODEL = {LOW: "haiku", MEDIUM: "sonnet", HIGH: "opus", ULTRA: "opus"}
_EFFORT = {LOW: "low", MEDIUM: "medium", HIGH: "high", ULTRA: "high"}


@dataclass(frozen=True)
class Step:
    cli: str  # provider name: "claude", "codex", or a custom provider
    model: str
    effort: str
    role: str = "executor"
    argv_template: tuple[str, ...] = ()  # custom providers: argv with {model}/{effort} placeholders


@dataclass(frozen=True)
class Route:
    tier: str
    main: str
    mode: str
    steps: tuple[Step, ...]
    advice: str = ""
    main_provider: str = ""
    detail: dict = field(default_factory=dict, compare=False)  # auto: chosen plan + scores


def normalize_main(main: str | None) -> str:
    """Map any model id/alias (Claude, GPT, Gemini, ...) to its tier: opus, sonnet or haiku."""
    return _providers.tier_of_model(main)


def command(step: Step, output_file: str | None = None) -> list[str]:
    """Argv for one subscription-backed subagent; prompt goes on stdin."""
    if step.argv_template:
        values = {"model": step.model, "effort": step.effort}
        # Only {model} and {effort} are placeholders; any other brace (JSON arguments, {}) stays as written.
        return [_PLACEHOLDER.sub(lambda match: values[match.group(1)], part) for part in step.argv_template]
    if step.cli == "claude":
        return ["claude", "-p", "--model", step.model, "--effort", step.effort]
    if step.cli == "codex":
        argv = ["codex", "exec", "--skip-git-repo-check"]
        if step.model:  # empty means the CLI's own default model
            argv += ["-m", step.model]
        argv += ["-c", f'model_reasoning_effort="{step.effort}"']
        return argv + (["-o", output_file] if output_file else []) + ["-"]
    raise ValueError(f"unknown cli {step.cli!r}")


def shell(step: Step, output_file: str | None = None) -> str:
    return " ".join(shlex.quote(p) for p in command(step, output_file))


def classify(kind: str, *, tokens: int = 0) -> str:
    """Pick a tier from a task kind; unknown kinds fall back to size."""
    if not isinstance(kind, str):
        raise TypeError("kind must be a string")
    k = kind.strip().lower().replace("-", "_").replace(" ", "_")
    for tier, kinds in ((LOW, LOW_KINDS), (ULTRA, ULTRA_KINDS), (HIGH, HIGH_KINDS), (MEDIUM, MEDIUM_KINDS)):
        if k in kinds:
            return tier
    if tokens > 60000:
        return ULTRA
    return LOW if tokens and tokens < 1500 else HIGH if tokens > 20000 else MEDIUM


# --- Token-saving optimizer (mode "auto") -------------------------------------
# Relative, tunable estimates, not live prices. Models are the latest of each
# family (the aliases resolve to the newest through the Claude CLI).
PREFER = {  # weights: quality, cost, speed, main-model tokens
    "balanced": (0.5, 0.2, 0.2, 0.1),
    "quality": (0.8, 0.07, 0.07, 0.06),
    "cheap": (0.3, 0.5, 0.1, 0.1),
    "fast": (0.3, 0.1, 0.5, 0.1),
    "tokens": (0.3, 0.1, 0.1, 0.5),
}
QUALITY = {  # fit of a model for each task tier, 0-1
    "haiku": {LOW: 0.9, MEDIUM: 0.6, HIGH: 0.3, ULTRA: 0.2},
    "sonnet": {LOW: 0.95, MEDIUM: 0.9, HIGH: 0.7, ULTRA: 0.55},
    "opus": {LOW: 1.0, MEDIUM: 1.0, HIGH: 0.97, ULTRA: 0.9},
}
COST = {"haiku": 1.0, "sonnet": 3.0, "opus": 15.0}   # relative price per token
SPEED = {"haiku": 1.0, "sonnet": 2.0, "opus": 4.0}   # relative latency per token
QUALITY_FLOOR = 0.85   # candidates below this are excluded unless none qualify
REVIEW = 0.15          # share of the task the manager spends reviewing delegated work
VERIFY = 0.5           # a verifier pass reads and corrects, so it costs half a full pass


def _candidates(main: str, tier: str, tokens: int, ranks: tuple[str, ...] = MODELS) -> list[dict]:
    """Every plan the optimizer may pick, with quality/cost/speed/main-token estimates."""
    q = lambda m: QUALITY[m][tier]
    solo = {"name": f"solo:{main}", "mode": SOLO, "models": (),
            "quality": q(main), "cost": COST[main] * tokens, "speed": SPEED[main], "main_tokens": tokens}
    out = [solo]

    def delegated(name, mode, models):
        # Manager review lifts weaker executors toward the manager's own quality.
        top = max(models, key=q)
        quality = q(top) + (0.4 * max(0.0, q(main) - q(top)) if len(models) == 1 else -0.03)
        weight = [1.0] + [VERIFY] * (len(models) - 1)
        cost = sum(COST[m] * w for m, w in zip(models, weight)) * tokens + COST[main] * REVIEW * tokens
        speed = sum(SPEED[m] * w for m, w in zip(models, weight)) + SPEED[main] * REVIEW
        out.append({"name": name, "mode": mode, "models": tuple(models), "quality": min(1.0, quality),
                    "cost": cost, "speed": speed, "main_tokens": REVIEW * tokens})

    for m in ranks:
        delegated(f"one:{m}", ONE, [m])
    if tier in (HIGH, ULTRA) and "sonnet" in ranks and "opus" in ranks:
        delegated("mix:sonnet+opus", MIX, ["sonnet", "opus"])
    return out


def _steps(cat: dict, names, effort: str, main_name: str | None) -> tuple[Step, ...]:
    """Concrete steps for tier names, using the first provider that offers each tier."""
    steps = []
    for i, name in enumerate(names):
        provider, model, _ = _providers.resolve(cat, name, main_name)
        steps.append(Step(provider, model, effort, "executor" if i == 0 else "verifier",
                          tuple(cat[provider]["argv"] or ())))
    return tuple(steps)


def _available_ranks(cat: dict, main_name: str | None) -> tuple[str, ...]:
    """Tiers that some provider can actually serve (a missing tier maps to the nearest one)."""
    found = {r[2] for rank in MODELS if (r := _providers.resolve(cat, rank, main_name))}
    return tuple(rank for rank in MODELS if rank in found)


def _auto(main: str, tier: str, prefer: str, tokens: int, cat: dict, main_name: str | None) -> Route:
    if prefer not in PREFER:
        raise ValueError(f"unknown preference {prefer!r}; use one of {tuple(PREFER)}")
    tokens = max(tokens, 1000)
    cands = _candidates(main, tier, tokens, _available_ranks(cat, main_name))
    ok = [c for c in cands if c["quality"] >= QUALITY_FLOOR] or [max(cands, key=lambda c: c["quality"])]
    best = {k: min(c[k] for c in ok) for k in ("cost", "speed", "main_tokens")}
    wq, wc, ws, wt = PREFER[prefer]
    for c in ok:  # cheaper/faster/leaner than the field's best scores closer to 1
        c["score"] = (wq * c["quality"] + wc * best["cost"] / c["cost"] + ws * best["speed"] / c["speed"]
                      + wt * best["main_tokens"] / c["main_tokens"])
    pick = max(ok, key=lambda c: c["score"])
    solo_main = next(c for c in cands if c["mode"] == SOLO)["main_tokens"]
    detail = {"prefer": prefer, "chosen": pick["name"], "main_tokens_saved": solo_main - pick["main_tokens"],
              "scores": {c["name"]: round(c["score"], 3) for c in ok}}
    effort = _EFFORT[tier]
    steps = _steps(cat, pick["models"], effort, main_name)
    detail["resolved"] = [f"{s.cli}:{s.model or 'default'}" for s in steps]
    if not steps:
        advice = f"{main} (main) does this {tier}-tier task itself; no sub-agent beats it on {prefer}."
    else:
        advice = (f"{main} manages (plans, reviews, owns the final answer); auto chose {pick['name']} "
                  f"for {tier}-tier work ({prefer}).")
    return Route(tier, main, AUTO, steps, advice, _providers.provider_of_model(main_name) or "", detail)


def route(kind: str, *, main: str | None = None, mode: str | None = None, model: str | None = None,
          prefer: str | None = None, tokens: int = 0, env: dict[str, str] | None = None,
          providers: dict | None = None) -> Route:
    """Plan sub-agents for a task. The main model is always the manager.

    mode: auto (default: score solo/one/mix on quality, cost, speed and main-model
    tokens and pick the best for `prefer`, default balanced), solo (main does it, no sub-agents), one (all sub-agents use one model,
    `model` or the main's default), mix (best model per tier; ultra adds a
    stronger verifier), router (advice only). Any main model may use any model.
    """
    env = os.environ if env is None else env
    main_name = main or env.get("AITS_MAIN_MODEL")  # as given: may be a GPT, Gemini or Claude model id
    main = normalize_main(main_name)
    cat = _providers.catalog(env, providers)
    main_provider = _providers.provider_of_model(main_name) or ""
    mode = (mode or env.get("AITS_SUBAGENT_MODE") or DEFAULT_MODE[main]).lower()
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; use one of {MODES}")
    tier = classify(kind, tokens=tokens)
    effort = _EFFORT[tier]
    if mode == AUTO:
        return _auto(main, tier, (prefer or env.get("AITS_PREFER") or "balanced").lower(), tokens, cat, main_name)
    if mode == SOLO:
        return Route(tier, main, SOLO, (), f"{main} (main) does this task itself; no sub-agents.", main_provider)
    if mode == ROUTER:
        best = BEST_MODEL[tier]
        if best == main:
            advice = f"Best model for this {tier}-tier task: {best}. Main model ({main}) should do it directly."
        else:
            advice = (f"Best model for this {tier}-tier task: {best}. Main model ({main}) should hand it to "
                      f"{best} (or ask the user to switch) and relay the result.")
        return Route(tier, main, ROUTER, (), advice, main_provider)
    if not cat:
        return Route(tier, main, SOLO, (), f"{main} (main) does this task itself; no sub-agent provider is available.", main_provider)
    ranks = _available_ranks(cat, main_name)
    if mode == ONE:
        want = normalize_main(model) if model else DEFAULT_ONE[main]
        names = [_providers.resolve(cat, want, main_name)[2]]
    else:  # MIX
        names = [_providers.resolve(cat, BEST_MODEL[tier], main_name)[2]]
        if tier == ULTRA and "sonnet" in ranks and "opus" in ranks:
            names = ["sonnet", "opus"]  # draft, then stronger verification
    steps = _steps(cat, names, effort, main_name)
    advice = f"{main} manages (plans, reviews, owns the final answer); {mode} sub-agents: {', '.join(names)}."
    return Route(tier, main, mode, steps, advice, main_provider)
