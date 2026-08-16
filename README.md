# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver performs **real, measured compaction**. By default it removes blank lines and **adjacent duplicate non-empty lines** while preserving meaningful content. It deliberately avoids global duplicate removal for code-like or structured technical content because repeated lines can be intentional.

It also supports **real-time incremental compaction**: chunks can be fed as they arrive, and newly completed safe lines are emitted immediately instead of waiting for the complete input.

For highly repetitive or padded input, the implementation can sometimes reach **around or above 99% reduction**. **99% is not a guaranteed result for every input**—if the input contains little redundancy, the real saving will be much smaller. The tool never deletes information just to make the percentage look better.

It provides:

- 🧠 Compact project-memory structures
- 🛡️ Code-aware conservative duplicate removal
- ⚡ Real-time incremental/streaming compaction
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication

- 📏 Actual before/after reduction measurement with in/out token counts
- 🎯 Accurate token counting with tiktoken (optional)
- ⚙️ Configurable compression levels (safe/balanced/aggressive)
- 📄 JSON output for automation and pipelines
=======
- 📏 Before/after token measurement with either a supplied tokenizer or an explicit approximate fallback

- 🤖 Model/provider-agnostic skill instructions
- 🔌 Designed to adapt to different AI assistants and coding agents
- 🔐 Configurable secret-looking-value redaction

## Safety-first compaction

The default mode is intentionally conservative:

- Repeated prose lines are removed only when they are adjacent.
- Repeated code, commands, paths, JSON/YAML, SQL, logs, and other technical-looking content is **not globally deduplicated**.
- Indentation and exact technical content are preserved.
- If you explicitly enable `aggressive=True`, global duplicate removal is still disabled for content that looks technical.
- For memory lists, merging may use global exact-line deduplication because those entries are structured facts rather than executable source code.

This is important: **AI Token Saver is a redundancy remover, not a semantic code optimizer.** When uncertain, it keeps information rather than risking behavior changes.

## Real-time usage

Use `RealtimeCompactor` when data arrives incrementally:

```python
from ai_token_saver import RealtimeCompactor

compactor = RealtimeCompactor()

output = compactor.feed("first line\nsecond")
if output:
    print(output, end="", flush=True)

output = compactor.feed(" line\nfirst line\nthird line")
if output:
    print(output, end="", flush=True)

output = compactor.finish()
if output:
    print(output, end="", flush=True)

result = compactor.result()
print(f"Reduction: {result.reduction_percent:.1%}")
```

Chunks may split in the middle of a line. The compactor buffers only the incomplete
final line, emits completed safe lines as soon as they arrive, and keeps cumulative
metrics. It does not need to wait for the full input.

For iterable streams, use `compact_stream()`.

## Token counting

Without a tokenizer, AI Token Saver uses a dependency-free character-based estimate.
That estimate is explicitly **approximate** and should not be used for exact billing
or model-context-limit accounting.

For model-specific measurements, pass a trusted tokenizer or token-counting function:

```python
from ai_token_saver import compact_text_with_metrics


def count_tokens(text: str) -> int:
    return len(text.split())

result = compact_text_with_metrics(
    "same line\nsame line\nunique line\n",
    tokenizer=count_tokens,
)

print(result.in_tokens)
print(result.out_tokens)
print(result.reduction_percent)
print(result.token_count_is_exact)
print(result.token_count_source)
```

`token_count_is_exact=True` means the implementation used the supplied counter. It
does **not** independently verify that the supplied counter matches the target model.
`token_count_source` is `"supplied-tokenizer"` when a counter is supplied and
`"approximate"` otherwise.

## Redaction modes

Secret-looking values are redacted by default. You can choose:

- `off` — no redaction
- `common` — common API-key/password/token patterns
- `strict` — common patterns plus additional Google-style key detection

Example:

```python
from ai_token_saver import compact_text

safe = compact_text("api_key=SECRET123", redaction_mode="common")
```

Redaction is a safety layer, **not a credential manager or a guarantee of secret detection**.

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

## Quick start

```bash
git clone https://github.com/yazaneva4/AI-token-saver.git
cd AI-token-saver
python ai_token_saver.py "We need to save the project state.\nThe project state is important.\nThe project state is important."
```

Without a supplied model tokenizer, the CLI labels its token measurement as approximate.

Use `--aggressive` only when stronger prose deduplication is wanted. Technical-looking
content remains protected.

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

compacted = compact_text(text)
print(compacted)
print(f"Reduction: {reduction(text, compacted):.1%}")



GitHub Actions runs the test suite on pushes and pull requests across Python
3.10 through 3.13.

The test suite covers safe adjacent deduplication, code preservation, aggressive-mode
safety, newline preservation, exact/approximate token measurement, reduction bounds,
memory merging, JSON round-tripping, malformed-memory handling, redaction modes,
real-time chunked compaction, CRLF chunks, and input validation.

## Token-saving philosophy

AI Token Saver does **not** blindly delete context to hit a percentage. It prioritizes:

1. Removing repeated information when that repetition is safely identifiable.
2. Removing blank/filler formatting where meaning is unchanged.
3. Keeping one canonical current value in structured memory.
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
