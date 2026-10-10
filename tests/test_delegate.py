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
