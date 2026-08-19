"""Realtime, idempotent usage-saving layer built on the token compaction engine.

This module deliberately keeps orchestration separate from the core compactor. It
accepts streaming chunks, emits compacted output incrementally, and persists the
fingerprint of the last completed input so identical work can be treated as a
no-op across separate CLI/skill invocations.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
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
    """Incremental usage saver with optional durable, cross-process idempotency."""

    def __init__(
        self,
        *,
        redact_secrets: bool = True,
        redaction_mode: RedactionMode | None = None,
        aggressive: bool = False,
        last_fingerprint: str | None = None,
        state_path: str | os.PathLike[str] | None = None,
        lock_timeout: float = 5.0,
    ) -> None:
        if lock_timeout <= 0:
            raise ValueError("lock_timeout must be positive")
        self.redact_secrets = redact_secrets
        self.redaction_mode = redaction_mode
        self.aggressive = aggressive
        self.state_path = Path(state_path).expanduser() if state_path else None
        self.lock_timeout = float(lock_timeout)
        self.last_fingerprint = last_fingerprint if last_fingerprint is not None else self._load_fingerprint()
        self._compactor: RealtimeCompactor | None = None
        self._finished = False
        self.last_result: RealtimeUsageResult | None = None

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

    def _refresh_persisted_fingerprint(self) -> str | None:
        if self.state_path is None:
            return self.last_fingerprint
        self.last_fingerprint = self._load_fingerprint()
        return self.last_fingerprint

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
                    raise TimeoutError(f"timed out waiting for realtime saver lock: {lock_path}")
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

    def start(self) -> None:
        """Start a new stream without discarding or staling the persisted fingerprint."""
        self._refresh_persisted_fingerprint()
        self._compactor = RealtimeCompactor(
            redact_secrets=self.redact_secrets,
            redaction_mode=self.redaction_mode,
            aggressive=self.aggressive,
        )
        self._finished = False
        self.last_result = None

    def feed(self, chunk: str) -> str:
        """Feed one chunk and return any output safe to emit immediately."""
        if self._compactor is None:
            self.start()
        if self._finished:
            raise RuntimeError("stream is already finished; call start() before feeding more data")
        assert self._compactor is not None
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")
        return self._compactor.feed(chunk)

    def finish(self) -> tuple[str, RealtimeUsageResult]:
        """Flush final output and atomically claim/persist the completed fingerprint."""
        if self._compactor is None:
            self.start()
        if self._finished:
            raise RuntimeError("stream is already finished; call start() before finishing again")
        assert self._compactor is not None
        final_output = self._compactor.finish()
        original = self._compactor.original
        mode = self._compactor.redaction_mode
        fingerprint = state_fingerprint(original, redaction_mode=mode, aggressive=self.aggressive)
        fd = self._acquire_lock()
        try:
            previous = self._load_fingerprint() if self.state_path else self.last_fingerprint
            changed = fingerprint != previous
            self._persist_fingerprint(fingerprint)
            self.last_fingerprint = fingerprint
            result = RealtimeUsageResult(fingerprint, self._compactor.result(), changed)
            self.last_result = result
            self._finished = True
            return final_output, result
        finally:
            self._release_lock(fd)

    def process(self, chunks: Iterable[str]) -> Iterator[str]:
        """Yield realtime output for a single stream, including final buffered data."""
        self.start()
        for chunk in chunks:
            emitted = self.feed(chunk)
            if emitted:
                yield emitted
        final_output, _ = self.finish()
        if final_output:
            yield final_output

    @property
    def result(self) -> RealtimeUsageResult | None:
        return self.last_result

    def is_same_input(self, text: str) -> bool:
        mode = self.redaction_mode or ("common" if self.redact_secrets else "off")
        previous = self._refresh_persisted_fingerprint()
        return state_fingerprint(text, redaction_mode=mode, aggressive=self.aggressive) == previous
