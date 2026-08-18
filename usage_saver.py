"""Daily-work usage saver helpers.

This module is intentionally provider-agnostic. It manages compact checkpoints,
service state, and idempotent repeated saver operations. It does not bypass or
modify provider quotas or runtime limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable, Mapping


SAVER_ALIASES = frozenset({"/ai-token-saver", "/ai-usage-saver"})


@dataclass
class ServiceState:
    """Compact, safe state for one daily-work service."""

    name: str
    values: dict[str, str] = field(default_factory=dict)

    def normalized(self) -> dict[str, object]:
        return {
            "name": self.name.strip().upper(),
            "values": {
                str(k): str(v).strip()
                for k, v in sorted(self.values.items(), key=lambda item: str(item[0]))
                if str(v).strip()
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
                value = str(value).strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                result.append(value)
            return result

        return {
            "project": self.project.strip(),
            "current_task": self.current_task.strip(),
            "completed": clean(self.completed),
            "in_progress": clean(self.in_progress),
            "blocked": clean(self.blocked),
            "bugs": clean(self.bugs),
            "tests": clean(self.tests),
            "services": [service.normalized() for service in self.services],
            "next_steps": clean(self.next_steps),
        }


def normalize_saver_commands(message: str) -> tuple[str, ...]:
    """Return saver aliases found in a message, with aliases collapsed.

    `/ai-token-saver /ai-usage-saver` therefore represents exactly one operation.
    """

    if not isinstance(message, str):
        raise TypeError("message must be a string")
    found = [alias for alias in SAVER_ALIASES if alias in message]
    return ("/ai-token-saver",) if found else ()


def state_fingerprint(state: Mapping[str, object] | UsageCheckpoint | str) -> str:
    """Create a stable SHA-256 fingerprint for idempotency checks."""

    if isinstance(state, UsageCheckpoint):
        payload: object = state.normalized()
    elif isinstance(state, Mapping):
        payload = _normalize_mapping(state)
    elif isinstance(state, str):
        payload = state
    else:
        raise TypeError("state must be a mapping, UsageCheckpoint, or string")

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in sorted(value, key=str):
        item = value[key]
        if isinstance(item, Mapping):
            result[str(key)] = _normalize_mapping(item)
        elif isinstance(item, (list, tuple)):
            result[str(key)] = [
                _normalize_mapping(x) if isinstance(x, Mapping) else str(x).strip()
                for x in item
            ]
        else:
            result[str(key)] = str(item).strip()
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
        """Run `operation` once per unique state and reuse the prior result.

        The operation is called with the original state only when the fingerprint
        changes. The returned object is reused for an unchanged repeated state.
        """

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

    normalized = checkpoint.normalized()
    return UsageCheckpoint(
        project=str(normalized["project"]),
        current_task=str(normalized["current_task"]),
        completed=list(normalized["completed"]),
        in_progress=list(normalized["in_progress"]),
        blocked=list(normalized["blocked"]),
        bugs=list(normalized["bugs"]),
        tests=list(normalized["tests"]),
        services=[
            ServiceState(str(item["name"]), dict(item["values"]))
            for item in normalized["services"]
        ],
        next_steps=list(normalized["next_steps"]),
    )
