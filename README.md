# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver targets **up to about 99% fewer context/memory tokens** when the input contains substantial repetition or filler. The 99% figure is a target, not a guarantee, and the tool must never remove information merely to reach a percentage.

It provides:

- 🧠 Compact project-memory structures
- ♻️ Duplicate removal without deleting meaningful phrases
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Approximate before/after token estimation
- 🤖 Model/provider-agnostic skill instructions
- 🔌 Designed to adapt to different AI assistants and coding agents
- 🔐 Secret-looking values are redacted by default during text compaction

## Available for AI assistants

AI Token Saver is **not locked to Claude, OpenAI, Gemini, or any other provider**.

It can be adapted for chat assistants, coding agents, AI IDE assistants, agent
frameworks, custom AI applications, and any AI system that supports custom
skills, instructions, memory, or context files.

Different AI platforms may have different skill formats and capabilities, so the
installation method can vary. The core memory-saving rules remain provider-agnostic.

## Files

```text
AI-token-saver/
├── SKILL.md
├── ai_token_saver.py
├── README.md
└── tests/
    └── test_ai_token_saver.py
```

### `SKILL.md`

Provider-agnostic skill instructions for saving and compressing AI context.

### `ai_token_saver.py`

The Python implementation for text compaction, approximate token estimation,
structured memory, persistence, merging, rendering, and default secret redaction.

## Quick start

Clone the repository and run:

```bash
git clone https://github.com/yazaneva4/AI-token-saver.git
cd AI-token-saver
python ai_token_saver.py "We need to save the project state.\nThe project state is important.\nThe project state is important."
```

The command prints compacted text and an approximate reduction percentage.

## Python usage

```python
from ai_token_saver import Memory, compact_text, memory_to_text

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

The test suite covers duplicate removal, meaning preservation, reduction bounds,
memory merging, JSON round-tripping, malformed-memory handling, and secret redaction.

## Token-saving philosophy

AI Token Saver does **not** blindly delete context to hit a percentage. It prioritizes:

1. Removing repeated information.
2. Removing unnecessary whitespace.
3. Keeping one canonical current value.
4. Preserving exact technical identifiers, paths, commands, models, versions,
   bugs, decisions, constraints, and next steps.
5. Keeping useful history only when it helps explain a change.

The goal is **less context, not less meaning**.

## Safety

Never intentionally put secrets into AI Token Saver memory. Text compaction
redacts common secret-looking values by default. This is a safety layer, not a
guaranty of secret detection; do not rely on it as a credential manager.

## Status

Early / experimental implementation. Token estimation is intentionally
approximate and is not suitable for billing or exact model-token accounting.
