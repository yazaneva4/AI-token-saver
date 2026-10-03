"""Dispatch a task to the tier chosen by model_router and compact the result.

    python delegate.py --kind edit --prompt-file task.txt [--context-file ctx.txt]

Runs the `codex` and `claude` CLIs with your own logins; no API keys needed.
Paired tiers: luna drafts, Sonnet verifies and corrects.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from typing import Callable

from ai_token_saver import compact_text, estimate_tokens
from model_router import Step, command, route

Runner = Callable[[Step, str], str]


def _run(argv: list[str], prompt: str) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(argv, input=prompt, text=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError(f"`{argv[0]}` CLI not found on PATH") from None
    if p.returncode:
        raise RuntimeError(f"{argv[0]} failed: {p.stderr.strip()[:500]}")
    return p


def run_codex(step: Step, prompt: str) -> str:
    with tempfile.NamedTemporaryFile("r", suffix=".txt") as out:
        _run(command(step, out.name), prompt)
        return out.read()


def run_claude(step: Step, prompt: str) -> str:
    return _run(command(step), prompt).stdout


RUNNERS: dict[str, Runner] = {"codex": run_codex, "claude": run_claude}


def delegate(kind: str, prompt: str, context: str = "", *, runners: dict[str, Runner] | None = None,
             env: dict[str, str] | None = None) -> dict:
    """Compact context, run the routed draft (+ verify) steps, compact the answer."""
    runners = runners or RUNNERS
    r = route(kind, tokens=estimate_tokens(prompt + context), env=env)
    full = compact_text(f"{context}\n\n{prompt}" if context else prompt)
    first = r.steps[0]
    out = runners[first.cli](first, full)
    if r.paired:
        second = r.steps[1]
        out = runners[second.cli](
            second, f"Verify and correct this draft. Return the final answer only.\n\nTASK:\n{full}\n\nDRAFT:\n{out}")
    out = compact_text(out)
    return {"tier": r.tier, "steps": [f"{s.cli}:{s.model}:{s.effort}" for s in r.steps],
            "tokens_in": estimate_tokens(full), "tokens_out": estimate_tokens(out), "result": out}


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--kind", required=True)
    a.add_argument("--prompt-file", required=True)
    a.add_argument("--context-file")
    a.add_argument("--json", action="store_true")
    n = a.parse_args(argv)
    prompt = open(n.prompt_file, encoding="utf-8").read()
    ctx = open(n.context_file, encoding="utf-8").read() if n.context_file else ""
    try:
        res = delegate(n.kind, prompt, ctx)
    except (RuntimeError, ValueError, OSError) as e:
        print(f"delegate: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res) if n.json else res["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
