"""Dispatch a task to the tier chosen by model_router and compact the result.

    python delegate.py --kind edit --prompt-file task.txt [--context-file ctx.txt]

Runs the `claude` CLI with your own login; no API keys needed. The main model
(--main opus|sonnet|haiku, or AITS_MAIN_MODEL) sets the team: opus manages and
sonnet executes; sonnet manages and haiku executes; haiku only routes (returns
the best model and what to do, runs nothing). The manager reviews the result.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Callable

from ai_token_saver import compact_text, estimate_tokens
from model_router import ROUTER, Step, command, route

Runner = Callable[[Step, str], str]


def _run(argv: list[str], prompt: str) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(argv, input=prompt, text=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError(f"`{argv[0]}` CLI not found on PATH") from None
    if p.returncode:
        raise RuntimeError(f"{argv[0]} failed: {p.stderr.strip()[:500]}")
    return p


def run_claude(step: Step, prompt: str) -> str:
    return _run(command(step), prompt).stdout


RUNNERS: dict[str, Runner] = {"claude": run_claude}


def delegate(kind: str, prompt: str, context: str = "", *, main: str | None = None,
             runners: dict[str, Runner] | None = None, env: dict[str, str] | None = None) -> dict:
    """Compact context, run the executor (manager reviews), compact the answer."""
    runners = runners or RUNNERS
    r = route(kind, main=main, tokens=estimate_tokens(prompt + context), env=env)
    full = compact_text(f"{context}\n\n{prompt}" if context else prompt)
    base = {"tier": r.tier, "main": r.main, "mode": r.mode, "manager": r.manager,
            "steps": [f"{s.cli}:{s.model}:{s.effort}:{s.role}" for s in r.steps],
            "tokens_in": estimate_tokens(full)}
    if r.mode == ROUTER:
        return {**base, "tokens_out": estimate_tokens(r.advice), "result": r.advice}
    step = r.steps[0]
    out = compact_text(runners[step.cli](step, full))
    return {**base, "tokens_out": estimate_tokens(out), "result": out}


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--kind", required=True)
    a.add_argument("--prompt-file", required=True)
    a.add_argument("--context-file")
    a.add_argument("--main", help="main model: opus, sonnet, or haiku")
    a.add_argument("--json", action="store_true")
    n = a.parse_args(argv)
    prompt = open(n.prompt_file, encoding="utf-8").read()
    ctx = open(n.context_file, encoding="utf-8").read() if n.context_file else ""
    try:
        res = delegate(n.kind, prompt, ctx, main=n.main)
    except (RuntimeError, ValueError, OSError) as e:
        print(f"delegate: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res) if n.json else res["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
