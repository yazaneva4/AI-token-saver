# Workflow, concise output and savings (full text)

Loaded on demand from SKILL.md.

## Everyday Token-Saving Workflow

Use this workflow when the user asks to save, carry forward, or reduce context. For ordinary tasks, apply the concise-response rules below without announcing token optimization.

1. **Keep only useful context.** Include the current goal, constraints, confirmed decisions, exact technical facts, unresolved blockers, and next action. Omit resolved discussion, repeated explanations, and unrelated history.
2. **Update by delta.** Add new or changed facts to the existing canonical state; do not resend or regenerate unchanged history. Keep superseded values only when they explain a decision or migration.
3. **Reuse accessible sources.** Refer to an existing file, project, or stable source instead of pasting it again when the host can access it. Never assume retrieval or caching is free.
4. **Right-size each turn.** Batch related requests; keep unrelated work separate. Ask only for missing information that materially changes the result. Avoid unnecessary acknowledgements, repeated summaries, tool calls, and agent delegation.
5. **Use the least costly adequate capability.** Select model effort and tools based on task difficulty; use stronger reasoning, browsing, or delegation only when it improves correctness or outcomes.
6. **Measure honestly.** Prefer the provider's meter or a tokenizer matching the target model. Label all other counts approximate. Report actual savings; never target a percentage by deleting meaning.
7. **Respect provider limits.** Check current provider usage windows and documented features. Caching, off-peak use, quotas, and model costs vary. Keep paid overage disabled unless the user explicitly chooses it. Keep-alive prompts consume usage and do not reset limits.

These practices can reduce avoidable context and output; they cannot change provider quotas, guarantee savings on a particular request, or make the skill itself free to load.

## Concise Responses and Safe Tool-Output Reduction

Use concise, answer-first language to reduce unnecessary output tokens, while
keeping every fact needed to act correctly.

- Remove greetings, repeated summaries, filler, and unnecessary explanations.
- Use short, plain sentences. Clarity wins whenever compression could confuse.
- Keep negations, conditions, order, warnings, and qualifications explicit.
- Preserve code, commands, paths, identifiers, numbers, units, API names, and
  decisive error text exactly. Never rewrite exact technical payloads to save
  tokens.
- For tool output, show the smallest useful evidence: decisive errors, changed
  lines, relevant result fields, and clear status. Do not omit information that
  affects correctness or a decision.
- Only integrations that explicitly support source-preserving compaction may
  shorten logs, diffs, JSON, or search results before model context. Keep the
  original available locally and provide a stable way to retrieve it. Never
  claim that the current text compactor performs this transformation.
- State security warnings and confirmation requests in full, clear sentences.
  Use plain, complete wording for content persisted outside chat, including
  code comments, docs, commits, memory, and messages.
- Repeated lines are kept unless the user opts in. Even in the opt-in modes only plain prose lines are touched; compaction never removes code,
  JSON/YAML, Markdown structure, list items, `key: value` lines, shell commands, or
  log/event records. The default returns the text unchanged, credentials and
  configuration values are never masked or rewritten, and only `dedupe="runs"` is
  described as lossless (it is exactly reversible with `expand_runs`).
- Report measured savings only. Realistic code, logs and transcripts usually save
  well under 1%; a figure near 99% describes pure repetition and nothing else.
- Do not imitate caveman grammar or use invented abbreviations. Save words,
  never meaning. If a caveman-style or other telegraphic-speech skill is also
  active, this skill takes precedence: write in plain grammatical language, and
  never use telegraphic style for warnings, errors, commits, docs, or memory.

### Output levels (choose the lowest that serves the request)

| Level | Behavior | Typical use |
|---|---|---|
| standard | Answer first; drop filler and recaps | default |
| tight | Short plain sentences; no preamble, recap, or offers of more help | status updates, explanations |
| max | Result only: the code, command, value, or diff; one full-sentence line for a blocker or warning | when the answer is the artifact |

At `max`, savings can exceed 90% on tasks whose answer is a command, value, or
patch, because the explanation is the only thing removed. They are small on tasks
that need explanation. Never exceed what the user's requested detail allows, and
never drop error text, security warnings, or confirmation requests at any level.
Hosts select the level with `prepare_request(..., output_level=...)`.

### How savings reach up to 99%

Real reductions come from not sending or generating tokens, not from deleting meaning:

- **Context:** send deltas and stable references instead of repeating history;
  offload bulky work to a cheaper sub-agent so the main context holds only the
  result (the `auto` optimizer reports main-model tokens saved); compact repeated
  or padded text with the deterministic compactor.
- **Output:** use the lowest output level that serves the request; return the
  artifact, not a narration of it.

Reductions near 99% happen on highly repetitive input or result-only answers; they
are never promised. Measure with the provider's meter or a matching tokenizer and
report the actual number.

Provider-neutral host integrations can include the compact answer-style instruction from `provider_adapter.py` before generation. It steers the assistant toward concise output while preserving explicit detail requirements; it cannot enforce a length or guarantee a reduction.

This is an AI instruction-layer behavior. It does not add a tool-output proxy or change the deterministic Python compaction algorithm by itself.
