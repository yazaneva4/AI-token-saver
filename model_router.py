"""Subscription-backed tier routing for Codex/GPT and Claude/Sonnet CLIs.

All calls use the user's signed-in subscriptions; no API keys are used.
low: GPT Luna; medium: GPT; high: latest Sonnet; ultra: GPT drafts, Sonnet verifies.
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
_PLAN = {
    LOW: (("codex", "low"),),
    MEDIUM: (("codex", "medium"),),
    HIGH: (("claude", "high"),),
    ULTRA: (("codex", "high"), ("claude", "high")),
}


@dataclass(frozen=True)
class Step:
    cli: str  # "codex" or "claude"
    model: str
    effort: str


@dataclass(frozen=True)
class Route:
    tier: str
    steps: tuple[Step, ...]

    @property
    def paired(self) -> bool:
        return len(self.steps) == 2


def _model(cli: str, env: dict[str, str]) -> str:
    if cli == "codex":
        # Keep the previous override working while making the GPT role explicit.
        return env.get("AITS_GPT_MODEL") or env.get("AITS_LUNA_MODEL") or "luna"
    if cli == "claude":
        return env.get("AITS_SONNET_MODEL") or "sonnet"
    raise ValueError(f"unknown cli {cli!r}")


def command(step: Step, output_file: str | None = None) -> list[str]:
    """Argv for one subscription-backed subagent; prompt goes on stdin."""
    if step.cli == "codex":
        cmd = ["codex", "exec", "--yolo", "--skip-git-repo-check", "-m", step.model,
               "-c", f'model_reasoning_effort="{step.effort}"']
        return cmd + (["-o", output_file] if output_file else []) + ["-"]
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


def route(kind: str, *, tokens: int = 0, env: dict[str, str] | None = None) -> Route:
    env = os.environ if env is None else env
    tier = classify(kind, tokens=tokens)
    steps = tuple(Step(cli, _model(cli, env), effort) for cli, effort in _PLAN[tier])
    return Route(tier, steps)
