"""AI Token Saver: compact, dependency-free project context storage.

The module provides deterministic text compaction, approximate token estimation,
and a small JSON memory store. It targets roughly 55% context reduction when
input contains repetition/filler, but never promises an exact ratio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import re
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class CompactionResult:
    """Result of text compaction with before/after metrics."""
    original: str
    compacted: str
    in_tokens: int
    out_tokens: int
    reduction_percent: float


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

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Memory":
        """Build Memory safely from JSON, ignoring unknown fields and bad list values."""
        result: dict[str, object] = {}
        for item in fields(cls):
            value = data.get(item.name)
            if item.name in {"project", "goal"}:
                result[item.name] = value if isinstance(value, str) else ""
            else:
                result[item.name] = (
                    [str(entry) for entry in value if isinstance(entry, (str, int, float))]
                    if isinstance(value, list)
                    else []
                )
        return cls(**result)


_SPACE = re.compile(r"\s+")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)


def estimate_tokens(text: str) -> int:
    """Estimate tokens without requiring a tokenizer dependency.

    This is intentionally approximate and should not be used for billing.
    """
    if not text.strip():
        return 0
    return max(1, round(len(text) / 4))


def _normalize(line: str) -> str:
    return _SPACE.sub(" ", line.strip())


def _redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS[:2]:
        redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub("[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[3].sub("[REDACTED]", redacted)
    return redacted


def deduplicate(lines: Iterable[str]) -> list[str]:
    """Remove normalized duplicate lines while preserving order and meaning."""
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


def compact_text(text: str, *, redact_secrets: bool = True) -> str:
    """Compact text conservatively without deleting meaningful phrases.

    Only whitespace normalization and duplicate-line removal are performed.
    Secret-looking values are redacted by default before the result is returned.
    """
    source = _redact_secrets(text) if redact_secrets else text
    return "\n".join(deduplicate(source.splitlines()))


def compact_text_with_metrics(text: str, *, redact_secrets: bool = True) -> CompactionResult:
    """Compact text and return detailed metrics including in/out token counts.
    
    This function provides the same compaction as compact_text() but also
    returns the original text, estimated input tokens, estimated output tokens,
    and the actual reduction percentage achieved.
    """
    source = _redact_secrets(text) if redact_secrets else text
    compacted = "\n".join(deduplicate(source.splitlines()))
    in_tokens = estimate_tokens(text)
    out_tokens = estimate_tokens(compacted)
    reduction_pct = reduction(text, compacted)
    return CompactionResult(
        original=text,
        compacted=compacted,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        reduction_percent=reduction_pct,
    )


def reduction(before: str, after: str) -> float:
    """Return approximate token reduction as a fraction from 0 to 1."""
    old = estimate_tokens(before)
    new = estimate_tokens(after)
    if old == 0:
        return 0.0
    return min(1.0, max(0.0, 1.0 - new / old))


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
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Memory file must contain a JSON object")
    return Memory.from_dict(raw)


def merge_list(current: Iterable[str], incoming: Iterable[str]) -> list[str]:
    """Merge memory entries with normalization and stable ordering."""
    return deduplicate([*current, *incoming])


def merge_memory(current: Memory, incoming: Memory) -> Memory:
    """Merge incoming memory while treating non-empty incoming project/goal as current."""
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
    parser.add_argument(
        "--keep-secrets",
        action="store_true",
        help="Disable the default secret redaction (not recommended).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed metrics including in/out token counts.",
    )
    args = parser.parse_args()
    source = args.text or ""
    
    if args.verbose:
        result = compact_text_with_metrics(source, redact_secrets=not args.keep_secrets)
        print(result.compacted)
        print(f"\n--- Metrics ---")
        print(f"Input tokens:  {result.in_tokens}")
        print(f"Output tokens: {result.out_tokens}")
        print(f"Saved tokens:  {result.in_tokens - result.out_tokens}")
        print(f"Reduction:     {result.reduction_percent:.1%}")
    else:
        compacted = compact_text(source, redact_secrets=not args.keep_secrets)
        print(compacted)
        print(f"\nApprox. token reduction: {reduction(source, compacted):.1%}")
