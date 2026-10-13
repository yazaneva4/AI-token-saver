from delegate import delegate, main


def fakes(log):
    def run(step, p):
        log.append((step.model, step.effort))
        return "answer\nanswer\n\n\nend"
    return {"claude": run}


def test_auto_default_reports_detail_and_prefer():
    log = []
    res = delegate("summary", "x", main="opus", runners=fakes(log), env={})
    assert log == [("haiku", "low")] and res["detail"]["chosen"] == "one:haiku"
    log.clear()
    res = delegate("plan", "x", main="sonnet", prefer="quality", runners=fakes(log), env={})
    assert log == [("opus", "high")] and res["mode"] == "auto"


def test_default_opus_runs_sonnet_and_compacts():
    log = []
    res = delegate("edit", "do it", main="opus", runners=fakes(log), env={}, dedupe="adjacent")
    assert log == [("sonnet", "medium")] and res["result"] == "answer\n\n\nend"


def test_default_delegate_returns_the_reply_unchanged():
    log = []
    res = delegate("edit", "do it", main="opus", runners=fakes(log), env={})
    assert res["result"] == "answer\nanswer\n\n\nend"  # Round 4: no blank-line collapse, no dropped lines


def test_solo_and_router_run_nothing():
    for m, mode in (("opus", "solo"), ("sonnet", "solo"), ("haiku", "solo"), ("haiku", "router")):
        log = []
        res = delegate("architecture", "design", main=m, mode=mode, runners=fakes(log), env={})
        assert log == [] and res["steps"] == []


def test_one_model_and_mix_with_verifier():
    log = []
    delegate("edit", "x", main="sonnet", mode="one", model="opus", runners=fakes(log), env={})
    assert log == [("opus", "medium")]
    log.clear()
    res = delegate("release", "x", main="opus", mode="mix", runners=fakes(log), env={})
    assert log == [("sonnet", "high"), ("opus", "high")] and len(res["steps"]) == 2


def test_missing_cli_is_clean_error(tmp_path, monkeypatch):
    p = tmp_path / "p.txt"; p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert main(["--kind", "edit", "--main", "opus", "--prompt-file", str(p)]) == 1


# ---------------------------------------------------------------- sub-agent timeout
import time

import pytest

SLOW = {"AITS_PROVIDERS": "slow",
        "AITS_CUSTOM_PROVIDERS": '{"slow": {"cmd": "sleep 30", "light": "m", "standard": "m", "deep": "m"}}'}


def test_a_hung_sub_agent_times_out_with_a_clear_error():
    start = time.monotonic()
    with pytest.raises(RuntimeError, match=r"sleep timed out after 1 s"):
        delegate("summary", "x", main="gemini-pro", env=dict(SLOW), timeout=1)
    assert time.monotonic() - start < 10


def test_timeout_comes_from_the_environment_and_the_flag(tmp_path, monkeypatch):
    start = time.monotonic()
    with pytest.raises(RuntimeError, match=r"timed out after 1 s"):
        delegate("summary", "x", main="gemini-pro", env={**SLOW, "AITS_TIMEOUT": "1"})
    assert time.monotonic() - start < 10
    p = tmp_path / "p.txt"; p.write_text("hi")
    for key, value in SLOW.items():
        monkeypatch.setenv(key, value)
    start = time.monotonic()
    assert main(["--kind", "summary", "--main", "gemini-pro", "--prompt-file", str(p), "--timeout", "1"]) == 1
    assert time.monotonic() - start < 10


def test_invalid_timeouts_are_rejected():
    for bad in (0, -1, float("nan"), "soon"):
        with pytest.raises(ValueError):
            delegate("summary", "x", main="opus", runners=fakes([]), env={}, timeout=bad)
    with pytest.raises(ValueError):
        delegate("summary", "x", main="opus", runners=fakes([]), env={"AITS_TIMEOUT": "abc"})
