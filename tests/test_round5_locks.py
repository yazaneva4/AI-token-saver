"""A lock left behind by a crash must not stall savers."""
import os
import time

from context_saver import ContextSaver
from realtime_usage_saver import RealtimeUsageSaver

STATE = {"project": "p", "current_task": "t", "decisions": ["a"]}


def _old_empty_lock(state_path, age=5):
    lock = state_path.with_suffix(state_path.suffix + ".lock")
    lock.write_bytes(b"")  # process killed between O_EXCL create and the PID write
    old = time.time() - age
    os.utime(lock, (old, old))
    return lock


def test_context_saver_ignores_an_old_empty_lock_quickly(tmp_path):
    path = tmp_path / "ctx.json"
    _old_empty_lock(path)
    start = time.monotonic()
    result = ContextSaver(state_path=path, lock_timeout=60).save(STATE)
    assert result.changed and time.monotonic() - start < 3


def test_context_saver_ignores_an_old_unparseable_lock_quickly(tmp_path):
    path = tmp_path / "ctx.json"
    lock = _old_empty_lock(path)
    lock.write_bytes(b"{not json")
    old = time.time() - 5
    os.utime(lock, (old, old))
    start = time.monotonic()
    assert ContextSaver(state_path=path, lock_timeout=60).save(STATE).changed
    assert time.monotonic() - start < 3


def test_realtime_saver_ignores_an_old_empty_lock_quickly(tmp_path):
    path = tmp_path / "rt.json"
    _old_empty_lock(path)
    saver = RealtimeUsageSaver(state_path=path, lock_timeout=60)
    saver.start()
    saver.feed("some context line here\n")
    start = time.monotonic()
    _, result = saver.finish()
    assert result.changed and time.monotonic() - start < 3


def test_a_fresh_empty_lock_is_still_respected(tmp_path):
    path = tmp_path / "ctx.json"
    _old_empty_lock(path, age=0)
    try:
        ContextSaver(state_path=path, lock_timeout=0.3).save(STATE)
    except TimeoutError:
        return
    raise AssertionError("a lock younger than a second belongs to a process that may still be writing it")
