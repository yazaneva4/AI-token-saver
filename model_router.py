"""Tiered model routing for delegated work.

Every tier is a draft step followed (except low) by a verify step:

low    -> GPT "luna" via the Codex CLI (also image generation)
medium -> two mediums together: Together drafts, a second Together pass verifies
high   -> medium + high: Together drafts, latest Sonnet verifies
ultra  -> high + high: latest Sonnet drafts, latest Sonnet verifies
         (very large work, best effort)

Model ids are defaults only; override with AITS_LOW_MODEL, AITS_MEDIUM_MODEL,
AITS_HIGH_MODEL because provider model names change.
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
_DEFAULTS = {"low": "luna", "medium": "", "high": "claude-sonnet-5-5"}
_ENV = {"low": "AITS_LOW_MODEL", "medium": "AITS_MEDIUM_MODEL", "high": "AITS_HIGH_MODEL"}
_PROVIDER = {"low": "codex", "medium": "together", "high": "anthropic"}
# tier -> (draft level, verify level or None)
_PLAN = {LOW: ("low", None), MEDIUM: ("medium", "medium"), HIGH: ("medium", "high"), ULTRA: ("high", "high")}


@dataclass(frozen=True)
class Step:
    provider: str
    model: str
    reasoning: str | None = None


@dataclass(frozen=True)
class Route:
    tier: str
    steps: tuple[Step, ...]

    @property
    def provider(self) -> str:
        return self.steps[0].provider

    @property
    def model(self) -> str:
        return self.steps[0].model

    @property
    def paired(self) -> bool:
        return len(self.steps) == 2


def codex_command(step: Step, output_file: str) -> list[str]:
    """Argv for a Codex CLI subagent; prompt goes on stdin (``-``)."""
    if step.provider != "codex":
        raise ValueError(f"{step.provider} step is not run through the Codex CLI")
    cmd = ["codex", "exec", "--yolo", "--skip-git-repo-check", "-m", step.model]
    if step.reasoning:
        cmd += ["-c", f'model_reasoning_effort="{step.reasoning}"']
    return cmd + ["-o", output_file, "-"]


def shell(step: Step, output_file: str) -> str:
    return " ".join(shlex.quote(p) for p in codex_command(step, output_file))


def classify(kind: str, *, tokens: int = 0) -> str:
    """Pick a tier from a task kind; unknown kinds fall back to size."""
    k = kind.strip().lower().replace("-", "_").replace(" ", "_")
    for tier, kinds in ((LOW, LOW_KINDS), (ULTRA, ULTRA_KINDS), (HIGH, HIGH_KINDS), (MEDIUM, MEDIUM_KINDS)):
        if k in kinds:
            return tier
    if tokens > 60000:
        return ULTRA
    return LOW if tokens and tokens < 1500 else HIGH if tokens > 20000 else MEDIUM


def _step(level: str, env) -> Step:
    model = env.get(_ENV[level]) or _DEFAULTS[level]
    if not model:
        raise ValueError(f"set {_ENV[level]} to a Together model id for medium work")
    return Step(_PROVIDER[level], model, "low" if level == "low" else None)


def route(kind: str, *, tokens: int = 0, env: dict[str, str] | None = None) -> Route:
    env = os.environ if env is None else env
    tier = classify(kind, tokens=tokens)
    draft, verify = _PLAN[tier]
    steps = (_step(draft, env),) + ((_step(verify, env),) if verify else ())
    return Route(tier, steps)
