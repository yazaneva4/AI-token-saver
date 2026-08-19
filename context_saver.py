"""Durable, conservative context-state saver for long-running AI work."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Iterable, Mapping

PRESERVED_FIELDS = ("project", "current_task", "decisions", "bugs", "fixes", "files", "commands", "tests", "services", "next_steps")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\bapi[-_]key\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\b(?:access[-_]?token|auth[-_]?token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{16,})"),
)


def _redact(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def _clean(value: object) -> str:
    return _redact(value)


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
        values = {_clean(key): _clean(val) for key, val in sorted(raw_values.items(), key=lambda pair: str(pair[0])) if _clean(val)}
        normalized = {"name": name, "values": values}
        key = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    result.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return tuple(result)


@dataclass(frozen=True)
class ContextSnapshot:
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
        return {"project": self.project, "current_task": self.current_task, "decisions": list(self.decisions), "bugs": list(self.bugs), "fixes": list(self.fixes), "files": list(self.files), "commands": list(self.commands), "tests": list(self.tests), "services": [dict(item) for item in self.services], "next_steps": list(self.next_steps)}

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_text(self) -> str:
        sections: list[str] = []
        for title, value in (("PROJECT", self.project), ("CURRENT TASK", self.current_task)):
            if value:
                sections.append(f"{title}:\n{value}")
        for title, values in (("DECISIONS", self.decisions), ("BUGS", self.bugs), ("FIXES", self.fixes), ("FILES", self.files), ("COMMANDS", self.commands), ("TESTS", self.tests), ("NEXT STEPS", self.next_steps)):
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
    """Build compact durable context and short-circuit unchanged saves.

    ``state_path`` makes duplicate detection survive separate CLI/skill
    invocations. The lock is acquired before the fingerprint is compared and
    claimed, giving each identical state a single winner across processes.
    """
    def __init__(self, *, last_fingerprint: str | None = None, state_path: str | os.PathLike[str] | None = None, lock_timeout: float = 5.0) -> None:
        if lock_timeout <= 0:
            raise ValueError("lock_timeout must be positive")
        self.state_path = Path(state_path).expanduser() if state_path else None
        self.lock_timeout = float(lock_timeout)
        self.last_fingerprint = last_fingerprint if last_fingerprint is not None else self._load_fingerprint()
        self.last_snapshot: ContextSnapshot | None = None

    @property
    def _lock_path(self) -> Path | None:
        return self.state_path.with_suffix(self.state_path.suffix + ".lock") if self.state_path else None

    def _load_fingerprint(self) -> str | None:
        if self.state_path is None or not self.state_path.is_file():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            value = data.get("fingerprint") if isinstance(data, dict) else None
            return value if isinstance(value, str) and value else None
        except (OSError, ValueError, TypeError):
            return None

    def _persist_fingerprint(self, fingerprint: str) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps({"fingerprint": fingerprint}, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.state_path)

    def _acquire_lock(self) -> int | None:
        lock_path = self._lock_path
        if lock_path is None:
            return None
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > self.lock_timeout * 2:
                        lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for context lock: {lock_path}")
                time.sleep(0.01)

    def _release_lock(self, fd: int | None) -> None:
        lock_path = self._lock_path
        if fd is not None:
            os.close(fd)
        if lock_path is not None:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def build(self, state: Mapping[str, object]) -> ContextSnapshot:
        if not isinstance(state, Mapping):
            raise TypeError("state must be a mapping")
        def values(name: str) -> tuple[str, ...]:
            raw = state.get(name, ())
            if isinstance(raw, str): raw = (raw,)
            if not isinstance(raw, (list, tuple, set, frozenset)): return ()
            return _dedupe(raw)
        return ContextSnapshot(
            project=_clean(state.get("project", "")), current_task=_clean(state.get("current_task", "")),
            decisions=values("decisions"), bugs=values("bugs"), fixes=values("fixes"), files=values("files"),
            commands=values("commands"), tests=values("tests"), services=_normalize_services(state.get("services", ())),
            next_steps=values("next_steps"),
        )

    def save(self, state: Mapping[str, object]) -> ContextSaveResult:
        snapshot = self.build(state)
        fingerprint = snapshot.fingerprint()
        fd = self._acquire_lock()
        try:
            previous = self._load_fingerprint() if self.state_path else self.last_fingerprint
            changed = fingerprint != previous
            # Only update in-memory state after durable persistence succeeds.
            self._persist_fingerprint(fingerprint)
            self.last_fingerprint = fingerprint
            self.last_snapshot = snapshot
            return ContextSaveResult(snapshot, fingerprint, changed, snapshot.to_text())
        finally:
            self._release_lock(fd)

    def save_if_changed(self, state: Mapping[str, object]) -> ContextSaveResult | None:
        return self.save_if_changed_and_apply(state)

    def save_if_changed_and_apply(
        self,
        state: Mapping[str, object],
        apply: Callable[[str, str], None] | None = None,
    ) -> ContextSaveResult | None:
        """Atomically check, optionally apply, then persist a changed snapshot.

        When ``apply`` is supplied, it runs while the idempotency lock is held and
        the fingerprint is persisted only after the host confirms the context was
        applied successfully. This prevents a failed host update from poisoning
        durable idempotency state.
        """
        snapshot = self.build(state)
        fingerprint = snapshot.fingerprint()
        fd = self._acquire_lock()
        try:
            previous = self._load_fingerprint() if self.state_path else self.last_fingerprint
            self.last_fingerprint = previous
            if fingerprint == previous:
                return None
            if apply is not None:
                apply(snapshot.to_text(), fingerprint)
            self._persist_fingerprint(fingerprint)
            self.last_fingerprint = fingerprint
            self.last_snapshot = snapshot
            return ContextSaveResult(snapshot, fingerprint, True, snapshot.to_text())
        finally:
            self._release_lock(fd)

    def reset(self) -> None:
        fd = self._acquire_lock()
        try:
            self.last_fingerprint = None
            self.last_snapshot = None
            if self.state_path:
                try: self.state_path.unlink(missing_ok=True)
                except OSError: pass
        finally:
            self._release_lock(fd)
