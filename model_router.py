"""Main-model-aware sub-agent routing over the user's Claude CLI subscription.

No API keys are used. The main model decides the team:
  opus   -> Opus is the manager (plans, reviews); Sonnet is the executor.
  sonnet -> Sonnet is the manager; Haiku is the executor.
  haiku  -> Haiku only routes: it names the best model for the task and what
            the main model should do. Nothing is delegated.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import shlex

LOW, MEDIUM, HIGH, ULTRA = "low", "medium", "high", "ultra"
LOW_KINDS = {"search", "lookup", "fetch", "rename", "format", "summary", "image", "image_gen"}
MEDIUM_KINDS = {"edit", "implement", "tests", "docs", "analysis", "review"}
HIGH_KINDS = {"architecture", "plan", "debug", "security", "multi_file_refactor", "refactor", "research"}
ULTRA_KINDS = {"critical", "release", "migration", "large_feature", "large_codebase"}

MANAGER_EXECUTOR = "manager_executor"
ROUTER = "router"
# main model -> (manager, executor); haiku has no executor, it only routes.
TEAMS = {"opus": ("opus", "sonnet"), "sonnet": ("sonnet", "haiku"), "haiku": ("haiku", None)}
# Best model per tier, used when the main model is only a router.
BEST_MODEL = {LOW: "haiku", MEDIUM: "sonnet", HIGH: "opus", ULTRA: "opus"}
_EFFORT = {LOW: "low", MEDIUM: "medium", HIGH: "high", ULTRA: "high"}


@dataclass(frozen=True)
class Step:
    cli: str  # "claude"
    model: str
    effort: str
    role: str = "executor"


@dataclass(frozen=True)
class Route:
    tier: str
    main: str
    mode: str
    manager: str
    steps: tuple[Step, ...]
    advice: str = ""


def normalize_main(main: str | None) -> str:
    """Map any model id/alias to opus, sonnet, or haiku (default sonnet)."""
    m = (main or "").lower()
    for name in ("opus", "sonnet", "haiku"):
        if name in m:
            return name
    return "sonnet"


def _model(name: str, env: dict[str, str]) -> str:
    return env.get(f"AITS_{name.upper()}_MODEL") or name


def command(step: Step, output_file: str | None = None) -> list[str]:
    """Argv for one subscription-backed subagent; prompt goes on stdin."""
    if step.cli == "claude":
        return ["claude", "-p", "--model", step.model, "--effort", step.effort]
    raise ValueError(f"unknown cli {step.cli!r}")


def shell(step: Step, output_file: str | None = None) -> str:
    return " ".join(shlex.quote(p) for p in command(step, output_file))


def classify(kind: str, *, tokens: int = 0) -> str:
    """Pick a tier from a task kind; unknown kinds fall back to size."""
    k = kind.strip().lower().replace("-", "_").replace(" ", "_")
    for tier, kinds in ((LOW, LOW_KINDS), (ULTRA, ULTRA_KINDS), (HIGH, HIGH_KINDS), (MEDIUM, MEDIUM_KINDS)):
        if k in kinds:
            return tier
    if tokens > 60000:
        return ULTRA
    return LOW if tokens and tokens < 1500 else HIGH if tokens > 20000 else MEDIUM


def route(kind: str, *, main: str | None = None, tokens: int = 0,
          env: dict[str, str] | None = None) -> Route:
    env = os.environ if env is None else env
    main = normalize_main(main or env.get("AITS_MAIN_MODEL"))
    tier = classify(kind, tokens=tokens)
    manager, executor = TEAMS[main]
    if executor is None:
        best = BEST_MODEL[tier]
        if best == "haiku":
            advice = f"Best model for this {tier}-tier task: haiku. Main model (haiku) should do it directly."
        else:
            advice = (f"Best model for this {tier}-tier task: {best}. Main model (haiku) should not attempt it; "
                      f"hand it to {best} (or ask the user to switch) and relay the result.")
        return Route(tier, main, ROUTER, manager, (), advice)
    step = Step("claude", _model(executor, env), _EFFORT[tier], "executor")
    advice = f"{manager} manages (plans, reviews, owns the final answer); {executor} executes."
    return Route(tier, main, MANAGER_EXECUTOR, manager, (step,), advice)
