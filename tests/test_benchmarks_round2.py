"""Smoke tests so the round-2 benchmark scripts keep working (tiny sizes, no git, no network)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args, timeout=120):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def test_compression_benchmark_runs_and_reports_every_mode(tmp_path):
    out = tmp_path / "c.json"
    done = run("benchmarks/compression_round2.py", "--size", "20000", "--json", str(out))
    assert done.returncode == 0, done.stderr
    rows = {r["dataset"].split(" (")[0]: r for r in json.loads(out.read_text())}
    assert len(rows) == 10
    for row in rows.values():
        assert row["default"]["saved_pct"] < 5, "the default keeps every repeated line"
        assert row["default"]["lossless"] is True, "the default must keep every line with its repeat count"
        assert row["runs"]["lossless"] is True, "dedupe='runs' must expand back to the input"
        for mode in ("default", "runs", "adjacent", "global"):
            assert row[mode]["parse_ok"] in (True, None), (row["dataset"], mode)
    assert rows["repetitive synthetic"]["runs"]["saved_pct"] > 95 and rows["repetitive synthetic"]["adjacent"]["dropped_lines"] > 0
    assert rows["retry/poll output"]["runs"]["saved_pct"] > 80
    typical = [r for n, r in rows.items() if n not in ("repetitive synthetic", "retry/poll output")]
    assert all(r["runs"]["saved_pct"] < 5 and r["adjacent"]["saved_pct"] < 5 for r in typical)


def test_stress_benchmark_smoke(tmp_path):
    out = tmp_path / "s.json"
    done = run("benchmarks/stress_round2.py", "--max-mb", "1", "--timeout", "60", "--only", "special", "--json", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    results = json.loads(out.read_text())
    assert results and all(r["ok"] for r in results)
