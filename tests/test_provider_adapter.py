from context_saver import ContextSaver
from provider_adapter import ProviderAdapter, create_adapter


class FakeHost:
    def __init__(self):
        self.applied = []
        self.state = {
            "project": "OpenSpark",
            "current_task": "Build universal context support",
            "decisions": ["Keep the core provider-neutral"],
            "services": [{"name": "github", "values": {"status": "passing"}}],
        }

    def get_context_state(self):
        return self.state

    def apply_context(self, text, *, fingerprint):
        self.applied.append((text, fingerprint))


class FailingHost(FakeHost):
    def apply_context(self, text, *, fingerprint):
        raise RuntimeError("host apply failed")


def test_adapter_supports_arbitrary_provider_names(tmp_path):
    for name in ("Cursor", "OpenSpark", "Gemini", "Claude", "OpenAI", "CustomAgent"):
        adapter = create_adapter(name, state_path=tmp_path / f"{name}.json")
        result = adapter.save({"project": name, "current_task": "test"})
        assert result.provider == name
        assert result.changed is True
        assert result.fingerprint
        assert "PROJECT:" in result.text


def test_adapter_short_circuits_identical_state():
    adapter = ProviderAdapter("OpenSpark", saver=ContextSaver())
    state = {"project": "OpenSpark", "current_task": "same"}
    first = adapter.save_if_changed(state)
    second = adapter.save_if_changed(state)
    assert first is not None
    assert second is None


def test_prepare_request_compacts_context_before_provider_call_without_persisting(tmp_path):
    path = tmp_path / "claude.json"
    adapter = ProviderAdapter("Claude", state_path=path)
    state = {
        "project": "OpenSpark",
        "current_task": "Route a request",
        "decisions": ["Use provider-neutral adapters", "Use provider-neutral adapters"],
    }

    prepared = adapter.prepare_request(state, "Implement the next routing step")

    assert prepared.provider == "Claude"
    assert prepared.fingerprint
    assert "PROJECT: OpenSpark" in prepared.context
    assert prepared.context.count("Use provider-neutral adapters") == 1
    assert prepared.render().endswith("USER REQUEST:\nImplement the next routing step")
    assert not path.exists(), "preparation must not persist state before provider success"


def test_prepare_request_does_not_change_request_or_call_provider():
    adapter = ProviderAdapter("Cursor", saver=ContextSaver())
    request = "Keep this exact request."
    prepared = adapter.prepare_request({"project": "Demo"}, request)

    assert prepared.request == request
    assert prepared.render() == "PROJECT: Demo\n\nUSER REQUEST:\nKeep this exact request."


def test_save_after_response_persists_only_after_success(tmp_path):
    path = tmp_path / "openspark.json"
    adapter = ProviderAdapter("OpenSpark", state_path=path)
    state = {"project": "OpenSpark", "current_task": "successful cycle"}

    prepared = adapter.prepare_request(state, "Do the work")
    assert prepared.fingerprint
    assert not path.exists()

    result = adapter.save_after_response(state)
    assert result is not None
    assert result.fingerprint == prepared.fingerprint
    assert path.is_file()

    assert adapter.save_after_response(state) is None


def test_host_adapter_applies_only_changed_context():
    host = FakeHost()
    adapter = ProviderAdapter("Cursor", saver=ContextSaver())
    first = adapter.save_from_host(host)
    second = adapter.save_from_host(host)
    assert first is not None
    assert second is None
    assert len(host.applied) == 1


def test_host_apply_failure_does_not_poison_persistent_idempotency(tmp_path):
    path = tmp_path / "host.json"
    host = FailingHost()
    adapter = ProviderAdapter("Claude", state_path=path)
    try:
        adapter.save_from_host(host)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected host apply failure")

    assert not path.exists()


def test_host_can_retry_after_apply_failure(tmp_path):
    path = tmp_path / "host.json"
    failing = FailingHost()
    adapter = ProviderAdapter("Claude", state_path=path)
    try:
        adapter.save_from_host(failing)
    except RuntimeError:
        pass

    host = FakeHost()
    result = ProviderAdapter("Claude", state_path=path).save_from_host(host)
    assert result is not None
    assert len(host.applied) == 1
    assert path.is_file()


def test_provider_name_does_not_change_core_fingerprint():
    state = {"project": "Shared", "current_task": "same"}
    a = ProviderAdapter("Cursor", saver=ContextSaver()).save(state)
    b = ProviderAdapter("OpenSpark", saver=ContextSaver()).save(state)
    assert a.fingerprint == b.fingerprint


def test_adapter_persists_deduplication_across_fresh_instances(tmp_path):
    state_path = tmp_path / "claude.json"
    state = {"project": "AI Token Saver", "current_task": "same request"}

    first = ProviderAdapter("Claude", state_path=state_path).save_if_changed(state)
    second = ProviderAdapter("Claude", state_path=state_path).save_if_changed(state)

    assert first is not None
    assert second is None
    assert state_path.is_file()


def test_adapter_persistent_state_is_provider_specific(tmp_path):
    state = {"project": "Shared", "current_task": "same"}
    cursor_path = tmp_path / "Cursor.json"
    openspark_path = tmp_path / "OpenSpark.json"

    cursor = ProviderAdapter("Cursor", state_path=cursor_path).save_if_changed(state)
    openspark = ProviderAdapter("OpenSpark", state_path=openspark_path).save_if_changed(state)

    assert cursor is not None
    assert openspark is not None
    assert cursor.fingerprint == openspark.fingerprint
    assert cursor_path != openspark_path
