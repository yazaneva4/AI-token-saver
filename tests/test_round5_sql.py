"""SQL continuation lines must survive every mode; metrics must report growth honestly."""
import pytest

from ai_token_saver import DEDUPE_MODES, compact_stream, compact_text

SQL = (
    "CREATE FUNCTION set_limit(float4)\nRETURNS float4\nAS 'MODULE_PATHNAME'\nLANGUAGE C STRICT VOLATILE PARALLEL UNSAFE;\n\n"
    "CREATE FUNCTION show_limit()\nRETURNS float4\nAS 'MODULE_PATHNAME'\nLANGUAGE C STABLE PARALLEL SAFE;\n"
)


@pytest.mark.parametrize("mode", DEDUPE_MODES)
def test_create_function_statements_come_back_unchanged(mode):
    assert compact_text(SQL, dedupe=mode) == SQL
    assert "".join(compact_stream([SQL[i:i + 7] for i in range(0, len(SQL), 7)], dedupe=mode)) == SQL
    assert compact_text(SQL, aggressive=True) == SQL


@pytest.mark.parametrize("mode", ["runs", "adjacent", "global"])
@pytest.mark.parametrize("line", [
    "RETURNS internal", "AS 'MODULE_PATHNAME'", "LANGUAGE plpgsql", "FROM users", "WHERE id IS NULL", "JOIN orders",
    "ON users.id", "SET search_path", "VALUES", "INTO audit", "BEGIN", "END", "SELECT name", "INSERT INTO t",
    "UPDATE accounts", "DELETE FROM t", "CREATE INDEX i", "ALTER TABLE t", "DROP TABLE t", "GRANT ALL",
])
def test_sql_clause_lines_are_never_deduplicated(mode, line):
    text = f"{line}\n{line}\n{line}\n"
    assert compact_text(text, dedupe=mode) == text


def test_repeated_continuation_lines_inside_a_sql_file_survive_in_any_case():
    text = "create table a (id int);\nreturns internal\nreturns internal\nlanguage sql\nlanguage sql\n"
    for mode in DEDUPE_MODES:
        assert compact_text(text, dedupe=mode) == text


def test_reduction_percent_is_negative_when_the_compacted_text_is_larger(monkeypatch):
    import ai_token_saver

    monkeypatch.setattr(ai_token_saver, "compact_text", lambda text, **kw: text + "extra words appended")
    result = ai_token_saver.compact_text_with_metrics("short text")
    assert result.output_grew and result.reduction_percent < 0 and result.token_change_percent < 0
