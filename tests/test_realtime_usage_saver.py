from realtime_usage_saver import RealtimeUsageSaver, state_fingerprint


def test_fingerprint_is_stable():
    assert state_fingerprint("hello") == state_fingerprint("hello")
    assert state_fingerprint("hello") != state_fingerprint("hello!")


def test_realtime_process_preserves_stream_data_and_flushes_final_buffer():
    text = "alpha\nbeta\ntrailing"
    saver = RealtimeUsageSaver(redact_secrets=False)
    output = "".join(saver.process(text[i : i + 2] for i in range(0, len(text), 2)))
    assert output == text
    assert saver.result is not None
    assert saver.result.result.compacted == text


def test_repeated_input_can_be_detected_without_reprocessing_state():
    text = "same state\n"
    saver = RealtimeUsageSaver(redact_secrets=False)
    assert "".join(saver.process([text])) == text
    assert saver.is_same_input(text)


def test_repeated_process_marks_second_run_unchanged():
    text = "same state\n"
    saver = RealtimeUsageSaver(redact_secrets=False)
    first = "".join(saver.process([text]))
    assert first == text
    assert saver.result is not None and saver.result.changed is True

    second = "".join(saver.process([text]))
    assert second == text
    assert saver.result is not None and saver.result.changed is False
    assert saver.is_same_input(text)


def test_changed_input_changes_fingerprint():
    saver = RealtimeUsageSaver(redact_secrets=False)
    list(saver.process(["one\n"]))
    assert not saver.is_same_input("two\n")


def test_feed_after_finish_requires_explicit_restart():
    saver = RealtimeUsageSaver(redact_secrets=False)
    list(saver.process(["done\n"]))
    try:
        saver.feed("more\n")
    except RuntimeError as exc:
        assert "start()" in str(exc)
    else:
        raise AssertionError("feed() should reject a finished stream")


def test_finish_after_finish_requires_explicit_restart():
    saver = RealtimeUsageSaver(redact_secrets=False)
    list(saver.process(["done\n"]))
    try:
        saver.finish()
    except RuntimeError as exc:
        assert "start()" in str(exc)
    else:
        raise AssertionError("finish() should reject a finished stream")


def test_tiny_chunks_do_not_drop_characters():
    text = "x" * 5000 + "\n"
    saver = RealtimeUsageSaver(redact_secrets=False)
    output = "".join(saver.process(text[i : i + 1] for i in range(len(text))))
    assert output == text


def test_persistent_state_survives_new_instance(tmp_path):
    path = tmp_path / "fingerprint.json"
    text = "persist me\n"
    first = RealtimeUsageSaver(redact_secrets=False, state_path=path)
    list(first.process([text]))
    second = RealtimeUsageSaver(redact_secrets=False, state_path=path)
    assert second.is_same_input(text)


def test_unchanged_run_does_not_rewrite_persistent_state(tmp_path):
    path = tmp_path / "fingerprint.json"
    text = "same\n"
    first = RealtimeUsageSaver(redact_secrets=False, state_path=path)
    list(first.process([text]))
    before = path.read_text(encoding="utf-8")
    second = RealtimeUsageSaver(redact_secrets=False, state_path=path)
    list(second.process([text]))
    assert path.read_text(encoding="utf-8") == before


def test_lock_is_removed_after_success(tmp_path):
    path = tmp_path / "fingerprint.json"
    saver = RealtimeUsageSaver(redact_secrets=False, state_path=path)
    list(saver.process(["done\n"]))
    assert not path.with_suffix(path.suffix + ".lock").exists()


def test_invalid_lock_timeout_is_rejected():
    try:
        RealtimeUsageSaver(lock_timeout=0)
    except ValueError as exc:
        assert "lock_timeout" in str(exc)
    else:
        raise AssertionError("non-positive lock timeout must be rejected")
