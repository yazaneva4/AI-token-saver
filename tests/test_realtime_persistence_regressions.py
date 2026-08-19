from pathlib import Path

from provider_adapter import _provider_state_path
from realtime_usage_saver import RealtimeUsageSaver


def test_realtime_fingerprint_survives_new_instance(tmp_path: Path):
    state = tmp_path / "realtime.json"
    text = "persistent stream\n"

    first = RealtimeUsageSaver(redact_secrets=False, state_path=state)
    assert "".join(first.process([text])) == text
    assert first.result is not None and first.result.changed is True

    second = RealtimeUsageSaver(redact_secrets=False, state_path=state)
    assert second.is_same_input(text)
    assert "".join(second.process([text])) == text
    assert second.result is not None and second.result.changed is False


def test_provider_state_names_cannot_collide():
    assert _provider_state_path("foo/bar") != _provider_state_path("foo_bar")
