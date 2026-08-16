---
name: ai-token-saver
description: >
  Token-efficient persistent context and memory skill for any AI assistant.
  Compresses saved context toward an up-to-99% reduction when repetition or
  filler allows, while preserving meaning, technical accuracy, and important
  details. Supports real-time incremental compaction and optional exact token
  counting when the host provides the target model's tokenizer.
---

# AI Token Saver

## Purpose

Save important project context in compact form so any AI assistant can continue
work accurately while using less context.

Target: **up to about 99% fewer context/memory tokens** when the input contains
substantial repetition or filler.

99% is a target, not a guarantee. Never remove information merely to hit the
target if doing so would change meaning or break future work.

## Core Rules

1. Save important project context accurately.
2. Compress repeated or redundant information.
3. Preserve meaning, technical accuracy, and useful relationships between facts.
4. Preserve exact names, file paths, commands, model names, versions, APIs,
   configuration values, and technical decisions when important.
5. Never invent missing information.
6. Deduplicate aggressively.
7. Prefer compact structured records over repeated prose.
8. Replace clearly outdated values with current values while retaining useful
   history when needed.
9. Never store passwords, API keys, authentication codes, private tokens, or
   other secrets.
10. Do not save temporary chatter unless explicitly requested.

## Token Measurement

AI Token Saver supports two measurement modes:

- **Exact mode:** when the host provides the tokenizer used by the target model,
  pass that tokenizer or a token-counting function to the implementation. The
  reported input/output counts and reduction then use that tokenizer.
- **Fallback mode:** when no tokenizer is supplied, the implementation uses a
  dependency-free character-based estimate. This is explicitly approximate and
  must never be presented as an exact model-token count.

Never claim a fixed percentage of savings from the fallback estimate. Always
report the reduction actually measured for the specific input.

## 99% Token Optimization

When saving context:

- Remove repeated information.
- Remove unnecessary filler and whitespace.
- Merge related facts.
- Use concise wording.
- Keep one canonical version of each current fact.
- Remove superseded duplicate entries.
- Keep dependencies and relationships explicit.
- Preserve exact technical identifiers.
- Preserve important constraints.
- Preserve unresolved bugs and next steps.
- Do not use unexplained abbreviations that could reduce clarity.
- Do not compress code, commands, paths, model names, or error strings when
  exact text matters.

The 99% figure is a maximum target for cases where the source contains enough
redundancy to support that level of reduction. It is not a promise of 99%
reduction on every input.

## Real-Time Compaction

When the implementation is available, context may be processed incrementally
as chunks arrive instead of waiting for the complete input.

- Feed incoming chunks to the real-time compactor.
- Keep incomplete final lines buffered until their content is complete.
- Emit newly completed unique lines as soon as they can be safely processed.
- Preserve the first occurrence's exact meaningful content.
- Flush the final partial line when the stream finishes.
- Do not claim that real-time compaction is character-level or token-level when
  the implementation is using safe line-level buffering.

Real-time compaction does not automatically connect to a provider's streaming
API. A provider-specific adapter may be required by the host application.

## Universal AI Compatibility

This skill is designed to be model-agnostic.

It can be adapted for AI assistants, coding agents, chat assistants, and other
systems that support custom instructions, skills, memory, or context files.

Do not assume a specific AI provider, model, API, SDK, or application.

## Skill Compatibility

AI Token Saver MUST NOT block, disable, reset, or override other skills.

Other skills may control response style, coding behavior, browser behavior,
reasoning preferences, or other functions independently.

If another skill is active, AI Token Saver should continue saving and compressing
context while respecting that skill's behavior.

## Commands

### /save

Save important persistent information from the current conversation.

### /save-all

Save all important persistent context available from the current conversation,
then deduplicate and compress it.

### /memory

Show relevant saved context in compact form.

### /forget

Forget the specific information requested by the user.

If the target is ambiguous, ask before deleting.

### /stop-saving

Disable AI Token Saver until re-enabled.

### /start-saving

Enable AI Token Saver.

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

After `/save`:

"Saved. Context compressed."

After `/save-all`:

"Saved. Context deduplicated and compressed."

Do not dump the entire memory unless the user asks for `/memory`.

## Persistence Honesty

This skill defines memory behavior. It does not guarantee that the host application
actually provides persistent storage.

If persistent storage is unavailable, say so instead of pretending memory was saved
permanently.
