# Claude Token Saver

A compact, dependency-free **SparkSave** implementation for reducing repeated context and memory overhead while preserving important project information.

## What it does

SparkSave is designed around a target of **about 55% fewer context/memory tokens** when the input contains repetition or filler. The 55% figure is a target, not a guarantee.

It provides:

- 🧠 Compact project-memory structures
- ♻️ Duplicate and filler removal
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Approximate before/after token estimation
- 🪨 Compatibility with the Caveman response-compression skill
- 🔐 No storage of passwords, API keys, access tokens, or authentication codes

## Files

```text
Claude-token-saver/
├── SKILL.md
├── sparksave.py
└── tests/
    └── test_sparksave.py
```

### `SKILL.md`

The skill instructions for using SparkSave as a memory/context-saving skill. It
also defines how SparkSave works alongside Caveman without disabling or overriding it.

### `sparksave.py`

The actual Python implementation. It includes:

- `compact_text()` — compact repeated/filler-heavy text
- `deduplicate()` — remove duplicate entries while preserving order
- `estimate_tokens()` — approximate token count
- `reduction()` — calculate approximate token reduction
- `Memory` — structured project-memory model
- `save_memory()` / `load_memory()` — JSON persistence
- `merge_memory()` — merge and deduplicate memory
- `memory_to_text()` — render compact structured memory

## Quick start

Clone the repository and run:

```bash
git clone https://github.com/yazaneva4/Claude-token-saver.git
cd Claude-token-saver
python sparksave.py "Now we need to save the project state.\nThe project state is important.\nThe project state is important."
```

The command prints the compacted text and an approximate reduction percentage.

## Python usage

```python
from sparksave import Memory, compact_text, memory_to_text, merge_memory

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

The repository includes tests for compaction, token-reduction calculation,
memory merging, and compact rendering.

With pytest installed:

```bash
python -m pytest
```

## Token-saving philosophy

SparkSave does **not** blindly delete context to hit a percentage. It prioritizes:

1. Removing repeated information.
2. Removing conversational filler.
3. Keeping one canonical current value.
4. Preserving exact technical identifiers, paths, commands, models, versions,
   bugs, decisions, constraints, and next steps.
5. Keeping useful history only when it helps explain a change.

The goal is **less context, not less meaning**.

## Caveman + SparkSave

These skills have different jobs:

- **Caveman** 🪨 — compresses the assistant's response style.
- **SparkSave** 💾 — compresses saved project context and memory.

They can run together. SparkSave must not disable or override Caveman, and
Caveman must not prevent SparkSave from saving context.

## Safety

Do not put secrets into SparkSave memory. Never store passwords, API keys,
access tokens, authentication codes, or private credentials.

## Status

Early project / experimental implementation. Token estimation is intentionally
approximate and is not suitable for billing or exact model-token accounting.

## License

Add a license before distributing the project publicly if you want to define
reuse and contribution terms.
