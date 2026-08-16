# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver performs **real, measured compaction**. It removes duplicate lines and unnecessary whitespace while preserving meaningful content, then reports the approximate reduction it actually achieved.

For highly repetitive input, the implementation can reach **up to about 99% reduction**. **99% is not a guaranteed result for every input**—if the input contains little redundancy, the real saving will be much smaller. The tool never deletes information just to make the percentage look better.

It provides:

- 🧠 Compact project-memory structures
- ♻️ Duplicate removal without deleting meaningful phrases
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Actual before/after reduction measurement with in/out token counts
- 🎯 Accurate token counting with tiktoken (optional)
- ⚙️ Configurable compression levels (safe/balanced/aggressive)
- 📄 JSON output for automation and pipelines
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

The command prints the compacted text and the **measured approximate reduction**
for that input.

### Reading from stdin

You can also pipe text directly:

```bash
cat large_file.txt | python ai_token_saver.py --stdin -v
```

Or use echo with newlines:

```bash
echo -e "Line 1\nLine 1\nLine 2" | python ai_token_saver.py --stdin
```

### JSON output for automation

Get structured JSON output for pipeline integration:

```bash
python ai_token_saver.py --json "Some text\nSome text" 
```

Output:
```json
{
  "original_tokens": 10,
  "compressed_tokens": 5,
  "saved_tokens": 5,
  "reduction_percent": 50.0,
  "text": "Some text"
}
```

### Compression levels

Control how aggressive the compression should be:

```bash
# Safe mode - minimal changes, preserve formatting
python ai_token_saver.py --aggression safe "text here"

# Balanced mode - default, good for most cases
python ai_token_saver.py --aggression balanced "text here"

# Aggressive mode - maximum compression
python ai_token_saver.py --aggression aggressive "text here" -v
```

### Accurate token counting

Use tiktoken for precise token counts (requires tiktoken installed):

```bash
python ai_token_saver.py --model gpt-4 "text here" -v
```

## Python usage

```python
from ai_token_saver import Memory, compact_text, compact_text_with_metrics, memory_to_text, reduction, count_tokens

text = """We need to save the project state.
We need to save the project state.
OpenSpark is the current project.
"""

# Basic usage - returns compacted text
compacted = compact_text(text)
print(compacted)
print(f"Reduction: {reduction(text, compacted):.1%}")

# With aggression level
compacted_safe = compact_text(text, aggression="safe")
compacted_aggressive = compact_text(text, aggression="aggressive")

# Detailed metrics - returns in/out tokens and reduction
result = compact_text_with_metrics(text)
print(f"Input tokens:  {result.in_tokens}")
print(f"Output tokens: {result.out_tokens}")
print(f"Saved tokens:  {result.in_tokens - result.out_tokens}")
print(f"Reduction:     {result.reduction_percent:.1%}")

# Accurate token counting with tiktoken
exact_tokens = count_tokens(text, model="gpt-4")
print(f"Exact tokens (tiktoken): {exact_tokens}")

# JSON output for automation
result_json = compact_text_with_metrics(text, output_json=True)
import json
output = {
    "original_tokens": result_json.in_tokens,
    "compressed_tokens": result_json.out_tokens,
    "saved_tokens": result_json.in_tokens - result_json.out_tokens,
    "reduction_percent": round(result_json.reduction_percent * 100, 2),
    "text": result_json.compacted
}
print(json.dumps(output, indent=2))

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
6. Reporting the reduction actually achieved instead of claiming a fixed saving.

The goal is **less context, not less meaning**.

## Safety

Never intentionally put secrets into AI Token Saver memory. Text compaction
redacts common secret-looking values by default. This is a safety layer, not a
guaranty of secret detection; do not rely on it as a credential manager.

## Status

Early / experimental implementation. Token estimation is intentionally
approximate and is not suitable for billing or exact model-token accounting.
