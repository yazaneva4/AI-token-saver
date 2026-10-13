"""State files are written through an exclusive, non-following temp file; orphans are cleaned up."""
import json
import os
import time

from context_saver import ContextSaver
from realtime_usage_saver import RealtimeUsageSaver

STATE = {"project": "p", "current_task": "t", "decisions": ["a"]}


def test_context_saver_does_not_write_through_a_symlink_at_the_old_tmp_path(tmp_path):
    path = tmp_path / "ctx.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    (tmp_path / "ctx.json.tmp").symlink_to(victim)
    assert ContextSaver(state_path=path).save(STATE).changed
    assert victim.read_text() == "precious"
    assert json.loads(path.read_text())["fingerprint"]


def test_realtime_saver_does_not_write_through_a_symlink_at_the_old_tmp_path(tmp_path):
    path = tmp_path / "rt.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    (tmp_path / "rt.json.tmp").symlink_to(victim)
    saver = RealtimeUsageSaver(state_path=path)
    saver.start()
    saver.feed("some context line here\n")
    saver.finish()
    assert victim.read_text() == "precious"
    assert json.loads(path.read_text())["fingerprint"]


def test_no_temp_files_remain_after_a_save(tmp_path):
    ContextSaver(state_path=tmp_path / "ctx.json").save(STATE)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ctx.json"]


def test_orphaned_temp_files_older_than_a_day_are_removed_on_startup(tmp_path):
    path = tmp_path / "ctx.json"
    old = tmp_path / "ctx.json.4242.deadbeef.tmp"
    fresh = tmp_path / "ctx.json.4343.cafef00d.tmp"
    unrelated = tmp_path / "other.json.1.abcd.tmp"
    for f in (old, fresh, unrelated):
        f.write_text("x")
    two_days = time.time() - 2 * 86400
    os.utime(old, (two_days, two_days))
    os.utime(unrelated, (two_days, two_days))
    ContextSaver(state_path=path)
    RealtimeUsageSaver(state_path=path)
    assert not old.exists() and fresh.exists() and unrelated.exists()
