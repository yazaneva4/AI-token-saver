"""Provider-neutral integration layer for AI Token Saver.

The core saver never talks directly to a model provider. Hosts such as Cursor,
OpenSpark, chat assistants, coding agents, or custom runtimes can adapt their
native context/state representation to ContextSaver through this small interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from context_saver import ContextSaveResult, ContextSaver


class ContextProvider(Protocol):
    """Minimal host contract; providers may implement this without inheritance."""

    def get_context_state(self) -> Mapping[str, Any]: ...

    def apply_context(self, text: str, *, fingerprint: str) -> None: ...


@dataclass(frozen=True)
class ProviderSaveResult:
    provider: str
    changed: bool
    fingerprint: str
    text: str


class ProviderAdapter:
    """Connect any host/provider to the provider-agnostic ContextSaver."""

    def __init__(self, provider: str, saver: ContextSaver | None = None) -> None:
        provider = provider.strip()
        if not provider:
            raise ValueError("provider must not be empty")
        self.provider = provider
        self.saver = saver or ContextSaver()

    def save(self, state: Mapping[str, Any]) -> ProviderSaveResult:
        result = self.saver.save(state)
        return self._result(result)

    def save_if_changed(self, state: Mapping[str, Any]) -> ProviderSaveResult | None:
        result = self.saver.save_if_changed(state)
        return None if result is None else self._result(result)

    def save_from_host(self, host: ContextProvider) -> ProviderSaveResult | None:
        """Read state from a host, save it, and let the host apply changed context."""
        result = self.save_if_changed(host.get_context_state())
        if result is not None:
            host.apply_context(result.text, fingerprint=result.fingerprint)
        return result

    def _result(self, result: ContextSaveResult) -> ProviderSaveResult:
        return ProviderSaveResult(
            provider=self.provider,
            changed=result.changed,
            fingerprint=result.fingerprint,
            text=result.text,
        )


def create_adapter(provider: str, *, saver: ContextSaver | None = None) -> ProviderAdapter:
    """Create an adapter for any provider/agent name without provider lock-in."""
    return ProviderAdapter(provider, saver=saver)
