"""The skill's always-loaded text stays small; longer material lives in references/ and every pointer resolves."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_skill_md_stays_small_and_its_references_exist():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert len(text) < 6000, "SKILL.md is loaded on every use; move detail to references/"
    pointers = set(re.findall(r"`(references/[\w.-]+\.md)`", text))
    assert pointers, "SKILL.md must point at its reference files"
    for pointer in pointers:
        assert (ROOT / pointer).is_file(), pointer
    assert "api_key" not in text.lower()
