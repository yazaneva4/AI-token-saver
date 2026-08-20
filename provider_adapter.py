"""Provider-neutral integration layer for AI Token Saver."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


@dataclass(frozen=True)
class PreparedProviderRequest:
    """A compact provider request prepared before the provider is called.

    Preparation never claims the request succeeded and never persists the
    fingerprint. Call ``ProviderAdapter.save_after_response`` only after the
    provider successfully accepts the request/response cycle.
    """
    provider: str
    request: str
    context: str
    fingerprint: str

    def render(self) -> str:
        if not self.context:
            return self.request
        if not self.request:
            return self.context
        return f"{self.context}\n\nUSER REQUEST:\n{self.request}"


def _provider_state_path(provider: str) -> Path:
    root = Path(os.environ.get("AI_TOKEN_SAVER_STATE_DIR", "~/.ai-token-saver/providers")).expanduser()
    normalized = provider.strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized) or "provider"
    # Keep the readable slug, but add a digest so distinct provider names such
    # as ``foo/bar`` and ``foo_bar`` can never share persistent state.
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return root / f"{safe}-{digest}.json"


class ProviderAdapter:
    """Connect any host/provider to ContextSaver with cross-invocation deduplication."""

    def __init__(
        self,
        provider: str,
        saver: ContextSaver | None = None,
        *,
        state_path: str | os.PathLike[str] | None = None,
    ) -> None:
        provider = provider.strip()
        if not provider:
            raise ValueError("provider must not be empty")
        if saver is not None and state_path is not None:
            raise ValueError("pass either saver or state_path, not both")
        self.provider = provider
        self.saver = saver or ContextSaver(
            state_path=state_path if state_path is not None else _provider_state_path(provider)
        )

    def save(self, state: Mapping[str, Any]) -> ProviderSaveResult:
        return self._result(self.saver.save(state))

    def save_if_changed(self, state: Mapping[str, Any]) -> ProviderSaveResult | None:
        result = self.saver.save_if_changed(state)
        return None if result is None else self._result(result)

    def prepare_request(self, state: Mapping[str, Any], request: str) -> PreparedProviderRequest:
        """Compact context for the next provider request without persisting it.

        This is intentionally a pre-request operation: it does not call a
        provider, does not mutate a running generation, and does not claim the
        request succeeded. Persist the checkpoint after a successful cycle with
        ``save_after_response``.
        """
        if not isinstance(request, str):
            raise TypeError("request must be a string")
        snapshot = self.saver.build(state)
        return PreparedProviderRequest(
            provider=self.provider,
            request=request,
            context=snapshot.to_text(),
            fingerprint=snapshot.fingerprint(),
        )

    def save_after_response(self, state: Mapping[str, Any]) -> ProviderSaveResult | None:
        """Persist useful state only after the provider cycle has succeeded."""
        return self.save_if_changed(state)

    def save_from_host(self, host: ContextProvider) -> ProviderSaveResult | None:
        # Keep the idempotency lock through the host apply and persist only after
        # the host confirms success. A failed apply therefore cannot poison state.
        result = self.saver.save_if_changed_and_apply(
            host.get_context_state(),
            lambda text, fingerprint: host.apply_context(text, fingerprint=fingerprint),
        )
        return None if result is None else self._result(result)

    def _result(self, result: ContextSaveResult) -> ProviderSaveResult:
        return ProviderSaveResult(self.provider, result.changed, result.fingerprint, result.text)


def create_adapter(
    provider: str,
    *,
    saver: ContextSaver | None = None,
    state_path: str | os.PathLike[str] | None = None,
) -> ProviderAdapter:
    return ProviderAdapter(provider, saver=saver, state_path=state_path)
