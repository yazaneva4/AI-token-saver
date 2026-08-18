"""Provider-neutral integration layer for AI Token Saver."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from context_saver import ContextSaveResult, ContextSaver


class ContextProvider(Protocol):
    def get_context_state(self) -> Mapping[str, Any]: ...
    def apply_context(self, text: str, *, fingerprint: str) -> None: ...


@dataclass(frozen=True)
class ProviderSaveResult:
    provider: str
    changed: bool
    fingerprint: str
    text: str


def _provider_state_path(provider: str) -> Path:
    root = Path(os.environ.get("AI_TOKEN_SAVER_STATE_DIR", "~/.ai-token-saver/providers")).expanduser()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", provider.strip()) or "provider"
    return root / f"{safe}.json"


class ProviderAdapter:
    """Connect any host/provider to ContextSaver with cross-invocation deduplication."""
    def __init__(self, provider: str, saver: ContextSaver | None = None) -> None:
        provider = provider.strip()
        if not provider:
            raise ValueError("provider must not be empty")
        self.provider = provider
        self.saver = saver or ContextSaver(state_path=_provider_state_path(provider))

    def save(self, state: Mapping[str, Any]) -> ProviderSaveResult:
        return self._result(self.saver.save(state))

    def save_if_changed(self, state: Mapping[str, Any]) -> ProviderSaveResult | None:
        result = self.saver.save_if_changed(state)
        return None if result is None else self._result(result)

    def save_from_host(self, host: ContextProvider) -> ProviderSaveResult | None:
        result = self.save_if_changed(host.get_context_state())
        if result is not None:
            host.apply_context(result.text, fingerprint=result.fingerprint)
        return result

    def _result(self, result: ContextSaveResult) -> ProviderSaveResult:
        return ProviderSaveResult(self.provider, result.changed, result.fingerprint, result.text)


def create_adapter(provider: str, *, saver: ContextSaver | None = None) -> ProviderAdapter:
    return ProviderAdapter(provider, saver=saver)
