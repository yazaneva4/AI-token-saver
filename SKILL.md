---
name: sparksave
description: >
  Token-efficient persistent project-memory skill. Compresses saved context toward
  a 55% token reduction while preserving meaning, technical accuracy, and important
  details. Works alongside other skills, including Caveman, without blocking them.
---

# SparkSave

## Purpose

Save important project context in compact form so future conversations need less
context while retaining the information needed to continue work accurately.

Target: approximately **55% fewer context/memory tokens** than an uncompressed
memory dump.

55% is a target, not a guarantee. Never remove information merely to hit the
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
10. Do not save temporary chatter unless the user explicitly asks.

## 55% Token Optimization

When saving context:

- Remove filler and repeated explanations.
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

Goal:

UNCOMPRESSED CONTEXT
        ↓
deduplicate
        ↓
merge
        ↓
remove filler
        ↓
compact structure
        ↓
~55% fewer context tokens

## Skill Compatibility

SparkSave MUST NOT block, disable, reset, or override other skills.

### Caveman

Caveman and SparkSave work together.

- Caveman controls response compression/style.
- SparkSave controls memory/context compression.
- Both may be active simultaneously.
- SparkSave must never turn Caveman off.
- Caveman must never prevent SparkSave from saving context.
- `/caveman` affects Caveman only.
- `stop caveman` / `normal mode` affects Caveman only.
- `/save`, `/save-all`, `/memory`, `/forget`, and `/stop-saving` affect SparkSave only.

When both are active, confirmations should also be concise.

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

If target is ambiguous, ask before deleting.

### /stop-saving

Disable SparkSave until re-enabled.

### /start-saving

Enable SparkSave.

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
- Store new value as canonical.

HISTORY:
- Keep old value only if it helps explain project evolution.

Never present outdated and current values as equally current.

Example:

Previous model: X.
Current model: Y.

Store:

MODEL: Y
HISTORY: X (replaced)

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
"Gemini API key configured."

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
