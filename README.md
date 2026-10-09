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
├── SKILL.md                  # the skill
├── README.md
├── ai_token_saver.py         # core compaction engine (Python API)
├── context_saver.py          # context snapshots
├── usage_saver.py            # idempotent usage checkpoints
├── realtime_usage_saver.py   # real-time incremental saver
├── provider_adapter.py       # provider-neutral integration and output levels
├── model_router.py           # sub-agent routing and auto optimizer
├── delegate.py               # command-line runner for routed sub-agents
├── benchmarks/               # benchmark runner
├── tests/                    # test suite
└── .github/workflows/        # CI (tests.yml)
```

## Quick start

```bash
git clone https://github.com/yazaneva4/AI-token-saver.git
cd AI-token-saver
```

`ai_token_saver.py` is a Python library with no command-line interface. See
[Python usage](#python-usage) below. Without a supplied model tokenizer, token
measurements are labeled approximate.

For stronger prose deduplication, call `compact_text(text, aggressive=True)`.
Technical-looking content remains protected.

## Python usage

```python
from ai_token_saver import Memory, compact_text, compact_text_with_metrics, memory_to_text, reduction

text = """We need to save the project state.
We need to save the project state.
OpenSpark is the current project.
"""

compacted = compact_text(text)
print(compacted)
print(f"Reduction: {reduction(text, compacted):.1%}")

result = compact_text_with_metrics(text)
print(f"Input tokens:  {result.in_tokens}")
print(f"Output tokens: {result.out_tokens}")
print(f"Saved tokens:  {result.in_tokens - result.out_tokens}")
print(f"Reduction:     {result.reduction_percent:.1%}")
print(f"Token count:   {result.token_count_source}")

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

GitHub Actions runs the test suite on pushes and pull requests across Python
3.10 through 3.13.

The test suite covers safe adjacent deduplication, code preservation, aggressive-mode
safety, newline preservation, exact/approximate token measurement, reduction bounds,
memory merging, JSON round-tripping, malformed-memory handling, redaction modes,
real-time chunked compaction, CRLF chunks, and input validation.

## Practical usage-saving rules

