# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver targets **about 55% fewer context/memory tokens** when the input contains repetition or filler. The 55% figure is a target, not a guarantee.

It provides:

- 🧠 Compact project-memory structures
- ♻️ Duplicate and filler removal
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Approximate before/after token estimation
- 🤖 Model/provider-agnostic skill instructions
- 🔌 Designed to adapt to different AI assistants and coding agents
- 🪨 Compatible with the Caveman skill without overriding it
- 🔐 No storage of passwords, API keys, access tokens, or authentication codes

## Available for AI assistants

AI Token Saver is **not locked to Claude, OpenAI, Gemini, or any other provider**.

It can be adapted for:

- Chat assistants
- Coding agents
- AI IDE assistants
- Agent frameworks
- Custom AI applications
- Any AI system that supports custom skills, instructions, memory, or context files

Different AI platforms may have different skill formats and capabilities, so the
installation method can vary. The core memory-saving rules remain provider-agnostic.

## Recommended setup

**Recommended for the best experience:** use **AI Token Saver + Caveman** together
when your AI platform supports both skills.

- **AI Token Saver** 💾 — reduces saved context and memory overhead.
- **Caveman** 🪨 — compresses assistant response style and helps reduce output tokens.

They have different jobs and can work together without either skill disabling the other.

### Caveman disclaimer

**Caveman is NOT made by me and is NOT part of AI Token Saver. Caveman was made
by JuliusBrussee.** This project only recommends and documents compatibility with
Caveman as an optional complementary skill. All Caveman credit belongs to its creator.

## Files

```text
AI-token-saver/
├── SKILL.md
├── sparksave.py
├── README.md
└── tests/
    └── test_sparksave.py
```

### `SKILL.md`

Provider-agnostic skill instructions for saving and compressing AI context.

### `sparksave.py`

The Python implementation for text compaction, token estimation, structured
memory, persistence, merging, and rendering.

## Quick start

Clone the repository and run:

```bash
git clone https://github.com/yazaneva4/Claude-token-saver.git
cd Claude-token-saver
python sparksave.py "We need to save the project state.\nThe project state is important.\nThe project state is important."
```

The command prints compacted text and an approximate reduction percentage.

## Python usage

```python
from sparksave import Memory, compact_text, memory_to_text

text = """We need to save the project state.
We need to save the project state.
OpenSpark is the current project.
"""

print(compact_text(text))

memory = Memory(
    project="OpenSpark",
    goal="AI auto-router",
    state=["provider system added"],
    next_steps=["add tests"],
)

print(memory_to_text(memory))
```

## Tests

```bash
python -m pytest
```

## Token-saving philosophy

AI Token Saver does **not** blindly delete context to hit a percentage. It
prioritizes:

1. Removing repeated information.
2. Removing conversational filler.
3. Keeping one canonical current value.
4. Preserving exact technical identifiers, paths, commands, models, versions,
   bugs, decisions, constraints, and next steps.
5. Keeping useful history only when it helps explain a change.

The goal is **less context, not less meaning**.

## Safety

Do not put secrets into AI Token Saver memory. Never store passwords, API keys,
access tokens, authentication codes, or private credentials.

## Status

Early / experimental implementation. Token estimation is intentionally
approximate and is not suitable for billing or exact model-token accounting.
