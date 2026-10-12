# Sub-agent plan (full text)

Loaded on demand from SKILL.md.

## Sub-agent Plan (main-model-aware, subscription-backed, no API)

Use the user's already signed-in CLIs (Claude, Codex/GPT, or a custom provider) for
delegated work. Do not require API keys or send tasks to paid API endpoints. If no
CLI is available or signed in, report that clearly and continue directly where
reasonable.

### Any agent, any provider

Tiers are labels matched by model name, not a power comparison between vendors:
this skill never judges whether a GPT model is stronger or weaker than a Claude
model, it only places each model in the tier its own name says.

The tiers are provider-neutral. **Haiku = light, Sonnet = standard, Opus = deep.**
A GPT, Gemini or local main model is placed in a tier by its name (`mini`, `nano`,
`flash`, `lite` = light; `pro`, `ultra`, `max`, `o3` = deep; otherwise standard) and
gets sub-agents from the models actually available, in the same tier as the Claude
model it replaces. Rules:

1. Ask for a tier, not a vendor model. Use the main model's own provider and its own
   tier models, even when other providers' CLIs are installed: a GPT main keeps to
   GPT tiers, a Claude main to Claude tiers. Use another provider only when the main
   model's provider has no model available, matching the tier exactly.
2. If the own provider lacks a tier, use its nearest tier (ties go to the stronger
   one) and say so. If no provider is available, the main model works alone.
3. Never name a Claude model when Claude is not available.
4. Hosts with their own sub-agent tool can skip the CLIs: call `route(..., providers={...})`
   with the models they can reach, then launch the returned tiers themselves.

Configure with `AITS_PROVIDERS` (preference order, default: detect installed `claude`
and `codex`), `AITS_<PROVIDER>_<LIGHT|STANDARD|DEEP>_MODEL` (for example
`AITS_CODEX_DEEP_MODEL`; Codex defaults to its own model for the standard tier), and
`AITS_CUSTOM_PROVIDERS` for any other CLI that reads a prompt on stdin.

The main model is always the manager: it plans, reviews, and owns the final
answer. Pick one sub-agent mode per task:

| Mode | What happens |
|---|---|
| auto (default) | The optimizer scores every plan and picks the best (see below) |
| solo | No sub-agents; the main model does the task itself |
| one | One sub-agent model for the work (any model, set with `--model`) |
| mix | Best model per tier: Haiku (low), Sonnet (medium), Opus (high); ultra adds a Sonnet draft then an Opus verifier |
| router | No execution; names the best model and what the main model should do |

`auto` is the default for every main model. Any main model may also force any
mode and any sub-agent model: Opus may use Haiku, Sonnet may use Opus, Haiku may
go solo, mix, or one-model. All models are the latest of their family (aliases
`opus`, `sonnet`, `haiku` resolve to the newest through the Claude CLI).

### Token-saving optimizer (auto)

The manager picks the setup that best balances output quality, cost, speed, and
main-model token use. Candidates: solo (main alone), one-model with Haiku,
Sonnet, or Opus, and mix (Sonnet drafts, Opus verifies; for high/ultra work).

1. Estimate each plan's quality for the task tier. Manager review lifts a weaker
   single executor part-way toward the manager's quality.
2. Drop any plan under the quality floor (0.85), so cheap never means weak.
3. Score the rest on quality, cost, speed, and main-model tokens. Weights come from
   `--prefer`: `balanced` (default: quality 0.5, cost 0.2, speed 0.2, tokens 0.1),
   `quality`, `cheap`, `fast`, or `tokens`.
4. Run the winner. The result reports the chosen plan, scores, and main-model
   tokens saved versus working solo.

Typical outcome: Haiku for lookups and summaries, Sonnet for edits, Sonnet+Opus mix
for architecture and releases, solo when delegating would cost more than it saves.
The cost, speed, and quality figures are relative estimates in `model_router.py`,
not live prices; retune them there. Set the priority with `AITS_PREFER`.

Executor effort follows the task tier: low (search, lookup, format, summaries),
medium (edits, implementation, tests, docs, analysis, review), high
(architecture, planning, debugging, security, refactors, research, critical
work, releases, migrations, large features/codebases).

Set the main model with `--main` or `AITS_MAIN_MODEL` (default `sonnet`), the
mode with `--mode` or `AITS_SUBAGENT_MODE`. Override aliases with
`AITS_OPUS_MODEL`, `AITS_SONNET_MODEL`, `AITS_HAIKU_MODEL`.

Never add, request, or expose API keys for this workflow. Subscription availability,
model aliases, and usage limits depend on the provider and may change.

### Automated runner

`python delegate.py --kind <kind> --main <opus|sonnet|haiku> [--mode auto|solo|one|mix|router] [--dedupe off|runs|adjacent|global] [--prefer balanced|quality|cheap|fast|tokens] [--model <m>] --prompt-file task.txt [--context-file ctx.txt] [--json]`
compacts context, runs the planned sub-agents (or returns advice for solo/router),
compacts the answer, and prints it (`--json`: tier, main, mode, steps, optimizer detail, tokens in/out). `--main` accepts any
model id (`gpt-5`, `gemini-pro`, ...) and `--providers codex,claude` sets the preference order. Each provider's CLI must be installed and
signed in with the user's subscription.

### Choosing a mode

- Default: `auto`. Override only with a reason:
- Tiny or already-in-context work: `solo`.
- Bulk, well-defined work under a stronger main model: `one` with a cheaper model.
- Mixed workload or one that needs a stronger check: `mix`.
- Main model too weak for the task (Haiku on high-tier work): `router`, then hand off.

### Instructions

1. Clarify intent only when needed; select the mode and tier with `route(...)`.
2. Before delegation, compact and minimize the task context without dropping
   constraints, exact technical facts, or success criteria.
3. The manager gives the executor the task and relevant context, then checks the
   executor's output independently against the user's request before reporting.
4. Do not run multiple agents for work that is simpler or cheaper to complete
   directly.
5. Report the result concisely, with verification status and material limits.

### Intelligent prompting

Subagents see only the context they receive. Include: **Context**, numbered
**Objectives**, **Constraints**, **Output format**, and **Success criteria**.
Name exact files and requested return format. Do not send secrets unless the
user specifically authorized a supported secure secret flow.

### Manual commands

```bash
# One-model sub-agent: Sonnet under an Opus main
claude -p --model sonnet --effort medium < task.txt

# One-model sub-agent: Haiku under a Sonnet main
claude -p --model haiku --effort low < task.txt

# Mix, ultra work: Sonnet drafts, Opus verifies
claude -p --model sonnet --effort high < task.txt > draft.txt
{ printf 'Verify and correct this draft. Return the final answer only.\n\nDRAFT:\n'; cat draft.txt; } |
  claude -p --model opus --effort high
```
