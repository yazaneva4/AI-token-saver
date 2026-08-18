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


def test_adapter_supports_arbitrary_provider_names():
    for name in ("Cursor", "OpenSpark", "Gemini", "Claude", "OpenAI", "CustomAgent"):
        adapter = create_adapter(name)
        result = adapter.save({"project": name, "current_task": "test"})
        assert result.provider == name
        assert result.changed is True
        assert result.fingerprint
        assert "PROJECT:" in result.text


def test_adapter_short_circuits_identical_state():
    adapter = ProviderAdapter("OpenSpark")
    state = {"project": "OpenSpark", "current_task": "same"}
    first = adapter.save_if_changed(state)
    second = adapter.save_if_changed(state)
    assert first is not None
    assert second is None


def test_host_adapter_applies_only_changed_context():
    host = FakeHost()
    adapter = ProviderAdapter("Cursor")
    first = adapter.save_from_host(host)
    second = adapter.save_from_host(host)
    assert first is not None
    assert second is None
    assert len(host.applied) == 1


def test_provider_name_does_not_change_core_fingerprint():
    state = {"project": "Shared", "current_task": "same"}
    a = ProviderAdapter("Cursor").save(state)
    b = ProviderAdapter("OpenSpark").save(state)
    assert a.fingerprint == b.fingerprint
