# AI Token Saver

A compact, model-agnostic token and context-saving tool designed to work with **any AI assistant or coding agent** that supports custom instructions, skills, memory, or context files.

## What it does

AI Token Saver performs **real, measured compaction**. By default it **returns the input unchanged**: every line, blank line, indentation and line ending (`\n`, `\r\n`, `\r`) stays as it was, because a repeated line can be a separate event, instruction or message and whitespace can be meaningful (YAML block scalars, CSV quoted fields, Markdown, Python). Removing repeats is opt-in through `dedupe=`: `"runs"` replaces a long run of identical lines by the line plus a count and is **exactly reversible** with `expand_runs`, while `"adjacent"` and `"global"` (and `aggressive=True`) are **explicitly lossy**. Code, structured data, Markdown structure, list items and log/event records are never touched in any mode.

It also supports **real-time incremental compaction**: chunks can be fed as they arrive, and newly completed safe lines are emitted immediately instead of waiting for the complete input.

For highly repetitive or padded input, the implementation can sometimes reach **around or above 99% reduction**. **99% is not a guaranteed result for every input**—if the input contains little redundancy, the real saving will be much smaller. The tool never deletes information just to make the percentage look better.

It provides:

- 🧠 Compact project-memory structures
- 🛡️ Code-aware, information-preserving by default; repeated-line removal is opt-in
- ⚡ Real-time incremental/streaming compaction
- 📦 Stable, structured JSON memory storage
- 🔀 Memory merging and deduplication
- 📏 Before/after token measurement with either a supplied tokenizer or an explicit approximate fallback
- 🤖 Model/provider-agnostic skill instructions
- 🔌 Designed to adapt to different AI assistants and coding agents
- 🔁 Reversible `runs` compression (`expand_runs(compact_text(x, dedupe="runs")) == x` for any string)
- 🧾 Your text is never rewritten by credential detection: API keys, passwords and config values pass through as written

## Safety-first compaction

The default mode is intentionally conservative:

