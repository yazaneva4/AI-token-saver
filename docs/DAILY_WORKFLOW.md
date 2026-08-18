# AI Token Saver — Daily Multi-Service Workflow

This document supplements `SKILL.md`. It is intentionally separate so the core skill does not need to become larger on every daily-work improvement.

## Goal

Keep long-running AI work compact, accurate, and resumable while working across GitHub, Vercel, Supabase, Gmail, web browsing, local development, and cloud development.

The optimization rule is:

> Reduce repeated context, not useful work.

Never sacrifice correctness merely to reduce tokens.

## Service State

Maintain a compact state for each active service:

```text
GITHUB:
- repository
- branch
- current task
- changed files
- latest relevant commit
- CI status

VERCEL:
- project
- deployment status
- latest build result
- production/preview status

SUPABASE:
- project
- schema/migration status
- authentication status
- relevant backend state

GMAIL:
- important sender/topic
- action required
- response status

BROWSER:
- current research/task
- relevant findings
- source links
- unresolved questions
```

Only update a service section when its state changes.

## GitHub

Prefer incremental repository inspection.

Do not repeatedly fetch unchanged files, diffs, or logs.

For CI, retain the workflow name, job, status, failing step, and useful error rather than thousands of successful log lines.

Never lose exact:

- file paths
- branch names
- commit SHAs
- commands
- identifiers
- version numbers
- error messages
- test names

When code changes, inspect the current version before editing it.

## Vercel

Track deployment state without retaining unnecessary build logs.

Preserve build failures and their relevant error messages. Do not store token values or other credentials.

A successful deployment can be represented compactly as:

```text
Vercel: production deployment succeeded; latest build passed.
```

## Supabase

Track schema decisions, migrations, RLS, authentication, storage, and relevant backend behavior.

Do not retain service-role keys, database passwords, or access tokens in ordinary context.

Prefer:

```text
Supabase: migration applied; RLS enabled; authentication configured.
```

over raw credential/config dumps.

## Gmail

Summarize routine email instead of retaining entire threads.

Preserve exact text when it is necessary for a technical requirement, error, requested change, or other important instruction.

Do not retain unrelated signatures, repeated quoted history, or boilerplate.

Do not expose credentials or authentication codes.

## Web Browsing

Extract relevant findings from pages rather than carrying entire pages forward.

Discard navigation menus, repeated footers, unrelated recommendations, and duplicate text.

Keep the source identity and relevant link when future verification may be needed.

Never claim that a fact came from a page unless it was actually observed or verified.

## Cross-Service Tasks

For a task spanning multiple services, preserve dependencies in order.

Example:

```text
1. GitHub: code updated.
2. Supabase: migration applied.
3. Vercel: deployment triggered.
4. Browser: production behavior checked.
5. Gmail: update sent.
```

Once a step is confirmed complete, do not repeatedly redo it unless a later change invalidates it.

## Checkpointing

For long tasks, maintain a compact checkpoint:

```text
PROJECT:
CURRENT TASK:
COMPLETED:
IN PROGRESS:
BLOCKED:
BUGS:
TESTS:
SERVICES:
NEXT:
```

The checkpoint must contain only information needed to resume the work.

## Repeated Commands

`/ai-token-saver` and `/ai-usage-saver` are aliases for the same saver workflow when both are supported by the host.

If both aliases appear in one user message, execute the saver operation once.

If an identical saver command is repeated with unchanged source state, do not rebuild the same checkpoint, re-run the same external tool calls, or feed the previous confirmation back into the saver as new source material.

Use the smallest possible acknowledgement for an unchanged state.

## Usage Saver Implementation

The repository includes `usage_saver.py` as a provider-agnostic implementation of the daily usage-saver layer.

It provides:

- `UsageCheckpoint` for resumable compact project state;
- `ServiceState` for GitHub, Vercel, Supabase, Gmail, and browser state;
- `state_fingerprint()` for deterministic SHA-256 state identity;
- `IdempotentUsageSaver` to avoid repeating expensive work for unchanged state;
- `normalize_saver_commands()` to collapse `/ai-token-saver` and `/ai-usage-saver` into one operation;
- `compact_checkpoint()` for deterministic normalization and exact-line deduplication of structured checkpoint facts.

This implementation does not bypass provider quotas, usage limits, billing controls, or safety restrictions. It only prevents redundant local work and keeps resumable state compact.

For cross-process idempotency, the host should persist the latest fingerprint and result outside the conversation. A process-local `IdempotentUsageSaver` cannot by itself remember state after the process exits.

## Bug Attack Protocol

A bug report is a hypothesis until verified.

When a Buggy appears:

1. Capture the exact reproduction.
2. Identify the layer involved: engine, skill, host, tool, provider, or test.
3. Inspect the current implementation.
4. Reproduce the failure when practical.
5. Determine the root cause.
6. Reject incorrect suggestions even if another AI proposed them.
7. Make the smallest correct change.
8. Add a regression test when appropriate.
9. Run focused tests.
10. Run the broader suite.
11. Inspect CI when available.
12. Only then declare the Buggy fixed.

Never weaken a correct implementation just to make a test pass.

## 5-Second Failure Investigation

If a repeated command or task works once and then hits a very short runtime/usage limit:

- compare the first and second input;
- check whether generated output was fed back as new input;
- check for recursive compaction;
- check for repeated external calls;
- check for growing saved state;
- check whether two aliases triggered the same workflow twice;
- check host/provider limits separately from engine behavior.

Do not assume the Python engine is responsible without evidence.

## Testing Matrix

Daily-work changes should be tested at multiple levels:

### Unit

Test the changed function directly.

### Regression

Test the exact Buggy reproduction.

### Idempotency

Run the same operation twice and verify that the second run does not create additional work when input is unchanged.

### Integration

Exercise the relevant service boundary when available.

### Deep benchmark

Run the repository's benchmark suite for large contexts, streaming, technical-content preservation, redaction, token counting, memory consolidation, and repeated-compaction stability.

The `tests/test_usage_saver.py` suite specifically verifies alias collapsing, unchanged-state idempotency, changed-state reruns, checkpoint normalization, stable fingerprints, and reset behavior.

## Usage Safety

Never attempt to bypass provider usage limits, quotas, billing controls, or safety restrictions.

The saver can reduce redundant context and unnecessary repeated work, but it cannot guarantee a provider's quota or remove a provider-imposed runtime limit.

## Secrets

Never put these into ordinary context:

- API keys
- passwords
- access tokens
- private keys
- service-role keys
- authentication codes
- session cookies

Keep only safe configuration state such as `authentication configured` or `deployment credentials available through secure storage`.

## Completion Rule

A task is complete only when the relevant implementation, tests, and service state have been verified.

Do not claim success from a code edit alone.

Do not claim CI passed without actual CI evidence.

Do not claim a deployment succeeded without a confirmed deployment result.
