from context_saver import ContextSaver


def sample_state():
    return {
        "project": "AI Token Saver", "current_task": "Build the real context saver",
        "decisions": ["Preserve technical state", "Preserve technical state"],
        "bugs": ["Second identical save can be expensive"], "fixes": ["Add deterministic fingerprinting"],
        "files": ["context_saver.py", "SKILL.md", "context_saver.py"], "commands": ["git pull origin main"],
        "tests": ["deep benchmark passed"],
        "services": [
            {"name": "github", "values": {"status": "passing"}}, {"name": "vercel", "values": {"status": "deployed"}},
            {"name": "supabase", "values": {"status": "connected"}}, {"name": "gmail", "values": {"status": "waiting"}},
            {"name": "browser", "values": {"status": "researching"}},
        ],
        "next_steps": ["Run the deep context test", "Run the deep context test"],
    }


def test_context_saver_preserves_high_value_state_and_deduplicates():
    result = ContextSaver().save(sample_state())
    snapshot = result.snapshot
    assert snapshot.project == "AI Token Saver"
    assert snapshot.current_task == "Build the real context saver"
    assert snapshot.decisions == ("Preserve technical state",)
    assert snapshot.files == ("context_saver.py", "SKILL.md")
    assert len(snapshot.services) == 5
    assert "BUGS:" in result.text and "NEXT STEPS:" in result.text


def test_context_saver_is_idempotent_for_identical_state():
    saver = ContextSaver(); first = saver.save(sample_state()); second = saver.save(sample_state())
    assert first.changed is True and second.changed is False
    assert first.fingerprint == second.fingerprint and first.text == second.text


def test_save_if_changed_returns_none_for_duplicate_state():
    saver = ContextSaver(); saver.save(sample_state())
    assert saver.save_if_changed(sample_state()) is None


def test_changed_state_gets_a_new_fingerprint():
    saver = ContextSaver(); first = saver.save(sample_state()); changed = sample_state(); changed["next_steps"] = ["Run CI"]
    second = saver.save(changed)
    assert second.changed is True and second.fingerprint != first.fingerprint


def test_normalization_is_order_independent_for_services():
    state = sample_state(); a = ContextSaver().save(state); state["services"] = list(reversed(state["services"])); b = ContextSaver().save(state)
    assert a.fingerprint == b.fingerprint


def test_reset_allows_same_state_to_be_saved_again():
    saver = ContextSaver(); saver.save(sample_state()); saver.reset(); assert saver.save(sample_state()).changed is True


def test_none_values_are_not_saved_as_literal_none():
    state = sample_state(); state["current_task"] = None; state["bugs"] = [None, "real bug"]
    result = ContextSaver().save(state)
    assert result.snapshot.current_task == "" and result.snapshot.bugs == ("real bug",)


def test_secret_values_are_redacted_without_redacting_bare_apikey():
    state = sample_state(); state["commands"] = ["api_key=SUPERSECRET", "api-key=OTHERSECRET", "apikey=keep-this-text", "Bearer abc", "Bearer abcdefghijklmnop"]
    result = ContextSaver().save(state)
    assert "api_key=[REDACTED]" in result.snapshot.commands
    assert "api-key=[REDACTED]" in result.snapshot.commands
    assert "apikey=keep-this-text" in result.snapshot.commands
    assert "Bearer abc" in result.snapshot.commands
    assert "Bearer [REDACTED]" in result.snapshot.commands


def test_secret_redaction_is_fingerprint_stable():
    a = sample_state(); b = sample_state(); a["commands"] = ["api_key=SECRET_ONE"]; b["commands"] = ["api_key=SECRET_TWO"]
    assert ContextSaver().save(a).fingerprint == ContextSaver().save(b).fingerprint


def test_persistent_fingerprint_survives_new_saver_instance(tmp_path):
    path = tmp_path / "context-state.json"
    first = ContextSaver(state_path=path).save(sample_state())
    second = ContextSaver(state_path=path).save_if_changed(sample_state())
    assert first.changed is True and second is None


def test_long_lived_saver_refreshes_fingerprint_from_disk(tmp_path):
    path = tmp_path / "context-state.json"
    first_saver = ContextSaver(state_path=path)
    second_saver = ContextSaver(state_path=path)
    first_saver.save(sample_state())
    assert second_saver.save_if_changed(sample_state()) is None


def test_persistent_state_is_atomic_and_reset_removes_it(tmp_path):
    path = tmp_path / "nested" / "context-state.json"; saver = ContextSaver(state_path=path); saver.save(sample_state())
    assert path.is_file() and not path.with_suffix(".json.tmp").exists()
    saver.reset(); assert not path.exists()
