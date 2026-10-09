"""End-to-end savings report: context, input tokens, output instruction cost, sub-agent offload.

Runs offline on built-in workloads. It measures what this repo actually controls:
  * context tokens: raw pasted history vs the compacted snapshot,
  * input tokens: raw context+request vs the prepared request (incl. output-style line),
  * sub-agent saving: main-model tokens avoided by the auto optimizer (a model of
    review overhead, not a live measurement).
Reply (output) tokens depend on a live model and are NOT measured here; the report
only shows how many tokens each output level adds to the prompt.

    python benchmarks/e2e_savings.py [--json]
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_token_saver import estimate_tokens  # noqa: E402
from model_router import route  # noqa: E402
from provider_adapter import OUTPUT_LEVELS, ProviderAdapter  # noqa: E402

REQUEST = "Implement the next routing step and update the tests."


def _workloads() -> dict[str, dict]:
    padded = ["Use provider-neutral adapters"] * 300 + ["Keep state in ContextSaver"] * 300
    varied = [f"Decision {i}: module_{i}.py uses timeout={i * 10}s and retry={i % 5}" for i in range(150)]
    mixed = [f"Decision {i // 3}: module_{i // 3}.py uses timeout={(i // 3) * 10}s" for i in range(300)]
    return {
        "padded history (2 facts x300)": {"kind": "edit", "decisions": padded},
        "varied history (150 distinct)": {"kind": "edit", "decisions": varied},
        "mixed history (each fact x3)": {"kind": "plan", "decisions": mixed},
    }


@dataclass
class Row:
    workload: str
    raw_context: int
    compact_context: int
    context_saved_pct: float
    raw_input: int
    prepared_input: int
    input_saved_pct: float
    plan: str
    main_tokens_saved_pct: float
    combined_main_pct: float


def _pct(before: int, after: int) -> float:
    return round(100 * (1 - after / before), 2) if before else 0.0


def run() -> dict:
    rows: list[Row] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, w in _workloads().items():
            adapter = ProviderAdapter("bench", state_path=os.path.join(tmp, f"{abs(hash(name))}.json"))
            state = {"project": "Bench", "current_task": "Route a request", "decisions": w["decisions"]}
            raw_ctx = "PROJECT: Bench\nCURRENT TASK: Route a request\nDECISIONS:\n" + "\n".join(f"- {d}" for d in w["decisions"])
            prepared = adapter.prepare_request(state, REQUEST)
            raw_in = estimate_tokens(raw_ctx + "\n\n" + REQUEST)
            prep_in = estimate_tokens(prepared.render())
            r = route(w["kind"], main="opus", tokens=prep_in, env={})
            solo = r.detail["main_tokens_saved"] + max(1000, prep_in) * 0.15
            saved_pct = round(100 * r.detail["main_tokens_saved"] / solo, 2) if solo else 0.0
            # Main-model tokens: raw solo baseline vs compacted input handled with the chosen plan.
            after_main = prep_in if not r.steps else prep_in * 0.15
            rows.append(Row(name, estimate_tokens(raw_ctx), estimate_tokens(prepared.context),
                            _pct(estimate_tokens(raw_ctx), estimate_tokens(prepared.context)),
                            raw_in, prep_in, _pct(raw_in, prep_in), r.detail["chosen"], saved_pct,
                            _pct(raw_in, round(after_main))))
    overhead = {lvl: estimate_tokens(text) for lvl, text in OUTPUT_LEVELS.items()}
    return {"rows": [asdict(r) for r in rows], "output_instruction_tokens": overhead,
            "note": "Reply tokens are not measured offline; sub-agent saving is modeled."}


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--json", action="store_true")
    res = run()
    if a.parse_args(argv).json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"{'workload':34}{'ctx raw>cmp':>14}{'ctx %':>8}{'in raw>prep':>14}{'in %':>8}  plan / main-model saved (modeled) / combined")
    for r in res["rows"]:
        print(f"{r['workload']:34}{r['raw_context']:>6}>{r['compact_context']:<6}{r['context_saved_pct']:>8}"
              f"{r['raw_input']:>7}>{r['prepared_input']:<6}{r['input_saved_pct']:>8}  "
              f"{r['plan']} / {r['main_tokens_saved_pct']}% / {r['combined_main_pct']}%")
    print("output-style instruction cost (tokens added to prompt):", res["output_instruction_tokens"])
    print(res["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
