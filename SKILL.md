---
name: ai-token-saver
description: >
  Token-efficient persistent context and memory skill for any AI assistant.


  Compresses saved context toward an up-to-99% token reduction when repetition
  or filler allows, while preserving meaning, technical accuracy, and important
  details. Uses precise tiktoken-based counting, supports configurable aggression
  levels (safe/balanced/aggressive), provides JSON structured output, and is
  architected for future real-time streaming. Works alongside other skills without
  blocking or overriding them.
=======
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

Reports actual measured savings using precise `tiktoken`-based estimation.

## Core Rules

1. Save important project context accurately.
2. Remove only genuine redundancy, filler, or safely disposable formatting.
3. Preserve meaning, technical accuracy, and relationships between facts.
4. Preserve exact names, file paths, commands, model names, versions, APIs,
   configuration values, technical decisions, and error text when important.
5. Never invent missing information.

6. Deduplicate aggressively (exact and semantic when enabled).
=======
6. Deduplicate conservatively; similar-looking lines are not automatically
   duplicates.

7. Prefer compact structured records over repeated prose.
8. Replace clearly outdated values with current values while retaining useful
   history when needed.
9. Never store passwords, API keys, authentication codes, private tokens, or
   other secrets.
10. Do not save temporary chatter unless explicitly requested.
11. Support configurable aggression: safe (preserve all), balanced (default), aggressive (max compression).
12. Provide structured JSON output for automation pipelines.
13. Maintain stateful architecture compatible with real-time streaming inputs.

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

## Safe Token Optimization

When saving context:

- Remove repeated information only when the repetition is safely identifiable.
- Remove genuine filler.
- Merge clearly equivalent facts in structured memory.
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
Supports optional `--mode` (safe|balanced|aggressive) and `--json` flags.

### /save-all


Save all important persistent context available from the current conversation,
then deduplicate and compress it.
Supports optional `--mode` (safe|balanced|aggressive) and `--json` flags.
=======
Save all **important persistent** context available from the current
conversation, then deduplicate and compress it. Do not interpret “all” as
permission to save secrets or temporary chatter.

### /memory

Show relevant saved context in compact form.

### /forget

Forget the specific information requested by the user.

If the target is ambiguous, ask before deleting.

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

Only include sections that contain useful information.

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

Never save:

- Passwords
- API keys
- Access tokens
- Authentication codes
- Private credentials

You may save non-secret status such as:
"API key configured."

## Response Behavior

After `/save`, if the host supports the command:

"Saved. Context compressed."

After `/save-all`, if the host supports the command:

"Saved. Context deduplicated and compressed."

Do not dump the entire memory unless the user asks for `/memory`.

## Persistence Honesty

This skill defines memory behavior. It does not guarantee that the host application
actually provides persistent storage.

If persistent storage is unavailable, say so instead of pretending memory was saved
permanently.
