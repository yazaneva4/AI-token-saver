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

OUTPUT_SAVING_RULES = """OUTPUT RULES:
- Answer directly; omit filler, repeated context, and unrequested explanations.
- Follow the user's requested detail and format exactly; never shorten requested code, data, reasoning, or warnings.
- For completed work, give a brief status and the most useful verification result.
"""


def _with_output_saving(prompt: str) -> str:
    """Steer generation toward concise answers without deleting requested content."""
    return f"{OUTPUT_SAVING_RULES}\nTASK:\n{prompt}"


def delegate(kind: str, prompt: str, context: str = "", *, runners: dict[str, Runner] | None = None,
             env: dict[str, str] | None = None) -> dict:
    """Compact context, run the routed draft (+ verify) steps, compact the answer."""
    runners = runners or RUNNERS
    r = route(kind, tokens=estimate_tokens(prompt + context), env=env)
    full = compact_text(f"{context}\n\n{prompt}" if context else prompt)
    first = r.steps[0]
    first_prompt = _with_output_saving(full)
    raw_out = runners[first.cli](first, first_prompt)
    if r.paired:
        second = r.steps[1]
        verification_prompt = (
            "Verify and correct this draft. Follow the user's requested detail and format. "
            "Return only the final answer.\n\n"
            f"TASK:\n{full}\n\nDRAFT:\n{raw_out}"
        )
        raw_out = runners[second.cli](second, _with_output_saving(verification_prompt))
    out = compact_text(raw_out)
    generated_estimate = estimate_tokens(raw_out)
    returned_estimate = estimate_tokens(out)
    return {
        "tier": r.tier,
        "steps": [f"{s.cli}:{s.model}:{s.effort}" for s in r.steps],
        "tokens_in": estimate_tokens(first_prompt),
        # These are character-based estimates, not provider billing data.
        "tokens_out": returned_estimate,  # backward-compatible returned-text estimate
        "tokens_out_generated_estimate": generated_estimate,
        "tokens_out_returned_estimate": returned_estimate,
        "tokens_removed_after_generation_estimate": max(0, generated_estimate - returned_estimate),
        "token_count_source": "approximate",
        "result": out,
    }


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
