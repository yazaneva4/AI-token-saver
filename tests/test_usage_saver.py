from usage_saver import (
    IdempotentUsageSaver,
    ServiceState,
    UsageCheckpoint,
    compact_checkpoint,
    normalize_saver_commands,
    state_fingerprint,
)


def test_aliases_collapse_to_one_operation():
    assert normalize_saver_commands("/ai-token-saver /ai-usage-saver") == ("/ai-token-saver",)
    assert normalize_saver_commands("please /ai-usage-saver") == ("/ai-token-saver",)
    assert normalize_saver_commands("nothing here") == ()


def test_idempotent_saver_does_not_repeat_expensive_operation():
    saver = IdempotentUsageSaver()
    calls = []

    def operation(state):
        calls.append(state)
        return "saved"

    first, changed = saver.run({"task": "same"}, operation)
    second, changed_again = saver.run({"task": "same"}, operation)

    assert first == second == "saved"
    assert changed is True
    assert changed_again is False
    assert len(calls) == 1


def test_changed_state_runs_again():
    saver = IdempotentUsageSaver()
    calls = []

    def operation(state):
        calls.append(state)
        return len(calls)

    assert saver.run({"task": "one"}, operation) == (1, True)
    assert saver.run({"task": "two"}, operation) == (2, True)
    assert len(calls) == 2


def test_checkpoint_normalization_is_stable_and_deduplicated():
    checkpoint = UsageCheckpoint(
        project=" OpenSpark ",
        current_task=" daily work ",
        completed=["GitHub done", "GitHub done", ""],
        bugs=["Buggy"],
        services=[ServiceState(" github ", {"branch": " main ", "empty": ""})],
    )
    compacted = compact_checkpoint(checkpoint)
    assert compacted.project == "OpenSpark"
    assert compacted.completed == ["GitHub done"]
    assert compacted.services[0].name == "GITHUB"
    assert compacted.services[0].values == {"branch": "main"}
    assert state_fingerprint(compacted) == state_fingerprint(compact_checkpoint(compacted))


def test_reset_allows_new_operation():
    saver = IdempotentUsageSaver()
    calls = []

    def operation(state):
        calls.append(state)
        return len(calls)

    saver.run("same", operation)
    saver.run("same", operation)
    saver.reset()
    assert saver.run("same", operation) == (2, True)
    assert len(calls) == 2
