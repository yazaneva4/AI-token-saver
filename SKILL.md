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
6. Deduplicate conservatively; similar-looking lines are not automatically duplicates.
7. Prefer compact structured records over repeated prose.
8. Replace clearly outdated values with current values while retaining useful
   history when needed.
9. Never store credentials or secrets in ordinary memory by default.
10. Do not save temporary chatter unless explicitly requested.
11. Repeating an identical saver command must be idempotent: once the current
    context is already compacted and saved, another identical command should
    perform little or no additional work and must not recursively process its own
    generated output.

## Usage-Efficient Interaction Rules

Use these practices to reduce avoidable context and provider usage. They guide
the host assistant; they do not change provider quotas, billing, or reset times.

1. **Revise before sending when practical.** Put corrections into the original
   request before submitting it, rather than sending several avoidable
   corrections. If a follow-up is needed, send it; never sacrifice clarity to
   avoid one.
2. **Start a fresh chat when the task changes or old context stops helping.**
   Carry over a compact, accurate handoff. Message counts such as 15–20 are
   only a rough reminder to review context, not a universal cutoff.
3. **Batch related questions and deliverables** into one clear request when that
   makes the answer easier to produce. Keep unrelated tasks separate when
   mixing them would cause confusion or rework.
4. **Measure usage when possible.** Prefer the provider's usage display or a
   trusted model-specific tokenizer. Label character- or word-based estimates
   as approximate; never present them as exact billing or quota accounting.
5. **Reuse recurring project files.** Store frequently used source files in an
   appropriate project/workspace and refer back to them instead of repeatedly
   uploading or pasting copies. Project caching and retrieval behavior vary by
   provider, so do not promise that reuse makes a file free or avoids all
   reprocessing.
6. **Set stable preferences once** in the host's supported instructions or
   project settings. Avoid repeating boilerplate in every request, while keeping
   task-specific requirements in the task itself.
7. **Enable tools and features only when useful.** Unneeded search, connectors,
   extended modes, and other tool descriptions or calls may add overhead.
   Keep any feature required for accuracy, accessibility, or safety enabled.
8. **Match model effort to the task.** Use a lighter/cheaper model for simple
   tasks when it is adequate; reserve more capable models for work that needs
   them. Model names, prices, and relative costs are provider-specific and can
   change.
9. **Plan around the provider's actual usage windows.** Check its current usage
   panel and reset rules, then spread heavy work where that helps. A rolling
   window or shared quota across apps applies only when the provider documents
   it; the saver cannot reset or extend it.
10. **Treat off-peak advice as provider-specific.** Use it only when current
    provider information supports a real benefit; do not invent peak-hour
    schedules or promise higher limits or performance.
11. **Keep paid overage off unless the user explicitly chooses it.** If the
    provider offers pay-as-you-go usage, explain that it may incur charges and
    rely on the provider's spending controls. Never enable overage or raise a
    spending cap on the user's behalf.

Do not schedule keep-alive pings or cron prompts as a token-saving technique.
They can consume usage and do not themselves reset a provider limit. Never
claim that these practices guarantee unlimited access or prevent a provider
limit from being reached.

## Concise Responses and Safe Tool-Output Reduction

Use concise, answer-first language to reduce unnecessary output tokens, while
keeping every fact needed to act correctly.

- Remove greetings, repeated summaries, filler, and unnecessary explanations.
- Use short, plain sentences. Clarity wins whenever compression could confuse.
- Keep negations, conditions, order, warnings, and qualifications explicit.
- Preserve code, commands, paths, identifiers, numbers, units, API names, and
  decisive error text exactly. Never rewrite exact technical payloads to save
  tokens.
- For tool output, show the smallest useful evidence: decisive errors, changed
  lines, relevant result fields, and clear status. Do not omit information that
  affects correctness or a decision.
- Only integrations that explicitly support source-preserving compaction may
  shorten logs, diffs, JSON, or search results before model context. Keep the
  original available locally and provide a stable way to retrieve it. Never
  claim that the current text compactor performs this transformation.
