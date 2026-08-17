"""Regression guards for verified Qwen bug reports."""

from ai_token_saver import compact_text


def test_json_object_is_preserved_in_aggressive_mode():
    text = '{"key": "value"}\n{"key": "value"}\n'
    assert compact_text(text, redact_secrets=False, aggressive=True) == text


def test_json_array_is_preserved_in_aggressive_mode():
    text = '[1, 2, 3]\n[1, 2, 3]\n'
    assert compact_text(text, redact_secrets=False, aggressive=True) == text


def test_single_code_hints_are_preserved():
    for line in ("return value\nreturn value\n", "import os\nimport os\n", "lambda x: x\nlambda x: x\n", "yield value\nyield value\n", "raise ValueError()\nraise ValueError()\n", "assert value\nassert value\n", "print(value)\nprint(value)\n"):
        assert compact_text(line, redact_secrets=False, aggressive=True) == line


def test_api_key_requires_separator():
    text = "apikey=keep-this\napi_key=hide-this\napi-key=hide-this\n"
    result = compact_text(text, aggressive=False)
    assert "apikey=keep-this" in result
    assert "api_key=[REDACTED]" in result
    assert "api-key=[REDACTED]" in result


def test_short_bearer_prose_is_not_redacted():
    text = "Bearer test\nBearer example\n"
    assert compact_text(text) == text


def test_long_bearer_credential_is_redacted():
    text = "Bearer abcdefghijklmnop\n"
    assert compact_text(text) == "Bearer [REDACTED]\n"
