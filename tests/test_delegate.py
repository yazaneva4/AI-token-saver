from delegate import delegate, main


def fakes(log):
    def run(step, p):
        log.append((step.model, step.effort))
        return "answer\n\n\nanswer"
    return {"claude": run}


def test_opus_main_runs_sonnet_executor_and_compacts():
    log = []
    res = delegate("edit", "do it", main="opus", runners=fakes(log), env={})
    assert log == [("sonnet", "medium")]
    assert res["manager"] == "opus" and res["result"] == "answer"


def test_sonnet_main_runs_haiku_executor():
    log = []
    res = delegate("summary", "sum", main="sonnet", runners=fakes(log), env={})
    assert log == [("haiku", "low")] and res["manager"] == "sonnet"


def test_haiku_main_routes_without_running():
    log = []
    res = delegate("architecture", "design", main="haiku", runners=fakes(log), env={})
    assert log == [] and res["mode"] == "router" and "opus" in res["result"]


def test_missing_cli_is_clean_error(tmp_path, monkeypatch):
    p = tmp_path / "p.txt"; p.write_text("hi")
    monkeypatch.setenv("PATH", "")
    assert main(["--kind", "edit", "--main", "opus", "--prompt-file", str(p)]) == 1