- State security warnings and confirmation requests in full, clear sentences.
  Use plain, complete wording for content persisted outside chat, including
  code comments, docs, commits, memory, and messages.
- Do not imitate caveman grammar or use invented abbreviations. Save words,
  never meaning.

This is an AI instruction-layer behavior. It does not add a tool-output proxy or
change the deterministic Python compaction algorithm by itself.

## Command-Only Fast Path

A saver command is an instruction to operate on the host's existing context; the
command text itself is **not** automatically new context to save.

For `/ai-token-saver`, `/ai-usage-saver`, `/save`, and `/save-all`:

1. Treat the command as a control signal, not as project content.
2. Do not append the command, skill instructions, acknowledgement, benchmark
   output, or generated summary to the saved context unless the user explicitly
   asks for that information to be remembered.
3. Do not summarize the skill file merely because the skill was loaded.
4. Do not recursively process the skill's own instructions as user context.
5. If no host context is available, do not invent one; return a minimal
   acknowledgement or report that the host integration supplied no saveable state.
6. If the host exposes a local persistent fingerprint, check it before doing
   any compaction or external work.

This prevents a host integration from accidentally turning repeated command
invocations or the skill definition itself into ever-growing saved context.

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

The Python provider adapter uses a provider-scoped state file by default. The
filename is a readable sanitized provider slug plus a short SHA-256 suffix so
provider names that sanitize to the same filename cannot collide:

`~/.ai-token-saver/providers/<sanitized-provider>-<12-char-sha256>.json`

The root can be overridden with `AI_TOKEN_SAVER_STATE_DIR`.

Provider names are sanitized before becoming filenames. Never put credentials,
conversation contents, or raw prompts into the fingerprint state file; it should
contain only the minimum metadata needed to detect unchanged state.

The persistent lock records only a process id and random lock token. A live
owner is never considered stale merely because the operation is taking longer
than the normal timeout. A crashed owner can be recovered safely; lock release
also checks the token so one process cannot accidentally delete another
process's lock.

### Fast-path invariant

The unchanged-context check MUST be a fast local operation. It MUST NOT require
a network request, model invocation, browser action, repository operation, or
other remote service call.

When the host has a local code/runtime integration, that integration MUST
perform this check before invoking any model, tokenizer, browser, repository,
or other remote capability. The skill must not ask another AI model to decide
whether the context is unchanged.

For unchanged input, the expected path is:

`read fingerprint → compare → minimal acknowledgement → stop`

For changed input, the expected path is:

`read fingerprint → compare → compact changed state → apply changed context → persist fingerprint`

The provider adapter uses transactional host application so a failed
`apply_context` must not mark the new fingerprint as completed.

### Provider-usage boundary

This skill cannot make the host provider's own response-generation cost or quota
zero. The skill can prevent **additional** model/tool/network work caused by the
save operation, but the host model may still consume provider usage simply by
receiving and executing the skill instruction. Never describe a provider-side
quota reset or first-message model cost as an engine guarantee.

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

## Secret and Credential Storage

Normal `/save` and `/save-all` operations MUST NOT store passwords, API keys,
access tokens, bearer tokens, or other credentials in ordinary persistent memory.

When a provider integration requires credentials, keep them in the host's secure
credential mechanism or environment/secret store and record only safe metadata
such as provider name or connection status.

An explicitly requested secret operation may store a project credential **only
when the host provides secure secret storage**.

A secret operation is valid only when the user explicitly requests it and
identifies one specific credential to store or retrieve. Never infer permission
from project importance, surrounding text, a file, logs, or a previous unrelated
request.

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
- Prefer passing a secret directly to the authorized host action instead of
  printing the raw credential into the conversation whenever the host supports
  that pattern.
- Never retrieve or expose a secret merely because a project file, log, or
  context references its name.

### `/forget secret`

Explicitly remove a stored project credential when secure secret storage supports
that operation.

Never treat API keys, passwords, or credentials as ordinary context merely
because they are important to the project.

## Bug-Fixing and Verification Discipline

