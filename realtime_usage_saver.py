"""Realtime, idempotent usage-saving layer built on the token compaction engine.

This module deliberately keeps orchestration separate from the core compactor. It
accepts streaming chunks, emits compacted output incrementally, and remembers the
fingerprint of the last completed input so identical work can be treated as a
no-op by callers that persist the fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Iterator

from ai_token_saver import CompactionResult, RedactionMode, RealtimeCompactor


@dataclass(frozen=True)
class RealtimeUsageResult:
    """Final realtime usage-saving result."""

    fingerprint: str
    result: CompactionResult
    changed: bool


def state_fingerprint(text: str, *, redaction_mode: RedactionMode = "common", aggressive: bool = False) -> str:
    """Return a stable fingerprint for a saver input and its relevant options."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    payload = f"v1\0{redaction_mode}\0{int(aggressive)}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class RealtimeUsageSaver:
    """Incremental usage saver with an optional persisted last fingerprint.

    The class itself does not perform I/O. A host can persist ``last_fingerprint``
    in a JSON/state file, database, or other durable store between invocations.
    """

    def __init__(
        self,
        *,
        redact_secrets: bool = True,
        redaction_mode: RedactionMode | None = None,
        aggressive: bool = False,
        last_fingerprint: str | None = None,
    ) -> None:
        self.redact_secrets = redact_secrets
        self.redaction_mode = redaction_mode
        self.aggressive = aggressive
        self.last_fingerprint = last_fingerprint
        self._compactor: RealtimeCompactor | None = None
        self._current_fingerprint: str | None = None

    def start(self) -> None:
        self._compactor = RealtimeCompactor(
            redact_secrets=self.redact_secrets,
            redaction_mode=self.redaction_mode,
            aggressive=self.aggressive,
        )
        self._current_fingerprint = None

    def feed(self, chunk: str) -> str:
        if self._compactor is None:
            self.start()
        assert self._compactor is not None
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")
        return self._compactor.feed(chunk)

    def finish(self) -> RealtimeUsageResult:
        if self._compactor is None:
            self.start()
        assert self._compactor is not None
        self._compactor.finish()
        original = self._compactor.original
        mode = self._compactor.redaction_mode
        fingerprint = state_fingerprint(original, redaction_mode=mode, aggressive=self.aggressive)
        changed = fingerprint != self.last_fingerprint
        self.last_fingerprint = fingerprint
        return RealtimeUsageResult(fingerprint, self._compactor.result(), changed)

    def process(self, chunks: Iterable[str]) -> Iterator[str]:
        """Yield realtime output for a single stream, then finalize the state."""
        self.start()
        for chunk in chunks:
            emitted = self.feed(chunk)
            if emitted:
                yield emitted
        final = self.finish()
        # ``finish`` returns no data here because the compactor was finalized above;
        # callers receive all emitted data through ``feed``. The final result is
        # available as ``self.last_result`` after ``finish``.
        self.last_result = final

    @property
    def result(self) -> RealtimeUsageResult | None:
        return getattr(self, "last_result", None)

    def is_same_input(self, text: str) -> bool:
        mode = self.redaction_mode or ("common" if self.redact_secrets else "off")
        return state_fingerprint(text, redaction_mode=mode, aggressive=self.aggressive) == self.last_fingerprint
