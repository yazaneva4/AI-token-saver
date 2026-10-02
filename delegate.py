"""Dispatch a task to the model tier chosen by model_router and compact the result.

    python delegate.py --kind edit --prompt-file task.txt [--context-file ctx.txt]

low    -> Codex CLI (GPT luna)             needs `codex` on PATH
medium -> Together draft + Together verify needs TOGETHER_API_KEY, AITS_MEDIUM_MODEL
high   -> Together draft + Sonnet verify   also needs ANTHROPIC_API_KEY
ultra  -> Sonnet draft + Sonnet verify     needs ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from typing import Callable

from ai_token_saver import compact_text, estimate_tokens
from model_router import Step, codex_command, route

Runner = Callable[[Step, str], str]


def _post(url: str, headers: dict[str, str], body: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def _key(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def run_codex(r: Step, prompt: str) -> str:
    with tempfile.NamedTemporaryFile("r", suffix=".txt") as out:
        p = subprocess.run(codex_command(r, out.name), input=prompt, text=True, capture_output=True)
        if p.returncode:
            raise RuntimeError(f"codex failed: {p.stderr.strip()[:500]}")
        return out.read()


def run_together(r: Step, prompt: str) -> str:
    d = _post("https://api.together.xyz/v1/chat/completions",
              {"Authorization": f"Bearer {_key('TOGETHER_API_KEY')}"},
              {"model": r.model, "messages": [{"role": "user", "content": prompt}]})
    return d["choices"][0]["message"]["content"]


def run_anthropic(r: Step, prompt: str) -> str:
    d = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
              {"model": r.model, "max_tokens": 8192, "messages": [{"role": "user", "content": prompt}]})
    return "".join(b.get("text", "") for b in d["content"])


RUNNERS: dict[str, Runner] = {"codex": run_codex, "together": run_together, "anthropic": run_anthropic}


def delegate(kind: str, prompt: str, context: str = "", *, runners: dict[str, Runner] | None = None,
             env: dict[str, str] | None = None) -> dict:
    """Compact context, run the routed draft (+ verify) steps, compact the answer."""
    runners = runners or RUNNERS
    r = route(kind, tokens=estimate_tokens(prompt + context), env=env)
    full = compact_text(f"{context}\n\n{prompt}" if context else prompt)
    first = r.steps[0]
    out = runners[first.provider](first, full)
    if r.paired:
        second = r.steps[1]
        out = runners[second.provider](
            second, f"Verify and correct this draft. Return the final answer only.\n\nTASK:\n{full}\n\nDRAFT:\n{out}")
    out = compact_text(out)
    return {"tier": r.tier, "models": [s.model for s in r.steps], "tokens_in": estimate_tokens(full),
            "tokens_out": estimate_tokens(out), "result": out}


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
