# Provider integration

Loaded on demand from SKILL.md.

## Universal Provider Integration

The core engine is provider-neutral. Hosts such as Cursor, OpenSpark, Claude,
Gemini, OpenAI-based agents, local agents, and future AI runtimes should connect
through `provider_adapter.py` rather than duplicating context-saver logic.

Recommended request lifecycle:

`host → ProviderAdapter.prepare_request() → provider request → successful response → ProviderAdapter.save_after_response()`

Use `prepare_request(state, request)` to compact and render the current context
**before** sending the next provider request. Preparation is local only: it does
not call the provider, does not modify an already-running generation, and does
not persist the new fingerprint before success.

After the provider successfully completes its request/response cycle, call
`save_after_response(state)` to persist the useful canonical state. Repeated
unchanged post-response saves are idempotent.

Use `save_from_host()` when the host exposes `get_context_state()` and
`apply_context()`. It automatically skips `apply_context()` when the normalized
state has not changed and persists the fingerprint only after successful host
application.

Provider identity must not alter the core context fingerprint. Provider-specific
state files are only for persistence boundaries; they must not be inserted into
the saved context itself.