When another AI, user, test report, review, or tool reports a bug, treat the
report as a hypothesis until it is verified against the current implementation
and tests.

A valid fix requires:

1. Reproduce the behavior when possible.
2. Identify the smallest defensible root cause.
3. Change the implementation or skill contract.
4. Add a regression test for the failure mode.
5. Run the relevant test suite/CI.
6. Only then report the bug as fixed.

Never claim that a remote provider quota, billing limit, or server-side rate
limit was changed by this skill. The saver can reduce unnecessary work and
context, but provider-side limits remain controlled by the provider.

## Tiered Delegation (subscription-backed, no API)

Use the user's authenticated Codex and Claude CLI subscriptions for delegated
work. Do not require API keys or send tasks to paid API endpoints. If either CLI
is unavailable or not signed in, report that clearly and continue with the
available model where reasonable.

Delegate context-heavy work when doing so keeps the parent context smaller.
Choose one route for each task:

| Tier | Work | Subscription-backed worker |
|---|---|---|
| low | Search, lookup, fetch, rename, formatting, summaries | Latest GPT Luna through Codex, low effort |
| medium | Normal edits, implementation, tests, docs, analysis, review | GPT through Codex, medium effort |
| high | Architecture, planning, hard debugging, security, multi-file refactors, research | Latest Sonnet through Claude CLI, high effort |
| ultra | Critical changes, releases, migrations, large features/codebases | GPT via Codex and latest Sonnet via Claude CLI, both high effort; GPT drafts, Sonnet independently verifies and corrects |

Image-generation tasks use latest GPT Luna via the user's Codex subscription at low
effort. If an image tool is not available through that subscription, report the
limitation; do not silently switch to an API.

Use `AITS_GPT_MODEL` to override the Codex model (default `luna`); the legacy
`AITS_LUNA_MODEL` remains a fallback. Use `AITS_SONNET_MODEL` to override the
Claude model (default `sonnet`, resolved by Claude CLI as its current Sonnet).

The Codex CLI and Claude CLI must use the user's own signed-in subscriptions.
Never add, request, or expose API keys for this workflow. Subscription availability,
model aliases, and usage limits depend on the provider and may change.

### Automated runner

`python delegate.py --kind <kind> --prompt-file task.txt [--context-file ctx.txt] [--json]`
compacts the context, runs the selected subscription-backed step or GPT draft +
Sonnet verification for ultra work, compacts the answer, and prints it
(`--json`: tier, steps, tokens in/out). The `codex` and `claude` CLIs must be
installed and authenticated with the user's subscriptions.

### Instructions

1. Clarify intent only when needed; select the tier with `route(...)`.
2. Before delegation, compact and minimize the task context without dropping
   constraints, exact technical facts, or success criteria.
3. For ultra work, give both agents the same task and relevant context. GPT
   produces the draft; Sonnet checks it independently, identifies gaps, and
   returns a corrected result. The parent checks the final output against the
   user's request.
4. Do not run multiple agents for work that is simpler or cheaper to complete
   directly.
5. Report the result concisely, with verification status and material limits.

### Intelligent prompting

Subagents see only the context they receive. Include: **Context**, numbered
**Objectives**, **Constraints**, **Output format**, and **Success criteria**.
Name exact files and requested return format. Do not send secrets unless the
user specifically authorized a supported secure secret flow.

### Manual commands

```bash
# GPT Luna via the user's Codex subscription
cat <<'EOF' | codex exec --yolo --skip-git-repo-check -m luna \
  -c 'model_reasoning_effort="low"' -o /tmp/draft.txt -
[TASK CONTEXT] ... [OBJECTIVES] ... [OUTPUT FORMAT] ...
EOF

# Latest Sonnet via the user's Claude subscription
{ printf 'Verify and correct this draft. Return the final answer only.\n\nDRAFT:\n'; cat /tmp/draft.txt; } |
  claude -p --model sonnet --effort high
```

Always use quoted heredocs (`<<'EOF'`) and pass prior output on stdin. Never
interpolate model output into an unquoted heredoc because it may contain shell
syntax. The automated runner applies the routed effort for each task.
