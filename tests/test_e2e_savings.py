import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks"))
from e2e_savings import run  # noqa: E402


def rows():
    return {r["workload"].split(" (")[0]: r for r in run()["rows"]}


def test_padded_history_saves_most_context_and_input():
    r = rows()["padded history"]
    assert r["context_saved_pct"] > 95 and r["input_saved_pct"] > 95


def test_repeated_history_saves_partially():
    r = rows()["mixed history"]
    assert 50 < r["context_saved_pct"] < 99


def test_distinct_history_does_not_claim_savings_or_blow_up():
    r = rows()["varied history"]
    assert r["context_saved_pct"] < 5 and r["input_saved_pct"] > -5


def test_subagent_saving_is_reported_and_output_cost_known():
    res = run()
    assert all(r["plan"] and r["main_tokens_saved_pct"] > 0 for r in res["rows"])
    cost = res["output_instruction_tokens"]
    assert cost["standard"] < cost["tight"] < cost["max"]