- The default (`dedupe="off"`) removes **no line**. Repeated lines such as `Payment received`, `Turn left` or `The project is ready.` may be separate events, instructions or messages, and punctuation or keywords cannot tell them apart from padding.
- `dedupe="runs"` is safe: a long run of identical consecutive prose lines becomes the line plus `[previous line repeated N more times]`, only when that is shorter, so the count survives, and `expand_runs` rebuilds the original exactly.
- `dedupe="adjacent"` and `dedupe="global"` (the same as `aggressive=True`) are **lossy**: they drop repeated prose lines and the repeat count is gone.
- Code, commands, closing braces, paths, JSON/YAML, SQL, Markdown headings, tables, quotes and list items, `key: value` lines, logs and other event records are **never** changed by any mode, even when they appear before any line that proves the input is code.
- Credentials, API keys and config values are never detected, masked or rewritten (see [Credentials](#credentials-and-configuration-values)).
- Indentation, speaker labels, message boundaries and chronological order are preserved.
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

## Credentials and configuration values

AI Token Saver is a token and context optimisation tool, not a secret manager. It does not detect, mask or replace credentials: API keys, passwords, tokens, connection strings and private keys in the text you give it come out exactly as they went in (there is no `[REDACTED]` substitution, no secret scanner and no `redaction.py`). The old `redact_secrets=` and `redaction_mode=` arguments are still accepted so existing code keeps working, but they are ignored. Savers that persist state (`ContextSaver`, `UsageCheckpoint`) store the values you give them as given; keep what you do not want written to disk out of the state you save. Nothing is logged, published or sent anywhere by this library, and it needs no API key or login.

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
├── ai-token-saver.zip        # ready-to-install skill package (SKILL.md plus the Python modules)
├── ai_token_saver.py         # core compaction engine (Python API)
├── context_saver.py          # context snapshots
├── usage_saver.py            # idempotent usage checkpoints
├── realtime_usage_saver.py   # real-time incremental saver
├── provider_adapter.py       # provider-neutral integration and output levels
├── providers.py              # provider/tier catalog for sub-agents
├── model_router.py           # sub-agent routing and auto optimizer
├── delegate.py               # command-line runner for routed sub-agents
├── benchmarks/               # benchmark runner, savings, audit, compression and stress benchmarks
├── tests/                    # test suite
└── .github/workflows/        # CI (tests.yml)
```

## Installing the skill

`ai-token-saver.zip` in the repository root is the packaged skill: a single `ai-token-saver/` folder holding `SKILL.md` and the Python modules (no `redaction.py`). Upload it wherever your assistant accepts a skill package (for example Claude's Skills settings), or unzip it into the assistant's skills directory. It is rebuilt from `main` when the code changes; the zip is not needed to use the Python library.

## Quick start

```bash
git clone https://github.com/yazaneva4/AI-token-saver.git
cd AI-token-saver
```

`ai_token_saver.py` is a Python library with no command-line interface. See
[Python usage](#python-usage) below. Without a supplied model tokenizer, token
measurements are labeled approximate.

To remove repeated lines, pass `dedupe="runs"` (keeps a count) or the lossy `dedupe="adjacent"` / `aggressive=True`.
Technical-looking content remains protected.

## Python usage

```python
from ai_token_saver import Memory, compact_text, compact_text_with_metrics, expand_runs, memory_to_text, reduction

text = """We need to save the project state.
We need to save the project state.
We need to save the project state.
OpenSpark is the current project.
"""

print(compact_text(text) == text)  # True: the default returns the text unchanged
compacted = compact_text(text, dedupe="runs")  # exactly reversible
print(compacted)
print(expand_runs(compacted) == text)  # True
print(f"Reduction: {reduction(text, compacted):.1%}")

result = compact_text_with_metrics(text, dedupe="runs")
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

The test suite covers the repeated-line modes, code preservation, aggressive-mode
safety, newline preservation, exact/approximate token measurement, reduction bounds,
memory merging, JSON round-tripping, malformed-memory handling, exact `runs` round trips, preserved credentials and whitespace,
real-time chunked compaction at arbitrary boundaries, CRLF chunks, bounded memory, and input validation.

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

Text compaction does not touch credentials and is not a credential manager. Saved
memory and context files are written to disk exactly as given, so do not put values
in them that must not be stored.

## Status

Early / experimental implementation (Round 4: no redaction, default identity, reversible `runs`). Token counting is approximate unless a trusted
model-specific tokenizer or token-counting function is supplied. Exact accounting
still depends on the supplied tokenizer matching the target model.

## Sub-agent plan (main-model-aware)

`model_router.py` routes sub-agent work through the user's signed-in CLIs (Claude, Codex/GPT, or custom). It does not require API keys. This routing is only for user-requested sub-agent work. Output-saving behavior is provider-neutral and belongs to the host adapter, not this router.

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

Compaction is split into levels:

| Level | What it does | Lossless? |
|---|---|---|
| Default (`dedupe="off"`) | Identity: returns the text unchanged, including blank lines, indentation, trailing spaces and the original line endings. Only `\n`, `\r\n` and `\r` are line breaks, so U+2028, form feeds and similar stay in the text | Yes, byte for byte |
| `dedupe="runs"` | A long run of identical consecutive **prose** lines becomes the line plus `[previous line repeated N more times]`, only when that is shorter. Never applied to code, structured data, Markdown structure, list items, paths, counts or log/event records | Yes, exactly: `expand_runs(compact_text(x, dedupe="runs")) == x` for every string. A run needs the same text **and** the same line ending, an input line that looks like a marker is given one extra leading backslash (removed again by `expand_runs`), and so compacting already compacted text a second time is not a no-op |
| `dedupe="adjacent"` | Drops a prose line identical to the previous one | **No: lossy**, the repeat count is lost |
| `dedupe="global"` / `aggressive=True` | Drops any repeated prose line anywhere | **No: lossy** |

`compact_text` and `compact_stream` use one engine, so for any chunking, including one character at a time and splits inside `\r\n`, streaming output equals batch output. In the default mode the stream simply echoes each chunk. In the other modes a trailing `\r` is held until the next chunk shows whether it is a `\r\n`. When the final input line is a removed duplicate and the input has no final newline, the output ends with the previous line's ending because a stream cannot take back a newline it already sent. Aggressive-mode idempotence is as below. Aggressive mode decides over a 4-line lookahead window, so a second pass may remove more but never adds content.

`RealtimeUsageSaver(..., suppress_unchanged=True)` holds output until `finish()` and emits nothing when the input matches the saved fingerprint (the held output grows with the input). The default still streams immediately and reports repetition through `result.changed`.

## Reliability notes

- **Memory files** (`save_memory`) are written atomically: a failed or interrupted save leaves the previous file intact, an existing file keeps its permissions, and a symlink is written through. `memory_to_text` indents continuation lines of a multi-line entry, so an entry cannot pose as a section header or another bullet. `Memory.from_dict` ignores booleans, NaN/infinity, nulls and containers in list fields.
- **Fingerprints** of sets are independent of the process hash seed. `RealtimeUsageSaver` fingerprints now include the `dedupe` mode (format v3, since redaction was removed), so state saved by an older version counts as changed once. A `state_path` that is a directory is rejected up front.
- **Custom providers** (`AITS_CUSTOM_PROVIDERS`): only `{model}` and `{effort}` are placeholders in a `cmd` template; every other brace is literal and there is no `{{ }}` escaping. The variable defines commands that will be run, so treat it as trusted configuration. A non-object provider spec or a non-string `cmd` is a `ValueError`.
- **`delegate.py`** reports unreadable input files as `delegate: ...` with exit code 1, accepts `--dedupe off|runs|adjacent|global`, and `route()` rejects a non-string task kind with `TypeError`.
- **Options** are validated the same way everywhere, including for empty input and for `compact_stream` before its first `next()` (`dedupe` must be one of `off|runs|adjacent|global`, `tokenizer` a callable or an object with `encode`). `RealtimeCompactor(retain=False)` and `RealtimeUsageSaver(retain=False)` keep neither the input nor the output (constant memory; `original`/`compacted`/`result()` then raise or are `None`); `compact_stream` always runs that way, and the usage saver fingerprints the stream incrementally instead of keeping a copy.
- **Memory use**: per-line classification is cached only for short lines, and `dedupe="global"` remembers long lines as 16-byte digests, so a stream of long unique lines is not retained.

## Measured results (read before quoting a percentage)

`python benchmarks/compression_round2.py` compacts ten datasets (about 1 MB each) four ways and counts tokens with the Tekken BPE tokenizer (a real subword tokenizer, **not Claude's**). "Intact" means every line and its repeat count is still present; "lossless" for `runs` means expanding the markers reproduces the input exactly.

| Dataset | default | `runs` (lossless) | `adjacent` (lossy, lines dropped) |
|---|---|---|---|
| 16,000 identical lines, **synthetic best case** (180,323 tokens) | 0.00%, intact | 99.99% | 99.99% (16,392) |
| Retry/poll output (repeated status lines, 193,020 tokens) | 0.00%, intact | 98.18% | 98.94% (26,584) |
| Coding-agent transcript, Python, JavaScript, project memory, JSON, YAML, multilingual | 0.00%, intact | 0.00% | 0.00% (0) |
| Non-repetitive prose | 0.00%, intact | 0.00% | 0.00% |

So: **99.8% and above is a best case that exists only for pure repetition**, and the default never claims it, because the default removes nothing. Typical coding-agent text, source code, JSON and YAML contain no adjacent repeated prose and save about 0% in every mode; real savings there would need a different technique. Parsed Python, JSON and YAML are identical to the input in every mode. An earlier engine reported extra savings on JSON only by deleting equal neighbouring values, which changes the data.

`python benchmarks/stress_round2.py [--dedupe MODE] [--engine-dir DIR]` runs 69 bounded cases (1 KB to 100 MB, one-character chunks, random chunking, malformed input, 100,000 repeated lines, threads) in separate subprocesses with an 8 GB cap. On the reference machine all 69 pass in every mode; 100 MB inputs take 5 to 34 s (about 3 to 10 MB/s; see below) with working memory of roughly 3 times the input. `python benchmarks/audit_compare.py` compares against a git baseline.

**Round 4 stress comparison** (63 cases up to 10 MB, `--max-mb 10`, same machine, run against the previous `main` with `--engine-dir`; all cases pass in every mode): total time default 46.9 s → 1.1 s (the default is now a pass-through), `runs` 46.6 s → 32.0 s, `adjacent` 46.3 s → 31.1 s; worst-case working memory above the input 188 MB → 74 MB (default), 153 MB → 93 MB (`runs`), 153 MB → 94 MB (`adjacent`). Part of the line-based speedup is that redaction no longer runs. Python 3.10, 3.11, 3.12 and 3.13: 3367 tests pass on each.

## Other agents and providers (GPT, Gemini, local models)

Tiers are labels matched by model name, not a power ranking across vendors: nothing here judges whether a GPT model is stronger than a Claude model. The tiers are provider-neutral: Haiku = light, Sonnet = standard, Opus = deep. `--main gpt-5` (or `AITS_MAIN_MODEL`) places the main model in a tier by name, and sub-agents come from the main model's *own* provider and its own tier models, even when other providers' CLIs are installed (a GPT main keeps to GPT tiers, a Claude main to Claude tiers). Another provider is used only when the main model's provider has no model, matched by tier. A tier the own provider lacks falls back to its nearest tier; with no provider the main model works alone, and no Claude model is used when Claude is not available.

| Setting | Meaning |
|---|---|
| `AITS_PROVIDERS` / `--providers` | Providers in preference order. Default: detect installed `claude` and `codex` CLIs, else `claude` |
| `AITS_<PROVIDER>_<LIGHT\|STANDARD\|DEEP>_MODEL` | Model for a tier, e.g. `AITS_CODEX_DEEP_MODEL=...`. Codex uses its own default model for the standard tier |
| `AITS_CUSTOM_PROVIDERS` | JSON such as `{"mycli": {"cmd": "mycli --model {model} --effort {effort}", "light": "...", "deep": "..."}}`; the prompt goes on stdin |

Python hosts can pass the models they can reach directly: `route("edit", main="gpt-5", providers={"codex": {"light": "...", "standard": "...", "deep": "..."}})`. Model names change often, so none are hard-coded beyond Claude's aliases. Tier placement is a name heuristic, so check `route(...).steps` for an unusual model id.
