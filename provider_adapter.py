"""Provider-neutral integration layer for AI Token Saver."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from context_saver import ContextSaveResult, ContextSaver


# Output levels trade words for tokens, never meaning. Unlike telegraphic
# "caveman" speech, every level keeps grammar, exact payloads, and full warnings.
OUTPUT_LEVELS = {
    "standard": (
        "Answer directly. Be concise by default; follow the requested detail and format, "
        "preserving all necessary facts."
    ),
    "tight": (
        "Answer first in short plain sentences. No preamble, recap, or offers of more help. "
        "Keep exact code, paths, numbers, warnings, and conditions in full."
    ),
    "max": (
        "Return only the result: the code, command, value, or diff. Add one line only for a "
        "blocker, risk, or warning, written in full. No explanation unless asked. Never drop "
        "error text, security warnings, or confirmation requests."
    ),
}
OUTPUT_SAVING_INSTRUCTION = OUTPUT_LEVELS["standard"]


def output_instruction(level: str = "standard") -> str:
    try:
        return OUTPUT_LEVELS[level]
    except KeyError:
        raise ValueError(f"unknown output level {level!r}; use one of {tuple(OUTPUT_LEVELS)}") from None


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
    output_level: str = "standard"

    def render(self) -> str:
        parts = [f"OUTPUT STYLE: {output_instruction(self.output_level)}"]
        if self.context:
            parts.append(self.context)
        if self.request:
            parts.append(f"USER REQUEST:\n{self.request}" if self.context else self.request)
        return "\n\n".join(parts)


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

    def prepare_request(self, state: Mapping[str, Any], request: str,
                        output_level: str = "standard") -> PreparedProviderRequest:
        """Compact context for the next provider request without persisting it.

        This is intentionally a pre-request operation: it does not call a
        provider, does not mutate a running generation, and does not claim the
        request succeeded. Persist the checkpoint after a successful cycle with
        ``save_after_response``.
        """
        if not isinstance(request, str):
            raise TypeError("request must be a string")
        output_instruction(output_level)  # validate before doing any work
        snapshot = self.saver.build(state)
        return PreparedProviderRequest(
            provider=self.provider,
            request=request,
            context=snapshot.to_text(),
            fingerprint=snapshot.fingerprint(),
            output_level=output_level,
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
