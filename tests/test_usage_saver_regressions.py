from usage_saver import ServiceState, UsageCheckpoint, normalize_saver_commands, state_fingerprint


def test_command_alias_matching_does_not_accept_longer_identifiers():
    assert normalize_saver_commands("/ai-token-saver") == ("/ai-token-saver",)
    assert normalize_saver_commands("please /ai-usage-saver now") == ("/ai-token-saver",)
    assert normalize_saver_commands("/ai-token-saver-extra") == ()
    assert normalize_saver_commands("prefix/ai-token-saver") == ()


def test_checkpoint_service_order_and_duplicates_do_not_change_fingerprint():
    a = UsageCheckpoint(services=[
        ServiceState("github", {"status": "passing"}),
        ServiceState("github", {"status": "passing"}),
        ServiceState("vercel", {"status": "deployed"}),
    ])
    b = UsageCheckpoint(services=[
        ServiceState("vercel", {"status": "deployed"}),
        ServiceState("github", {"status": "passing"}),
    ])
    assert state_fingerprint(a) == state_fingerprint(b)


def test_mapping_fingerprint_preserves_scalar_types():
    assert state_fingerprint({"value": True}) != state_fingerprint({"value": "True"})
    assert state_fingerprint({"value": None}) != state_fingerprint({"value": "None"})


def test_save_and_save_all_are_saver_commands_but_save_secret_is_not():
    assert normalize_saver_commands("/save") == ("/ai-token-saver",)
    assert normalize_saver_commands("ok /save-all now") == ("/ai-token-saver",)
    assert normalize_saver_commands("/save /save-all /ai-usage-saver") == ("/ai-token-saver",)
    assert normalize_saver_commands("/save secret my-key") == ()  # a distinct, explicit secret operation
    for text in ("/saved", "/save-x", "/save_all", "prefix/save", "/saves"):
        assert normalize_saver_commands(text) == (), text
