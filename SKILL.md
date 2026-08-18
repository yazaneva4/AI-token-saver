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
2. If nothing material changed, do not rebuild or rewrite the entire saved state.
3. Do not feed the skill's own generated summary, confirmation message, or
   compacted memory back into the same save operation as if it were new source
   material.
4. Do not recursively compact the output of the previous compaction operation.
5. Do not repeatedly append the same status, summary, benchmark, or confirmation.
6. Do not repeatedly call the same external service merely because the saver
   command was repeated.
7. If the host exposes a stable fingerprint/version for the saved state, use it
   to detect unchanged input.
8. If the host does not expose a fingerprint, compare the normalized relevant
   source state before doing expensive work.
9. When unchanged, return a minimal acknowledgement rather than regenerating the
   complete memory.
10. When material changes exist, compact only the changed/new information and
    merge it into the existing canonical state.

### Idempotency invariant

For unchanged input:

`save(save(X)) == save(X)`

and the second invocation must not cause unbounded context growth, recursive
processing, or repeated external tool calls.

The exact user-facing acknowledgement may be short, for example:

`Already compact and up to date.`

Do not dump the full saved state merely because the command was repeated.

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

- Inspect the current source and relevant tests before changing code.
- Reproduce or otherwise verify the reported behavior when practical.
- Do not blindly implement a suggested fix just because it appears in a bug report.
- If the report is based on a misunderstanding of the requirements or current
  behavior, do not introduce the proposed change; explain why and keep the safer
  implementation.
- Distinguish real regressions from stale tests, stale reports, expected behavior,
  and incorrect assumptions.
- Prefer the smallest change that fixes the verified root cause.
- Preserve unrelated working behavior.
- Add or update a regression test for each verified bug when a test is appropriate.
- Run the relevant test suite after changes and inspect the actual failure output
  when tests fail.
- Do not claim a test is passing unless the test was actually run or reliable CI
  evidence is available.
- Do not claim a bug is fixed merely because code was changed.
- When multiple supported Python versions are tested by CI, verify the complete
  matrix before declaring the change stable.
- If a failure is caused by a test that contradicts the intended behavior, fix the
  test only after verifying the implementation and requirement; never weaken
  correct production behavior solely to make CI green.

## Change Scope and Skill Integrity

Do not modify `SKILL.md` as a side effect of ordinary code fixes.

- Change `SKILL.md` only when the user explicitly requests a skill/instruction
  change or when the task explicitly includes skill documentation.
- When modifying `SKILL.md`, preserve unrelated rules and make the smallest
  documentation change needed.
- Never rewrite the whole skill merely to address a code bug unless the user asks
  for a full rewrite.
- Keep implementation behavior, tests, and skill instructions consistent, but do
  not silently change one to compensate for an unrelated defect in another.

## Provider Integration

When integrating with an AI provider:

- Use the provider's official tokenizer or token-counting API when available.
- Never guess provider-specific token counts when an official counter is
  unavailable.
- Never claim to know a user's remaining usage quota unless the provider exposes
  it through an available interface.
- Never attempt to bypass, reset, or remove provider usage limits.
- Keep provider-specific integrations separate from the provider-agnostic core.
- Do not assume access to hidden provider telemetry, billing data, or internal
  context-management state.

## Code Preservation

When processing source code or other exact technical content:

- Preserve indentation and syntax.
- Preserve comments when they contain useful information.
- Never globally deduplicate lines solely because they look identical.
- Never modify commands, paths, identifiers, versions, or configuration values
  unless explicitly requested.
- Prefer removing redundant surrounding explanation rather than modifying
  executable code.
- If uncertain whether two pieces of code or configuration are equivalent,
  keep both rather than risk changing behavior.

## Token Measurement

AI Token Saver supports two measurement modes:

- **Supplied-tokenizer mode:** the host may provide the tokenizer used by the
  target model, or a trusted token-counting function. The result records
  `token_count_source="supplied-tokenizer"`. This is only as exact as the
  supplied tokenizer and its match to the target model.
- **Fallback mode:** when no tokenizer is supplied, the implementation uses a
  dependency-free character-based estimate and records
  `token_count_source="approximate"`. This must never be presented as an exact
  model-token count.

Always report the reduction actually measured for the specific input. Do not
promise a fixed savings percentage.

## Redaction

Secret-looking values are redacted by default.

Supported modes:

- `off` — disable redaction.
- `common` — common API-key, password, bearer-token, and secret patterns.
- `strict` — common patterns plus additional Google-style key detection.

