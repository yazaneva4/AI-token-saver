"""Durable, conservative context-state saver for long-running AI work."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping


PRESERVED_FIELDS = ("project", "current_task", "decisions", "bugs", "fixes", "files", "commands", "tests", "services", "next_steps")


def _clean(value: object) -> str:
    return str(value).strip()


def _dedupe(values: Iterable[object]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = _clean(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _normalize_services(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _clean(item.get("name", "")).upper()
        raw_values = item.get("values", {})
        if not name or not isinstance(raw_values, Mapping):
            continue
        values = {
            _clean(key): _clean(val)
            for key, val in sorted(raw_values.items(), key=lambda pair: str(pair[0]))
            if _clean(val)
        }
        normalized = {"name": name, "values": values}
        key = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return tuple(result)


@dataclass(frozen=True)
class ContextSnapshot:
    """Deterministic, compact state suitable for persistence between turns."""
    project: str = ""
    current_task: str = ""
    decisions: tuple[str, ...] = ()
    bugs: tuple[str, ...] = ()
    fixes: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    services: tuple[dict[str, object], ...] = ()
    next_steps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "current_task": self.current_task,
            "decisions": list(self.decisions),
            "bugs": list(self.bugs),
            "fixes": list(self.fixes),
            "files": list(self.files),
            "commands": list(self.commands),
            "tests": list(self.tests),
            "services": [dict(item) for item in self.services],
            "next_steps": list(self.next_steps),
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_text(self) -> str:
        sections: list[str] = []
        for title, value in (("PROJECT", self.project), ("CURRENT TASK", self.current_task)):
            if value:
                sections.append(f"{title}:\n{value}")
        for title, values in (
            ("DECISIONS", self.decisions), ("BUGS", self.bugs), ("FIXES", self.fixes),
            ("FILES", self.files), ("COMMANDS", self.commands), ("TESTS", self.tests),
            ("NEXT STEPS", self.next_steps),
        ):
            if values:
                sections.append(title + ":\n" + "\n".join(f"- {value}" for value in values))
        if self.services:
            lines: list[str] = []
            for service in self.services:
                lines.append(f"- {service['name']}")
                for key, value in service.get("values", {}).items():
                    lines.append(f"  - {key}: {value}")
            sections.append("SERVICES:\n" + "\n".join(lines))
        return "\n\n".join(sections)


@dataclass(frozen=True)
class ContextSaveResult:
    snapshot: ContextSnapshot
    fingerprint: str
    changed: bool
    text: str


class ContextSaver:
    """Build compact durable context and short-circuit unchanged saves."""
    def __init__(self, *, last_fingerprint: str | None = None) -> None:
        self.last_fingerprint = last_fingerprint
        self.last_snapshot: ContextSnapshot | None = None

    def build(self, state: Mapping[str, object]) -> ContextSnapshot:
        if not isinstance(state, Mapping):
            raise TypeError("state must be a mapping")

        def values(name: str) -> tuple[str, ...]:
            raw = state.get(name, ())
            if isinstance(raw, str):
                raw = (raw,)
            if not isinstance(raw, (list, tuple, set, frozenset)):
                return ()
            return _dedupe(raw)

        return ContextSnapshot(
            project=_clean(state.get("project", "")),
            current_task=_clean(state.get("current_task", "")),
            decisions=values("decisions"),
            bugs=values("bugs"),
            fixes=values("fixes"),
            files=values("files"),
            commands=values("commands"),
            tests=values("tests"),
            services=_normalize_services(state.get("services", ())),
            next_steps=values("next_steps"),
        )

    def save(self, state: Mapping[str, object]) -> ContextSaveResult:
        snapshot = self.build(state)
        fingerprint = snapshot.fingerprint()
        changed = fingerprint != self.last_fingerprint
        self.last_fingerprint = fingerprint
        self.last_snapshot = snapshot
        return ContextSaveResult(snapshot, fingerprint, changed, snapshot.to_text())

    def save_if_changed(self, state: Mapping[str, object]) -> ContextSaveResult | None:
        snapshot = self.build(state)
        fingerprint = snapshot.fingerprint()
        if fingerprint == self.last_fingerprint:
            return None
        self.last_fingerprint = fingerprint
        self.last_snapshot = snapshot
        return ContextSaveResult(snapshot, fingerprint, True, snapshot.to_text())

    def reset(self) -> None:
        self.last_fingerprint = None
        self.last_snapshot = None
