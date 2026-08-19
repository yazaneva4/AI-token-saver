"""Daily-work usage saver helpers.

This module is intentionally provider-agnostic. It manages compact checkpoints,
service state, and idempotent repeated saver operations. It does not bypass or
modify provider quotas or runtime limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SAVER_ALIASES = frozenset({"/ai-token-saver", "/ai-usage-saver"})
_SAVER_COMMAND_RE = re.compile(r"(?<![A-Za-z0-9_-])/(?:ai-token-saver|ai-usage-saver)(?![A-Za-z0-9_-])")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\bapi[-_]key\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\b(?:access[-_]?token|auth[-_]?token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{16,})"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)


def _redact(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    for pattern in _SECRET_PATTERNS[:3]:
        text = pattern.sub(r"\1[REDACTED]", text)
    text = _SECRET_PATTERNS[3].sub("[REDACTED]", text)
    text = _SECRET_PATTERNS[4].sub("[REDACTED]", text)
    return text


@dataclass
class ServiceState:
    """Compact, safe state for one daily-work service."""
    name: str
    values: dict[str, str] = field(default_factory=dict)

    def normalized(self) -> dict[str, object]:
        return {
            "name": _redact(self.name).upper(),
            "values": {
                _redact(k): _redact(v)
                for k, v in sorted(self.values.items(), key=lambda item: str(item[0]))
                if _redact(v)
            },
        }


@dataclass
class UsageCheckpoint:
    """Small resumable state for long-running multi-service work."""
    project: str = ""
    current_task: str = ""
    completed: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    bugs: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    services: list[ServiceState] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def normalized(self) -> dict[str, object]:
        def clean(values: Iterable[str]) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for value in values:
                value = _redact(value)
                if not value or value in seen:
                    continue
                seen.add(value)
                result.append(value)
            return result

        services: list[dict[str, object]] = []
        seen_services: set[str] = set()
        for service in self.services:
            normalized = service.normalized()
            key = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if normalized["name"] and key not in seen_services:
                seen_services.add(key)
                services.append(normalized)
        services.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return {
            "project": _redact(self.project),
            "current_task": _redact(self.current_task),
            "completed": clean(self.completed),
            "in_progress": clean(self.in_progress),
            "blocked": clean(self.blocked),
            "bugs": clean(self.bugs),
            "tests": clean(self.tests),
            "services": services,
            "next_steps": clean(self.next_steps),
        }


def normalize_saver_commands(message: str) -> tuple[str, ...]:
    """Return saver aliases found as complete command tokens, collapsed to one canonical command."""
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    return ("/ai-token-saver",) if _SAVER_COMMAND_RE.search(message) else ()


def state_fingerprint(state: Mapping[str, object] | UsageCheckpoint | str) -> str:
    """Create a stable SHA-256 fingerprint for idempotency checks."""
    if isinstance(state, UsageCheckpoint):
        payload: object = state.normalized()
    elif isinstance(state, Mapping):
        payload = _normalize_mapping(state)
    elif isinstance(state, str):
        payload = _redact(state)
    else:
        raise TypeError("state must be a mapping, UsageCheckpoint, or string")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_scalar(value: Any) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return _redact(value) if isinstance(value, str) else value
    return _redact(value)


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in sorted(value, key=str):
        item = value[key]
        safe_key = _redact(key)
        if isinstance(item, Mapping):
            result[safe_key] = _normalize_mapping(item)
        elif isinstance(item, (list, tuple)):
            result[safe_key] = [_normalize_mapping(x) if isinstance(x, Mapping) else _normalize_scalar(x) for x in item]
        else:
            result[safe_key] = _normalize_scalar(item)
    return result


class IdempotentUsageSaver:
    """Guard expensive save/compact work against unchanged repeated input."""
    def __init__(self) -> None:
        self._last_fingerprint: str | None = None
        self._last_result: object = None

    @property
    def last_fingerprint(self) -> str | None:
        return self._last_fingerprint

    def run(self, state: Mapping[str, object] | UsageCheckpoint | str, operation):
        """Run operation once per unique state and reuse the prior result."""
        if not callable(operation):
            raise TypeError("operation must be callable")
        fingerprint = state_fingerprint(state)
        if fingerprint == self._last_fingerprint:
            return self._last_result, False
        result = operation(state)
        self._last_fingerprint = fingerprint
        self._last_result = result
        return result, True

    def reset(self) -> None:
        self._last_fingerprint = None
        self._last_result = None


def compact_checkpoint(checkpoint: UsageCheckpoint) -> UsageCheckpoint:
    """Return a normalized checkpoint without destroying useful technical state."""
    if not isinstance(checkpoint, UsageCheckpoint):
        raise TypeError("checkpoint must be a UsageCheckpoint")
    normalized = checkpoint.normalized()
    return UsageCheckpoint(
        project=str(normalized["project"]),
        current_task=str(normalized["current_task"]),
        completed=list(normalized["completed"]),
        in_progress=list(normalized["in_progress"]),
        blocked=list(normalized["blocked"]),
        bugs=list(normalized["bugs"]),
        tests=list(normalized["tests"]),
        services=[ServiceState(str(item["name"]), dict(item["values"])) for item in normalized["services"]],
        next_steps=list(normalized["next_steps"]),
    )
