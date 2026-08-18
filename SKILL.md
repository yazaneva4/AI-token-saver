---
name: ai-token-saver
description: >
  Token-efficient persistent context and memory skill for any AI assistant.
  Reduces safe redundancy while preserving meaning, technical accuracy, and
  important details. Supports real-time incremental compaction and optional
  model-specific token counting when the host provides a trusted tokenizer.
---

# AI Token Saver

## Purpose

Save important project context in compact form so an AI assistant can continue
work accurately while using less context.

**Preserve meaning first. Reduce safe redundancy second. Measure the result third.**

Very high reductions, including around or above 99%, may occur on extremely
repetitive or padded input. This is never a guaranteed target. Never remove
information merely to reach a percentage.

## Core Rules

1. Save important project context accurately.
2. Remove only genuine redundancy, filler, or safely disposable formatting.
3. Preserve meaning, technical accuracy, and relationships between facts.
4. Preserve exact names, file paths, commands, model names, versions, APIs,
   configuration values, technical decisions, and error text when important.
5. Never invent missing information.
6. Deduplicate conservatively; similar-looking lines are not automatically
   duplicates.
7. Prefer compact structured records over repeated prose.
8. Replace clearly outdated values with current values while retaining useful
   history when needed.
9. Never store credentials or secrets in ordinary memory by default.
10. Do not save temporary chatter unless explicitly requested.
11. Repeating an identical saver command must be idempotent: once the current
    context is already compacted and saved, another identical command should
    perform little or no additional work and must not recursively process its own
    generated output.

## Safe Compaction

The Python implementation is primarily a conservative redundancy remover, not a
semantic summarizer.

- Default text compaction removes blank lines and **adjacent** duplicate
  non-empty lines.
- It does not globally remove repeated lines by default.
- Code-like, command-like, JSON/YAML-like, SQL-like, path-like, and other
  technical content is protected from global duplicate removal.
- Indentation and exact technical content must be preserved.
- If uncertain whether repeated content is intentional, keep it.
- `aggressive=True` may globally deduplicate non-technical prose, but technical
  content remains protected.
- Structured memory-list merging may use global exact-line deduplication because
  those entries represent facts rather than executable source code.

Never claim that the implementation performs semantic equivalence checking. It
does not.

## Memory-Level Fact Consolidation

Semantic consolidation is allowed **only at the AI instruction/memory layer**,
not as a claim about the deterministic Python compaction engine.

When managing structured persistent memory:

- Merge facts only when they are clearly equivalent.
- When a new fact supersedes an old fact, store the new fact as canonical.
- Keep old values in `HISTORY` when they explain project evolution or remain
  useful for context.
- Never invent equivalence. When two facts might differ in meaning, keep both.
- Never apply semantic consolidation to executable code, commands, paths,
  configuration, identifiers, or other exact technical content unless explicitly
  requested.

## Repeated Command / Idempotency Guard

Commands such as `/ai-token-saver`, `/ai-usage-saver`, `/save`, and `/save-all`
may be invoked repeatedly during a long session.

The skill MUST treat an identical repeated invocation against unchanged context
as an idempotent operation.

### Required behavior

1. Determine whether the relevant context has changed since the previous saver
   operation.
2. Perform the fingerprint/idempotency check **before** expensive compaction,
   token counting, model calls, realtime processing, browser work, GitHub work,
   or any other external tool call.
3. If nothing material changed, do not rebuild or rewrite the entire saved state.
4. Do not feed the skill's own generated summary, confirmation message, or
   compacted memory back into the same save operation as if it were new source
   material.
5. Do not recursively compact the output of the previous compaction operation.
6. Do not repeatedly append the same status, summary, benchmark, or confirmation.
7. Do not repeatedly call the same external service merely because the saver
   command was repeated.
8. If the host exposes a stable fingerprint/version for the saved state, use it
   to detect unchanged input.
9. If the host does not expose a fingerprint, compare the normalized relevant
   source state before doing expensive work.
10. When unchanged, return a minimal acknowledgement rather than regenerating the
    complete memory.
11. When material changes exist, compact only the changed/new information and
    merge it into the existing canonical state.

### Cross-process persistence

