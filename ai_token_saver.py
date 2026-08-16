"""AI Token Saver: compact, dependency-free project context storage.

The module provides deterministic text compaction, token estimation, and a small
JSON memory store. It targets roughly 55% context reduction when the input has
repetition/filler, but never promises an exact ratio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path
from typing import Iterable


@dataclass
class Memory:
    project: str = ""
    goal: str = ""
    state: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)


_FUZZY_FILLER = re.compile(
    r"^(?:now|okay|ok|well|so|basically|in this case|let me|let's|i will|i'll|"
    r"we need to|the idea is|as mentioned|as noted)[,: ]+",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")


def estimate_tokens(text: str) -> int:
    """Estimate tokens without requiring a tokenizer dependency."""
    if not text.strip():
        return 0
    words = re.findall(r"\S+", text)
    punctuation = re.findall(r"[{}\[\]():,.;!?`*_#/\\=<>-]", text)
    return max(1, len(words) + len(punctuation) // 4)


def _normalize(line: str) -> str:
    line = _SPACE.sub(" ", line.strip())
    line = _FUZZY_FILLER.sub("", line).strip()
    return line


def deduplicate(lines: Iterable[str]) -> list[str]:
    """Remove exact and normalized duplicate lines while preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = _normalize(raw)
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def compact_text(text: str) -> str:
    """Compact prose conservatively and deterministically."""
    lines = deduplicate(text.splitlines())
    if not lines:
        return ""

    merged: list[str] = []
    for line in lines:
        code_like = any(x in line for x in ("/", "\\", "=", "::", "->", "`"))
        if merged and not code_like and not merged[-1].endswith((".", ":", ";", "?", "!")):
            merged[-1] += " " + line
        else:
            merged.append(line)
    return "\n".join(merged)


def reduction(before: str, after: str) -> float:
    """Return approximate token reduction as a fraction from 0 to 1."""
    old = estimate_tokens(before)
    new = estimate_tokens(after)
    if old == 0:
        return 0.0
    return max(0.0, 1.0 - new / old)


def save_memory(path: str | Path, memory: Memory) -> None:
    """Write memory as compact, human-readable JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(memory), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_memory(path: str | Path) -> Memory:
    """Load memory, returning an empty Memory when the file does not exist."""
    target = Path(path)
    if not target.exists():
        return Memory()
    data = json.loads(target.read_text(encoding="utf-8"))
    return Memory(**{
        field: data.get(field, []) if field not in ("project", "goal") else data.get(field, "")
        for field in Memory.__dataclass_fields__
    })


def merge_list(current: list[str], incoming: Iterable[str]) -> list[str]:
    """Merge memory entries with normalization and stable ordering."""
    return deduplicate([*current, *incoming])


def merge_memory(current: Memory, incoming: Memory) -> Memory:
    """Merge incoming memory while treating incoming project/goal as current."""
    return Memory(
        project=incoming.project or current.project,
        goal=incoming.goal or current.goal,
        state=merge_list(current.state, incoming.state),
        decisions=merge_list(current.decisions, incoming.decisions),
        files=merge_list(current.files, incoming.files),
        issues=merge_list(current.issues, incoming.issues),
        next_steps=merge_list(current.next_steps, incoming.next_steps),
        preferences=merge_list(current.preferences, incoming.preferences),
        history=merge_list(current.history, incoming.history),
    )


def memory_to_text(memory: Memory) -> str:
    """Render memory in the compact format described by SKILL.md."""
    sections: list[str] = []
    if memory.project:
        sections.append(f"PROJECT: {memory.project}")
    if memory.goal:
        sections.append(f"GOAL: {memory.goal}")

    mapping = [
        ("STATE", memory.state),
        ("DECISIONS", memory.decisions),
        ("FILES", memory.files),
        ("ISSUES", memory.issues),
        ("NEXT", memory.next_steps),
        ("PREFERENCES", memory.preferences),
        ("HISTORY", memory.history),
    ]
    for title, values in mapping:
        values = deduplicate(values)
        if values:
            sections.append(title + ":\n" + "\n".join(f"- {value}" for value in values))
    return "\n\n".join(sections)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compact text for AI Token Saver.")
    parser.add_argument("text", nargs="?", help="Text to compact.")
    args = parser.parse_args()
    source = args.text or ""
    compacted = compact_text(source)
    print(compacted)
    print(f"\nApprox. token reduction: {reduction(source, compacted):.1%}")
