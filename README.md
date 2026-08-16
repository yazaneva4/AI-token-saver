# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver performs **real, measured compaction**. It removes duplicate lines and unnecessary whitespace while preserving meaningful content, then reports the reduction it actually achieved.

It also supports **real-time incremental compaction**: chunks can be fed as they arrive, and newly completed unique lines are emitted immediately instead of waiting for the complete input.

For highly repetitive input, the implementation can reach **up to about 99% reduction**. **99% is not a guaranteed result for every input**—if the input contains little redundancy, the real saving will be much smaller. The tool never deletes information just to make the percentage look better.

It provides:

- 🧠 Compact project-memory structures
- ♻️ Conservative duplicate removal that avoids treating differently indented code as identical
- ⚡ Real-time incremental/streaming compaction
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Before/after token measurement with either a supplied model tokenizer or an explicit approximate fallback
- 🤖 Model/provider-agnostic skill instructions
- 🔌 Designed to adapt to different AI assistants and coding agents
- 🔐 Secret-looking values are redacted by default during text compaction

## Real-time usage

Use `RealtimeCompactor` when data arrives incrementally:

```python
from ai_token_saver import RealtimeCompactor

compactor = RealtimeCompactor()

# Call this whenever a new chunk arrives from a stream/socket/model.
output = compactor.feed("first line\nsecond")
if output:
    print(output, end="", flush=True)

output = compactor.feed(" line\nfirst line\nthird line")
if output:
    print(output, end="", flush=True)

# Flush the final partial line when the stream ends.
output = compactor.finish()
if output:
    print(output, end="", flush=True)

result = compactor.result()
print(f"Reduction: {result.reduction_percent:.1%}")
```

Chunks may split in the middle of a line. The compactor buffers only the incomplete
final line, emits completed unique lines as soon as they arrive, and keeps cumulative
metrics. It does not need to wait for the full input.

For iterable streams, use `compact_stream()`:

```python
from ai_token_saver import compact_stream

for compacted_chunk in compact_stream(incoming_chunks):
    send_to_ai(compacted_chunk)
```

## Token counting

Without a tokenizer, AI Token Saver uses a dependency-free character-based estimate.
That estimate is explicitly **approximate** and should not be used for exact billing
or model-context-limit accounting.

For model-specific measurements, pass a trusted tokenizer or token-counting function:

```python
from ai_token_saver import compact_text_with_metrics


def count_tokens(text: str) -> int:
    # Replace this with the tokenizer for your target model.
    return len(text.split())

result = compact_text_with_metrics(
    "same line\nsame line\nunique line\n",
    tokenizer=count_tokens,
)

print(result.in_tokens)
print(result.out_tokens)
print(result.reduction_percent)
print(result.token_count_is_exact)
```

`token_count_is_exact=True` means the implementation used the supplied counter. It
does **not** independently verify that the supplied counter matches the target model;
the host application is responsible for that.

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
├── .github/
│   └── workflows/
│       └── tests.yml
└── tests/
    └── test_ai_token_saver.py
```

### `SKILL.md`

Provider-agnostic skill instructions for saving and compressing AI context.

### `ai_token_saver.py`

The Python implementation for text compaction, real-time incremental compaction,
model-specific or approximate token measurement, structured memory, persistence,
merging, rendering, and default secret redaction.

## Quick start

Clone the repository and run:

```bash
git clone https://github.com/yazaneva4/AI-token-saver.git
cd AI-token-saver
python ai_token_saver.py "We need to save the project state.\nThe project state is important.\nThe project state is important."
```

The command prints the compacted text and the measured reduction. Without a supplied
model tokenizer, the CLI labels its token measurement as approximate.

## Python usage

```python
from ai_token_saver import Memory, compact_text, compact_text_with_metrics, memory_to_text, reduction

text = """We need to save the project state.
We need to save the project state.
OpenSpark is the current project.
"""

# Basic usage - returns compacted text
compacted = compact_text(text)
print(compacted)
print(f"Reduction: {reduction(text, compacted):.1%}")

# Detailed metrics - returns in/out tokens and reduction
result = compact_text_with_metrics(text)
print(f"Input tokens:  {result.in_tokens}")
print(f"Output tokens: {result.out_tokens}")
print(f"Saved tokens:  {result.in_tokens - result.out_tokens}")
print(f"Reduction:     {result.reduction_percent:.1%}")
print(f"Token count:   {'exact' if result.token_count_is_exact else 'approximate'}")

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

GitHub Actions also runs the test suite on pushes and pull requests across Python
3.10 through 3.13.

The test suite covers duplicate removal, meaning preservation, code indentation,
newline preservation, exact/approximate token measurement, reduction bounds, memory
merging, JSON round-tripping, malformed-memory handling, secret redaction, real-time
chunked compaction, CRLF chunks, and input validation.

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

Early / experimental implementation. Token counting is approximate unless a trusted
model-specific tokenizer or token-counting function is supplied. Exact accounting
still depends on the supplied tokenizer matching the target model.
