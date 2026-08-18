# Provider Adapter for AI Token Saver

This is the provider-facing integration contract for the `ai-token-saver` skill.

The core skill remains provider-neutral. A host installs or wires this adapter into its own skill/agent system; it is **not** an automatic installation into every AI provider.

## Supported host categories

The adapter is designed for any host that can call Python code, expose a skill/tool, load a context file, or connect through an API/MCP-style bridge, including:

- Cursor and other coding agents
- OpenSpark and other custom agents
- Claude-style skill systems
- Gemini-based agents
- OpenAI-based agents
- Local/self-hosted agents
- Future providers

## Required flow

`host/agent -> provider adapter -> ContextSaver -> Token Saver / Realtime Saver`

The adapter must pass only host-supplied state. It must not invent provider telemetry or claim access to hidden context/usage state.

## Install into a host skill

A host skill should:

1. Load the provider adapter contract.
2. Map the host's current project/context state into the normalized context schema.
3. Call `ContextSaver.save_if_changed()` for ordinary repeated saves.
4. Send only changed context to the token/realtime saver.
5. Store the returned fingerprint with the host's durable state when persistence is available.
6. Keep provider-specific credentials outside ordinary context and use secure secret storage.

## Provider-specific behavior

A provider adapter may supply an official tokenizer or token counter when the provider exposes one. Otherwise it must use the engine's approximate measurement and label it as approximate.

A provider adapter must never bypass, reset, remove, or claim to control provider usage limits.

## Idempotency

If two provider aliases invoke the same saver operation on unchanged state, the adapter must collapse them into one operation. For example, if `/ai-token-saver` and `/ai-usage-saver` appear in the same request, they represent one save operation, not two.

For unchanged normalized state, the adapter should return a minimal no-op result instead of rebuilding the entire context.
