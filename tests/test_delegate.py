from delegate import delegate, main


def fakes(log):
    def run(step, p):
        log.append((step.model, step.effort))
        return "answer\n\n\nanswer"
    return {"claude": run}


def test_default_opus_runs_sonnet_and_compacts():
    log = []
    res = delegate("edit", "do it", main="opus", runners=fakes(log), env={})
    assert log == [("sonnet", "medium")] and res["result"] == "answer"


def test_solo_and_router_run_nothing():
    for m, mode in (("opus", "solo"), ("sonnet", "solo"), ("haiku", "solo"), ("haiku", None)):
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