Redaction is a safety layer, not a credential manager and not a guarantee that
every secret will be detected.

## Benchmarking

When evaluating savings:

- Measure before and after using the same tokenizer or counting method.
- Report input tokens, output tokens, saved tokens, and percentage reduction
  when those measurements are available.
- Test both repetitive and non-repetitive inputs.
- Test code and structured technical content separately from prose.
- Do not use a highly repetitive example as evidence that the same reduction
  applies universally.
- Keep approximate measurements clearly labeled as approximate.
- If no reliable measurement is available, say that the result is an estimate
  instead of inventing a number.

### Deep Benchmark Engine

The repository includes `benchmarks/benchmark_runner.py` and
`tests/test_deep_benchmark_engine.py` for repeatable verification of the public
compaction behavior.

The deep benchmark suite covers:

- large-context compaction at representative sizes, with optional 1 MB, 5 MB,
  and 10 MB deep runs;
- real-time streaming with tiny and varied chunk boundaries;
- preservation of executable and structured technical content;
- default/common/strict secret-redaction behavior using only fake test values;
- supplied token-counter reporting and fallback measurement semantics;
- structured memory fact consolidation without rewriting history;
- repeated-compaction/idempotency stability.

Use `python -m benchmarks.benchmark_runner` for the CI-safe smoke suite. Use
`python -m benchmarks.benchmark_runner --deep` for the larger context run.
Use `--json` when machine-readable benchmark records are needed.

Benchmark results are evidence for the tested inputs and environment only. Do
not turn a benchmark result into a universal savings promise. The benchmark
runner must fail when a required behavior does not pass, and CI runs the smoke
suite after the normal pytest suite.

## Real Context Saver

The repository also includes `context_saver.py`, a deterministic context-state
layer that sits above token compaction. It is designed to reduce **what must be
carried between turns**, not merely remove duplicate lines.

The context saver preserves these high-value fields when supplied by the host:

- `project`
- `current_task`
- `decisions`
- `bugs`
- `fixes`
- `files`
- `commands`
- `tests`
- `services`
- `next_steps`

It produces a `ContextSnapshot` with a stable SHA-256 fingerprint and a compact
text representation. Repeated entries in structured fields are deduplicated,
service entries are normalized deterministically, and ordering differences in
service state do not change the fingerprint.

### Context Saver idempotency

`ContextSaver.save(state)` reports whether the normalized context changed.
`ContextSaver.save_if_changed(state)` returns no result when the normalized
context is unchanged. Hosts should prefer `save_if_changed` when a second save
must be a cheap no-op.

The context saver MUST NOT infer facts that are not supplied by the host. It is a
structured state compressor, not a semantic model that can safely invent missing
project information.

### Daily multi-service context

When a host supplies service state, the saver can compact status for daily work
across:

- GitHub — repository, branch, PR/issue, CI, and code state
- Vercel — deployment and project state
- Supabase — database/auth/backend state
- Gmail — relevant communication status
- Browser — current research/task state

Only include service state that the host actually supplies. Do not claim live
access to any service merely because its name appears in a snapshot.

### Context Saver safety

Do not place credentials, passwords, private keys, or raw access tokens into the
structured context state. Hosts that need credential storage must use secure
secret storage separately from the context saver.

Do not use the context saver to rewrite executable source code, commands, paths,
identifiers, versions, or exact error text. Those belong in protected technical
state.

## Safe Token Optimization

When saving context:

- Remove repeated information only when the repetition is safely identifiable.
- Remove genuine filler.
- Merge clearly equivalent facts in structured memory only, following the
  Memory-Level Fact Consolidation rules above.
- Use concise wording where meaning is unchanged.
- Keep one canonical version of each current fact.
- Remove superseded duplicates when they no longer provide useful history.
- Keep dependencies and relationships explicit.
- Preserve exact technical identifiers.
- Preserve important constraints.
- Preserve unresolved bugs and next steps.
- Do not use unexplained abbreviations that could reduce clarity.
- Do not rewrite code, commands, paths, model names, or error strings when
  exact text matters.

## Failure Safety

If compaction could remove information needed for correctness:

- Keep the information.
- Prefer lower savings over information loss.
- If uncertain whether two pieces of information are equivalent, do not merge
  them.
- Never invent missing context to make the compressed result appear complete.
- If an operation fails, report the failure rather than claiming it succeeded.
- Prefer an uncompressed result over a corrupted or misleading compressed result.

