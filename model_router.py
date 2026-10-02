"""Tiered model routing for delegated work.

high   -> latest Sonnet (the parent Claude / Anthropic API)
medium -> Together (OpenAI-compatible chat API)
small  -> GPT "luna" via the Codex CLI (also used for image generation)

Model ids are defaults only; override them with environment variables
(AITS_HIGH_MODEL, AITS_MEDIUM_MODEL, AITS_SMALL_MODEL) because provider
model names change.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import shlex

HIGH, MEDIUM, SMALL = "high", "medium", "small"
SMALL_KINDS = {"search", "lookup", "fetch", "rename", "format", "summary", "image", "image_gen"}
MEDIUM_KINDS = {"edit", "implement", "refactor", "review", "tests", "docs", "analysis"}
HIGH_KINDS = {"architecture", "plan", "debug", "security", "multi_file_refactor", "research"}
_DEFAULTS = {HIGH: "claude-sonnet-5-5", MEDIUM: "", SMALL: "luna"}
_ENV = {HIGH: "AITS_HIGH_MODEL", MEDIUM: "AITS_MEDIUM_MODEL", SMALL: "AITS_SMALL_MODEL"}
_PROVIDER = {HIGH: "anthropic", MEDIUM: "together", SMALL: "codex"}


@dataclass(frozen=True)
class Route:
    tier: str
    provider: str
    model: str
    reasoning: str | None = None

    def codex_command(self, output_file: str) -> list[str]:
        """Argv for a Codex CLI subagent; prompt goes on stdin (``-``)."""
        if self.provider != "codex":
            raise ValueError(f"{self.provider} tier is not run through the Codex CLI")
        cmd = ["codex", "exec", "--yolo", "--skip-git-repo-check", "-m", self.model]
        if self.reasoning:
            cmd += ["-c", f'model_reasoning_effort="{self.reasoning}"']
        return cmd + ["-o", output_file, "-"]

    def shell(self, output_file: str) -> str:
        return " ".join(shlex.quote(p) for p in self.codex_command(output_file))


def classify(kind: str, *, tokens: int = 0) -> str:
    """Pick a tier from a task kind; unknown kinds fall back to size."""
    k = kind.strip().lower().replace("-", "_").replace(" ", "_")
    if k in SMALL_KINDS:
        return SMALL
    if k in HIGH_KINDS:
        return HIGH
    if k in MEDIUM_KINDS:
        return MEDIUM
    return SMALL if tokens and tokens < 1500 else HIGH if tokens > 20000 else MEDIUM


def route(kind: str, *, tokens: int = 0, env: dict[str, str] | None = None) -> Route:
    env = os.environ if env is None else env
    tier = classify(kind, tokens=tokens)
    model = env.get(_ENV[tier]) or _DEFAULTS[tier]
    if tier == MEDIUM and not model:
        raise ValueError("set AITS_MEDIUM_MODEL to a Together model id for medium work")
    return Route(tier, _PROVIDER[tier], model, "low" if tier == SMALL else None)
