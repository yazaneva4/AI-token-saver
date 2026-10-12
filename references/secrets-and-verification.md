# Secret storage and verification discipline

Loaded on demand from SKILL.md.

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
