---
name: ai-token-saver
description: >
  Token-efficient persistent context and memory skill for any AI assistant.
  Reduces safe redundancy while preserving meaning, technical accuracy, and
  important details. Supports real-time incremental compaction and optional
  model-specific token counting when the host provides a trusted tokenizer.
---

# AI Token Saver

Preserve meaning first, remove safe redundancy second, measure third. Savings near 99% occur only on extremely repetitive input or result-only answers; they are never a target or a promise. Never delete information to reach a percentage.

## Core rules

1. Save important context accurately: goal, constraints, decisions, exact technical facts, blockers, next action. Never invent missing information.
2. Keep exact names, paths, commands, model names, versions, APIs, config values and error text.
3. Never drop a repeated line by default (a repeat can be a separate event or instruction). `dedupe="runs"` shortens long runs and is exactly reversible (`expand_runs`); `adjacent`, `global` and `aggressive` are lossy.
4. Text is never masked or rewritten because it looks like a credential. Do not put credentials in ordinary persistent memory; secret operations are described in `references/secrets-and-verification.md`.
5. Update by delta: add new or changed facts to the saved state instead of resending unchanged history. Refer to accessible files instead of pasting them again.
6. Do not save temporary chatter, the saver command itself, this skill, or generated confirmations.
7. Report measured savings only, with the provider's meter or a matching tokenizer; label other counts approximate.

## Answering concisely

Answer first. Drop greetings, recaps, filler and offers of more help. Short plain sentences; keep negations, conditions, order and warnings explicit. Never rewrite code, commands, paths, identifiers, numbers or decisive error text. Show the smallest useful tool output (decisive errors, changed lines, status). Security warnings and confirmations stay in full sentences. Do not imitate caveman grammar; if another telegraphic-style skill is active, plain grammar wins.

| Level | Behavior | Use |
|---|---|---|
| standard | Answer first, no filler | default |
| tight | No preamble, recap or offers | status, explanations |
| max | Only the code, command, value or diff; one sentence for a blocker | answer is the artifact |

Use the lowest level that serves the request; never drop errors, warnings or confirmations at any level. Hosts select it with `prepare_request(..., output_level=...)`.

## Save commands (`/ai-token-saver`, `/ai-usage-saver`, `/save`, `/save-all`)

Treat the command as a control signal, not content. Compare local state with the last saved fingerprint first: unchanged means acknowledge briefly and stop (no model, tokenizer, network or rewrite). Changed means process only the delta, merge it, and persist the new fingerprint after success. Nothing saveable: say so; never invent context. This avoids extra work from saving; it cannot refund usage already spent loading the skill, and it cannot change provider quotas.

## Sub-agents

The main model manages; sub-agents come from the user's signed-in CLIs, never API keys. Default mode is `auto` (an optimizer picks solo, one-model or mix by quality, cost, speed and main-model tokens). Do not delegate small tasks. Use `python delegate.py --kind <kind> --main <model> ...`. Tiers: Haiku = light, Sonnet = standard, Opus = deep; other providers map by model name.

## Read more only when needed

- `references/workflow-and-output.md`: full everyday workflow, output-level and savings detail.
- `references/provider-integration.md`: `ProviderAdapter` lifecycle for hosts.
- `references/secrets-and-verification.md`: `/save secret`, `/memory secret`, bug-fix discipline.
- `references/subagents.md`: modes, optimizer, providers, runner flags, manual commands.
