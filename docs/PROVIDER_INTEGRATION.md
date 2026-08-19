# Universal Provider Integration

AI Token Saver has a provider-neutral core. It does not require a specific model,
API, SDK, or application.

## Architecture

```text
Provider / Agent / IDE
        |
        v
ProviderAdapter
        |
        v
ContextSaver
        |
        +--> Token Saver
        +--> Realtime Saver
        +--> Secret protection
```

The adapter translates the host's state into the common context-state mapping and
applies a changed compact context back to the host. The provider adapter uses a
transactional apply path: the persistent fingerprint is committed only after the
host accepts the changed context.

## Supported host styles

The adapter is intentionally name-agnostic. It can be used by:

- Cursor and other coding IDE agents
- OpenSpark and custom agents
- Claude-style assistants
- Gemini-based assistants
- OpenAI-based assistants
- local models and local agents
- self-hosted agent runtimes
- future providers without changing the core engine

"Supported" here means the core adapter can integrate with the host. A concrete
host still needs a small native integration that knows how that host stores and
loads context.

## Minimal host contract

A host integration provides:

- `get_context_state()` -> a mapping containing fields such as `project`,
  `current_task`, `decisions`, `bugs`, `fixes`, `files`, `commands`, `tests`,
  `services`, and `next_steps`.
- `apply_context(text, fingerprint=...)` -> stores the compact context using the
  host's own supported mechanism and raises an error if the application fails.

Use `ProviderAdapter.save_from_host(host)` to save only when the normalized state
changed. The adapter keeps the idempotency lock through the host apply and only
persists the new fingerprint after successful application.

## Fast-path requirement

When a host provides local code execution, the host integration should perform the
persistent fingerprint check before any model, tokenizer, browser, repository, or
network operation. The saver should never call another AI model merely to decide
whether an unchanged state needs saving.

The core engine cannot eliminate the provider's own cost for executing the skill
instruction. It can only prevent additional work caused by the save operation.

## Provider-specific token counting

The universal adapter does not guess token counts. If a host has an official
model tokenizer or trusted counter, pass it through the existing measurement
interfaces. Otherwise measurements must remain labeled approximate.

## Security

The adapter must never place credentials into ordinary context. Providers that
need credentials must use their secure secret facilities separately.

## Important limitation

The adapter does not magically install itself into every provider. Each host needs
a thin native integration using its own extension/skill/plugin/MCP/API mechanism.
The core remains provider-neutral so those integrations do not fork the saver
logic.
