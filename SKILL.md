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

## Everyday Token-Saving Workflow

Use this workflow when the user asks to save, carry forward, or reduce context. For ordinary tasks, apply the concise-response rules below without announcing token optimization.

1. **Keep only useful context.** Include the current goal, constraints, confirmed decisions, exact technical facts, unresolved blockers, and next action. Omit resolved discussion, repeated explanations, and unrelated history.
2. **Update by delta.** Add new or changed facts to the existing canonical state; do not resend or regenerate unchanged history. Keep superseded values only when they explain a decision or migration.
3. **Reuse accessible sources.** Refer to an existing file, project, or stable source instead of pasting it again when the host can access it. Never assume retrieval or caching is free.
4. **Right-size each turn.** Batch related requests; keep unrelated work separate. Ask only for missing information that materially changes the result. Avoid unnecessary acknowledgements, repeated summaries, tool calls, and agent delegation.
5. **Use the least costly adequate capability.** Select model effort and tools based on task difficulty; use stronger reasoning, browsing, or delegation only when it improves correctness or outcomes.
6. **Measure honestly.** Prefer the provider's meter or a tokenizer matching the target model. Label all other counts approximate. Report actual savings; never target a percentage by deleting meaning.
7. **Respect provider limits.** Check current provider usage windows and documented features. Caching, off-peak use, quotas, and model costs vary. Keep paid overage disabled unless the user explicitly chooses it. Keep-alive prompts consume usage and do not reset limits.

These practices can reduce avoidable context and output; they cannot change provider quotas, guarantee savings on a particular request, or make the skill itself free to load.

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

Provider-neutral host integrations can include the compact answer-style instruction from `provider_adapter.py` before generation. It steers the assistant toward concise output while preserving explicit detail requirements; it cannot enforce a length or guarantee a reduction.

This is an AI instruction-layer behavior. It does not add a tool-output proxy or change the deterministic Python compaction algorithm by itself.

## Fast, Idempotent Save Commands

For `/ai-token-saver`, `/ai-usage-saver`, `/save`, and `/save-all`, treat the command as a control signal, not content. Do not save the command, this skill, generated summaries, confirmations, or benchmark output unless explicitly requested. If the host provides no saveable context, say so briefly; never invent context.

Before compaction or external work, compare the relevant source state with the last saved fingerprint/version. If unchanged, return a short acknowledgement and stop. Do not regenerate, recursively compact, reapply, or re-send unchanged state. If changed, process only the delta, merge it into canonical state, and persist the new fingerprint only after successful application.

The check must be local and fast: no model, tokenizer, network, browser, repository, or other remote call. If the host offers a stable fingerprint, use it; otherwise compare normalized relevant source state. Never ask another model to decide whether input is unchanged.

For fresh processes, use the provider adapter's persistent `ContextSaver` state when available. Its state file stores minimum metadata only—not credentials, conversation contents, or raw prompts. Lock files contain only a process ID and random token; recover a lock only after confirming its owner is no longer alive, and release it only if its token still matches.

An unchanged save must not rewrite or append the saved state, repeat external calls, or create unbounded growth. A failed host application must not be recorded as completed. Expected fast path: `read fingerprint → compare → acknowledge → stop`.

This prevents additional work caused by saving; it cannot remove the provider usage already spent receiving and executing the command or skill.

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
| low | Search, lookup, fetch, rename, formatting, summaries | Latest Sonnet through Claude CLI, low effort |
| medium | Normal edits, implementation, tests, docs, analysis, review | GPT-6 Luna through Codex, medium effort |
| high | Architecture, planning, hard debugging, security, multi-file refactors, research | Latest Sonnet through Claude CLI, high effort |
| ultra | Critical changes, releases, migrations, large features/codebases | GPT-6 Luna and latest Sonnet work together; one uses medium effort and the other high, based on task type |

Image-generation tasks are a low-effort exception: use GPT-6 Luna via the user's
Codex subscription. Other low-tier tasks use latest Sonnet at low effort. If an image tool is not available through that subscription, report the
limitation; do not silently switch to an API.

Use `AITS_GPT_MODEL` to override GPT-6 Luna in Codex (default alias `luna`); the legacy
`AITS_LUNA_MODEL` remains a fallback. Use `AITS_SONNET_MODEL` to override the
Claude model (default `sonnet`, resolved by Claude CLI as its current Sonnet).

The Codex CLI and Claude CLI must use the user's own signed-in subscriptions.
Never add, request, or expose API keys for this workflow. Subscription availability,
model aliases, and usage limits depend on the provider and may change.

### Automated runner

`python delegate.py --kind <kind> --prompt-file task.txt [--context-file ctx.txt] [--json]`
compacts context, runs the selected subscription-backed step or GPT draft + Sonnet verification for ultra work, compacts the answer, and prints it (`--json`: tier, steps, tokens in/out). The `codex` and `claude` CLIs must be
installed and authenticated with the user's subscriptions.

### Instructions

1. Clarify intent only when needed; select the tier with `route(...)`.
2. Before delegation, compact and minimize the task context without dropping
   constraints, exact technical facts, or success criteria.
3. For ultra work, give both agents the same task and relevant context. Route
   large features/codebases to GPT high + Sonnet medium; route critical fixes,
   releases, migrations, and size-based ultra work to GPT medium + Sonnet high.
   GPT drafts; Sonnet checks independently and corrects. The parent checks the
   final output against the user's request.
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
# GPT-6 Luna image-generation task via the user's Codex subscription
cat <<'EOF' | codex exec --yolo --skip-git-repo-check -m luna \
  -c 'model_reasoning_effort="low"' -o /tmp/draft.txt -
[TASK CONTEXT] ... [OBJECTIVES] ... [OUTPUT FORMAT] ...
EOF

## Latest Sonnet via the user's Claude subscription (low-tier regular task)

`claude -p --model sonnet --effort low`

## Latest Sonnet verifies ultra work via the user's Claude subscription
{ printf 'Verify and correct this draft. Return the final answer only.\n\nDRAFT:\n'; cat /tmp/draft.txt; } |
  claude -p --model sonnet --effort high
```

Always use quoted heredocs (`<<'EOF'`) and pass prior output on stdin. Never
interpolate model output into an unquoted heredoc because it may contain shell
syntax. The automated runner applies the routed effort for each task.