The companion [skill instructions](SKILL.md#everyday-token-saving-workflow) apply these habits across assistants. They reduce avoidable context and usage; they cannot change a provider's quota or guarantee unlimited access.

- Revise a request before sending when practical; use follow-ups whenever needed for clarity.
- Start a fresh chat when the task changes or old context is no longer useful, carrying over a compact handoff. Message-count suggestions are only rough reminders.
- Batch related questions, reuse recurring project files, and save stable preferences once in host settings.
- Track usage with the provider's meter or a trusted tokenizer; mark estimates as approximate.
- Use only the tools needed and choose a model suited to the task.
- Follow the provider's documented usage windows. Off-peak timing and file caching benefits vary by provider.
- Keep paid overage disabled unless the user chooses it, and use spending controls if enabled.
- Do not schedule keep-alive prompts as a quota-saving trick; they can consume usage and do not reset limits.


## Concise output and safe tool-result reduction

AI Token Saver now includes Caveman-inspired skill behavior: answer first, trim filler, use concise plain language, and keep every fact needed for correctness. Preserve code, commands, paths, identifiers, numbers, units, and decisive errors exactly. Security warnings, confirmation requests, and persisted content stay clear and complete.

A host integration may shorten noisy logs, diffs, JSON, or search results only when it keeps the original available and retrievable. The existing Python text compactor does not itself provide a Caveman proxy or arbitrary tool-output compression. See the [Caveman skill](https://github.com/JuliusBrussee/caveman/tree/main/skills/caveman) for the inspiration.

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

## Sub-agent plan (main-model-aware)

`model_router.py` routes sub-agent work through the user's signed-in Claude CLI subscription. It does not require API keys. This routing is only for user-requested sub-agent work. Output-saving behavior is provider-neutral and belongs to the host adapter, not this router.

The main model is always the manager. Pick a mode per task:

| Mode | Behavior |
|---|---|
| auto (default) | Scores solo / one-model / mix on quality, cost, speed and main-model tokens; picks the best for `--prefer` (default `balanced`) |
| solo | No sub-agents; the main model does it |
| one | One sub-agent model (`--model`; default Opus->Sonnet, Sonnet->Haiku) |
| mix | Best model per tier (Haiku/Sonnet/Opus); ultra adds Sonnet draft + Opus verifier |
| router | Advice only: best model and what the main model should do |

Any main model can use any mode and any sub-agent model (e.g. Opus with Haiku, Sonnet with Opus, Haiku solo/mix/one). `auto` is the default for every main model: it drops plans below a quality floor, then scores the rest (balanced = quality 0.5, cost 0.2, speed 0.2, main tokens 0.1; also `quality`, `cheap`, `fast`, `tokens`) and reports the choice and main-model tokens saved. Models are the latest of each family. Cost/speed/quality figures are relative estimates in `model_router.py`, not live prices.

Executor effort follows the task tier (low / medium / high; ultra work runs at high). Set the main model with `--main` or `AITS_MAIN_MODEL` (default `sonnet`) and the mode with `--mode` or `AITS_SUBAGENT_MODE`; override aliases with `AITS_OPUS_MODEL`, `AITS_SONNET_MODEL`, `AITS_HAIKU_MODEL`. Examples: `python delegate.py --kind edit --main opus --prompt-file task.txt` (default), `--main sonnet --mode one --model opus`, `--main haiku --mode mix`, `--mode solo`, `--mode router`. Models, aliases, and subscription limits may change.

## Output levels

`provider_adapter.prepare_request(state, request, output_level=...)` selects how terse the reply instruction is: `standard` (default), `tight` (short plain sentences, no recap), or `max` (result only: the code, command, value, or diff, plus one full-sentence line for any blocker or warning). Every level keeps grammar, exact technical payloads, and full-sentence warnings, so it never degrades into telegraphic "caveman" speech, and this skill takes precedence if such a skill is also active. Savings depend on the task: large when the answer is a command or patch, small when it needs explanation. They are never guaranteed.

## Measuring savings

`python benchmarks/e2e_savings.py [--json]` reports, per workload, context tokens (raw vs compacted), input tokens (raw vs the prepared request, including the output-style line), the sub-agent plan the `auto` optimizer picks, and the modeled main-model token saving. It runs offline. Reply (output) tokens depend on a live model and are not measured; the report shows only how many tokens each output level adds to the prompt. Savings vary by workload, from about 99% on heavily repeated history to roughly 0% on distinct text, and are never guaranteed.

## Processing levels and limits

Compaction is split into levels, and redaction is kept apart from all of them:

| Level | What it does | Lossless? |
|---|---|---|
| Normalisation | Line endings (`\r\n`, `\r`) become `\n`; only these three are line breaks, so U+2028, form feeds and similar stay in the text | Yes, apart from line endings |
| Conservative (default) | Drops runs of blank lines beyond one paragraph break and consecutive duplicate prose lines. Code, JSON, log/event records, list items and `key: value` lines are never deduplicated; code keeps its blank lines exactly | No |
| Intentionally lossy | `aggressive=True` removes any repeated prose line (same protections as above) | No |
| Redaction | Replaces credentials with `[REDACTED]`. Quoted values keep their quotes so JSON and Python stay parseable; calls, attribute access, subscripts and `$VAR` references (`password = get_pw()`) are left alone | No, never counted as lossless |

`compact_text` and `compact_stream` use one engine, so for any chunking, including one character at a time and splits inside `\r\n`, streaming output equals batch output. When the final input line is a removed duplicate and the input has no final newline, the output ends with one newline because a stream cannot take back a newline it already sent.

`RealtimeUsageSaver(..., suppress_unchanged=True)` holds output until `finish()` and emits nothing when the input matches the saved fingerprint. The default still streams immediately and reports repetition through `result.changed`.

Known limits: a bare unquoted identifier assigned to a secret key outside a call (`password = hunter2`) is redacted, because it cannot be told apart from a `.env` secret. Redaction matches key names, not values, so a secret under another name is not found. Detection of code and log lines is heuristic. `python benchmarks/audit_compare.py` compares token counts, time and peak memory against a baseline git ref.
