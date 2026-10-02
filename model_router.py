"""Tiered routing between GPT luna (Codex CLI) and Sonnet (Claude Code CLI).

Both run through the user's own subscriptions via their CLIs; no API keys.
Paired tiers have luna draft and Sonnet verify, each at the effort shown.

low    -> luna(low)
medium -> luna(medium) + sonnet(medium)
high   -> luna(medium) + sonnet(high)
ultra  -> luna(high)   + sonnet(high)     very large work, best effort

Override ids with AITS_LUNA_MODEL (default "luna") and AITS_SONNET_MODEL
(default "sonnet", which the Claude CLI resolves to the latest Sonnet).
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
    MEDIUM: (("codex", "medium"), ("claude", "medium")),
    HIGH: (("codex", "medium"), ("claude", "high")),
    ULTRA: (("codex", "high"), ("claude", "high")),
}
_MODEL = {"codex": ("AITS_LUNA_MODEL", "luna"), "claude": ("AITS_SONNET_MODEL", "sonnet")}


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


def command(step: Step, output_file: str | None = None) -> list[str]:
    """Argv for one subagent; the prompt goes on stdin."""
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
    steps = []
    for cli, effort in _PLAN[tier]:
        var, default = _MODEL[cli]
        steps.append(Step(cli, env.get(var) or default, effort))
    return Route(tier, tuple(steps))