## Real-Time Compaction

When the implementation is available, context may be processed incrementally as
chunks arrive instead of waiting for the complete input.

- Feed incoming string chunks to the real-time compactor.
- Incomplete final lines are buffered until their content is complete.
- Newly completed safe lines can be emitted immediately.
- Adjacent duplicate lines may be removed.
- Code-like and technical repeated lines must be preserved.
- The final partial line is flushed when the stream finishes.
- The current implementation is line-oriented, not character-level or
  token-level streaming.
- Very large lines without a line ending may remain buffered until completion.
- Provider-specific streaming adapters may still be required to connect this
  implementation to an AI provider's streaming API.

## Token Counting in Real Time

The real-time compactor can use the same optional tokenizer/token-counter for
cumulative input/output measurements.

Supplying a tokenizer does **not** prove that it matches the target model. The
host application is responsible for supplying a trusted tokenizer appropriate
to the model whose context limits or usage are being measured.

## Universal AI Compatibility

This skill is model-agnostic and can be adapted for AI assistants, coding agents,
chat assistants, and systems that support custom instructions, skills, memory,
or context files.

Do not assume a specific AI provider, model, API, SDK, or application.

## Skill Compatibility

AI Token Saver MUST NOT block, disable, reset, or override other skills.

Other skills may control response style, coding behavior, browser behavior,
reasoning preferences, or other functions independently.

If another skill is active, AI Token Saver should continue its context-saving
behavior while respecting that skill's behavior.

## Commands

These commands are conventions for hosts that support custom skill commands.
They are not guaranteed to exist in every AI application.

### /save

Save important persistent information from the current conversation.

### /save-all

Save all **important persistent** context available from the current
conversation, then deduplicate and compress it. Do not interpret “all” as
permission to save secrets or temporary chatter.

### /save secret

Explicitly request secure storage of a specific project credential. This command
is available only when the host provides secure secret storage. Never fall back to
ordinary memory storage for credentials.

### /memory

Show relevant saved context in compact form. Secrets are excluded by default.

### /memory secret

Explicitly request a stored project credential when secure secret storage is
available. Never display credentials as part of ordinary `/memory`.

### /forget

Forget the specific information requested by the user.

If the target is ambiguous, ask before deleting.

### /forget secret

Remove an explicitly stored project credential when secure secret storage supports
that operation.

### /stop-saving

Disable AI Token Saver until re-enabled, if the host supports skill state.

### /start-saving

Enable AI Token Saver until disabled, if the host supports skill state.

## Memory Structure

Use:

PROJECT: <name>
GOAL: <goal>

STATE:
- <current fact>

DECISIONS:
- <decision>

FILES:
- <path> — <purpose>

ISSUES:
- <issue> — <status>

NEXT:
- <next step>

PREFERENCES:
- <persistent preference>

UPDATED: <date if known>

Do not include secrets in this ordinary memory structure.

## Updating Existing Memory

When new information changes an old value:

CURRENT:
- Store the new value as canonical.

HISTORY:
- Keep the old value only if it helps explain project evolution.

Never present outdated and current values as equally current.

## Context Selection

Prioritize information that helps future work:

HIGH:
- Current architecture
- Current implementation state
- Important decisions
- Current requirements
- File paths
- APIs/models/versions
- Known bugs
- Next steps
- Persistent workflow preferences

LOW:
- Repeated explanations
- Temporary conversation
- Old superseded details
- Casual chatter

## Safety

Never save credentials into ordinary persistent memory.

Credentials include:

- Passwords
- API keys
- Access tokens
- Authentication codes
- Private credentials
- Master passwords

An explicit `/save secret` request does not make plaintext memory safe. Secure
host-provided secret storage is still required.

You may save non-secret status such as:
"API key configured."

## Response Behavior

After `/save`, if the host supports the command:

"Saved. Context compressed."

After `/save-all`, if the host supports the command:

"Saved. Context deduplicated and compressed."

For an unchanged repeated saver command, prefer:

"Already compact and up to date."

Do not regenerate or dump the complete saved state for an unchanged repeated
command.

After `/save secret`, do not echo the credential. Confirm only that the secure
secret-store operation succeeded, or clearly state that secure storage is
unavailable.

Do not dump the entire memory unless the user asks for `/memory`.

## Persistence Honesty

This skill defines memory behavior. It does not guarantee that the host application
actually provides persistent storage or secure secret storage.

If persistent storage or secure secret storage is unavailable, say so instead of
pretending the information was saved permanently.