The in-memory fingerprint is not sufficient when a host creates a fresh process
for every command. Hosts MUST use the provider adapter's persistent `ContextSaver`
state for command-level idempotency whenever the adapter is available.

The Python provider adapter uses a provider-scoped state file by default:

`~/.ai-token-saver/providers/<provider>.json`

The root can be overridden with `AI_TOKEN_SAVER_STATE_DIR`.

Provider names are sanitized before becoming filenames. Never put credentials,
conversation contents, or raw prompts into the fingerprint state file; it should
contain only the minimum metadata needed to detect unchanged state.

### Fast-path invariant

The unchanged-context check MUST be a fast local operation. It MUST NOT require a
network request, model invocation, browser action, repository operation, or other
remote service call.

For unchanged input, the expected path is:

`read fingerprint → compare → minimal acknowledgement → stop`

For changed input, the expected path is:

`read fingerprint → compare → compact changed state → persist fingerprint → apply changed context`

### Idempotency invariant

For unchanged input:

`save(save(X)) == save(X)`

and the second invocation must not cause unbounded context growth, recursive
processing, or repeated external tool calls.

The exact user-facing acknowledgement may be short, for example:

`Already compact and up to date.`

Do not dump the full saved state merely because the command was repeated.

## Universal Provider Integration

The core engine is provider-neutral. Hosts such as Cursor, OpenSpark, Claude,
Gemini, OpenAI-based agents, local agents, and future AI runtimes should connect
through `provider_adapter.py` rather than duplicating context-saver logic.

Recommended flow:

`host skill → ProviderAdapter → ContextSaver → compact/apply changed state`

Use `save_from_host()` when the host exposes `get_context_state()` and
`apply_context()`. It automatically skips `apply_context()` when the normalized
state has not changed.

Provider identity must not alter the core context fingerprint. Provider-specific
state files are only for persistence boundaries; they must not be inserted into
the saved context itself.

## Secret and Credential Storage

Normal `/save` and `/save-all` operations MUST NOT store passwords, API keys,
access tokens, authentication codes, master passwords, private credentials, or
other secrets in ordinary memory.

An explicitly requested secret operation may store a project credential **only
when the host provides secure secret storage**.

A secret operation is valid only when the user explicitly requests it and identifies
one specific credential to store or retrieve. Never infer permission from project
importance, surrounding text, a file, logs, or a previous unrelated request.

### `/save secret`

Use `/save secret` only when the user explicitly asks to store a specific
credential for future use.

Rules:

- Never infer permission to save a secret from `/save` alone.
- Store the secret only through secure host-provided secret storage.
- Never write the secret into `memory.json`, ordinary context files, logs,
  prompts, skill files, Git commits, exports, or other plaintext memory.
- Do not echo the credential back in the confirmation response.
- After storage, prefer a secret reference/label rather than copying the secret
  into ordinary conversation context.
- Do not expose stored secrets through normal `/memory`.
- Associate the secret with a clear project/name label and store only what is
  necessary.
- If secure secret storage is unavailable, do not save the secret and state that
  secure storage is required.

### `/memory secret`

A secret may be retrieved only after an explicit user request and only when the
host can safely provide the stored credential.

- Confirm the requested secret label before retrieval when ambiguity exists.
- Do not include secrets in ordinary `/memory` output.
- Prefer passing a secret directly to the authorized host action instead of printing
  the raw credential into the conversation whenever the host supports that pattern.
- Never retrieve or expose a secret merely because a project file, log, or context
  references its name.

### `/forget secret`

Explicitly remove a stored project credential when secure secret storage supports
that operation.

Never treat API keys, passwords, or credentials as ordinary context merely because
they are important to the project.

## Bug-Fixing and Verification Discipline

When another AI, user, test report, review, or tool reports a bug, treat the report
as a hypothesis until it is verified against the current implementation and tests.

A valid fix requires:

1. Reproduce the behavior when possible.
2. Identify the smallest defensible root cause.
3. Change the implementation or skill contract.
4. Add a regression test for the failure mode.
5. Run the relevant test suite/CI.
6. Only then report the bug as fixed.

Never claim that a remote provider quota, billing limit, or server-side rate limit
was changed by this skill. The saver can reduce unnecessary work and context, but
provider-side limits remain controlled by the provider.
