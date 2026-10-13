"""Dispatch a task to the tier chosen by model_router and compact the result.

    python delegate.py --kind edit --prompt-file task.txt [--context-file ctx.txt]

Runs signed-in CLIs (`claude`, `codex`, or custom providers) with your own logins; no
API keys needed. The main model (--main, any model id such as opus, gpt-5 or
gemini-pro, or AITS_MAIN_MODEL) is the manager and reviews the result. Sub-agent
models come from the providers available (--providers, AITS_PROVIDERS), placed in the
same quality tier as Claude's haiku/sonnet/opus.
--mode: auto (default; scores every plan on quality, cost, speed and
main-model tokens, --prefer balanced|quality|cheap|fast|tokens), solo (main does it, no sub-agents), one (one sub-agent model; defaults
opus->sonnet, sonnet->haiku, or --model), mix (best model per tier), router
(advice only).
--timeout SECONDS (or AITS_TIMEOUT, default 600) stops a hung sub-agent CLI call and reports `<cli> timed out after N s`.
"""
from __future__ import annotations

import argparse
import contextvars
import json
import math
import os
import subprocess
import sys
import tempfile
from typing import Callable

from ai_token_saver import compact_text, estimate_tokens
from model_router import Step, command, route

Runner = Callable[[Step, str], str]


DEFAULT_TIMEOUT = 600.0  # seconds a single sub-agent CLI call may run
_TIMEOUT: contextvars.ContextVar[float] = contextvars.ContextVar("aits_timeout", default=DEFAULT_TIMEOUT)


def resolve_timeout(timeout: object = None, env: dict[str, str] | None = None) -> float:
    """``timeout`` argument, else ``AITS_TIMEOUT``, else 600 seconds. Must be a positive number."""
    raw = timeout if timeout is not None else (env if env is not None else os.environ).get("AITS_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"timeout must be a positive number of seconds, got {raw!r}") from None
    if not value > 0 or math.isinf(value):
        raise ValueError(f"timeout must be a positive number of seconds, got {raw!r}")
    return value


def _run(argv: list[str], prompt: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    limit = _TIMEOUT.get() if timeout is None else timeout
    try:
        p = subprocess.run(argv, input=prompt, text=True, capture_output=True, timeout=limit)
    except FileNotFoundError:
        raise RuntimeError(f"`{argv[0]}` CLI not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{argv[0]} timed out after {limit:g} s") from None
    if p.returncode:
        raise RuntimeError(f"{argv[0]} failed: {p.stderr.strip()[:500]}")
    return p


def run_claude(step: Step, prompt: str) -> str:
    return _run(command(step), prompt).stdout


def run_codex(step: Step, prompt: str) -> str:
    with tempfile.NamedTemporaryFile("r", suffix=".txt") as out:
        _run(command(step, out.name), prompt)
        return out.read()


def run_command(step: Step, prompt: str) -> str:
    """Any other provider: its argv template, prompt on stdin, answer on stdout."""
    return _run(command(step), prompt).stdout


RUNNERS: dict[str, Runner] = {"claude": run_claude, "codex": run_codex}


def delegate(kind: str, prompt: str, context: str = "", *, main: str | None = None,
             mode: str | None = None, model: str | None = None, prefer: str | None = None,
             runners: dict[str, Runner] | None = None, env: dict[str, str] | None = None,
             providers: dict | None = None, dedupe: str | None = None, timeout: float | None = None) -> dict:
    """Compact context, run the planned sub-agents (verifier reviews draft), compact the answer."""
    runners = runners or RUNNERS
    limit = resolve_timeout(timeout, env)
    r = route(kind, main=main, mode=mode, model=model, prefer=prefer, tokens=estimate_tokens(prompt + context), env=env,
              providers=providers)
    full = compact_text(f"{context}\n\n{prompt}" if context else prompt, dedupe=dedupe)
    base = {"tier": r.tier, "main": r.main, "mode": r.mode,
            "steps": [f"{s.cli}:{s.model}:{s.effort}:{s.role}" for s in r.steps],
            "tokens_in": estimate_tokens(full), "detail": r.detail}
    if not r.steps:  # solo or router: nothing to run, the main model acts on the advice
        return {**base, "tokens_out": estimate_tokens(r.advice), "result": r.advice}
    out = ""
    token = _TIMEOUT.set(limit)
    try:
        for i, step in enumerate(r.steps):
            p = full if i == 0 else (
                f"Verify and correct this draft. Return the final answer only.\n\nTASK:\n{full}\n\nDRAFT:\n{out}")
            out = (runners.get(step.cli) or run_command)(step, p)
    finally:
        _TIMEOUT.reset(token)
    out = compact_text(out, dedupe=dedupe)
    return {**base, "tokens_out": estimate_tokens(out), "result": out}


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--kind", required=True)
    a.add_argument("--prompt-file", required=True)
    a.add_argument("--context-file")
    a.add_argument("--main", help="main model id: opus, sonnet, haiku, gpt-5, gemini-pro, ... (placed in a tier by name)")
    a.add_argument("--mode", choices=["auto", "solo", "one", "mix", "router"],
                   help="auto (default): best plan by quality/cost/speed/tokens; solo: main does it; one: one sub-agent model; mix: best model per tier; router: advice only")
    a.add_argument("--model", help="sub-agent tier or model id for --mode one (opus/deep, sonnet/standard, haiku/light, or any model id)")
    a.add_argument("--prefer", choices=["balanced", "quality", "cheap", "fast", "tokens"],
                   help="auto priority (default balanced)")
    a.add_argument("--dedupe", choices=["off", "runs", "adjacent", "global"],
                   help="repeated-line handling for context and answers: off (default, keeps every line), runs (count-preserving), adjacent/global (lossy)")
    a.add_argument("--timeout", type=float, help="seconds one sub-agent CLI call may run (default 600, or AITS_TIMEOUT)")
    a.add_argument("--providers", help="comma list of providers to use, in preference order (default: detect)")
    a.add_argument("--json", action="store_true")
    n = a.parse_args(argv)
    try:
        with open(n.prompt_file, encoding="utf-8") as handle:
            prompt = handle.read()
        ctx = ""
        if n.context_file:
            with open(n.context_file, encoding="utf-8") as handle:
                ctx = handle.read()
        env = dict(os.environ)
        if n.providers:
            env["AITS_PROVIDERS"] = n.providers
        res = delegate(n.kind, prompt, ctx, main=n.main, mode=n.mode, model=n.model, prefer=n.prefer, env=env, dedupe=n.dedupe, timeout=n.timeout)
    except (RuntimeError, ValueError, OSError) as e:
        print(f"delegate: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res) if n.json else res["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
