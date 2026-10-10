"""Smoke tests so the round-2 benchmark scripts keep working (tiny sizes, no git, no network)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args, timeout=120):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def test_compression_benchmark_runs_and_reports_every_dataset(tmp_path):
    out = tmp_path / "c.json"
    done = run("benchmarks/compression_round2.py", "--size", "20000", "--baseline-ref", "none", "--json", str(out))
    assert done.returncode == 0, done.stderr
    rows = json.loads(out.read_text())
    assert len(rows) == 9 and all(r["lost_distinct_lines"] == 0 for r in rows)
    best = next(r for r in rows if "best case" in r["dataset"])
    typical = [r for r in rows if "best case" not in r["dataset"]]
    assert best["saved_pct"] > 95 and all(r["saved_pct"] < 5 for r in typical)


def test_stress_benchmark_smoke(tmp_path):
    out = tmp_path / "s.json"
    done = run("benchmarks/stress_round2.py", "--max-mb", "1", "--timeout", "60", "--only", "special", "--json", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    results = json.loads(out.read_text())
    assert results and all(r["ok"] for r in results)
