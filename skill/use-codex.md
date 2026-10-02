---
name: use-codex
display_name: Use Codex
description: Route delegated work by size. High work stays on the latest Sonnet, medium work goes to Together, small work and image generation go to GPT luna through the Codex CLI. Use when the user says "use codex", "ask codex", "get a codex second opinion", "compare codex vs claude", "have two agents try it", or asks for a large coding task (research, multi-file refactors, large codebase analysis).
---

# Codex Subagent Skill (tiered routing)

Spawn autonomous subagents to offload context-heavy work. Subagents burn their own tokens and return only their final message, so the parent's context stays clean.

**Golden Rule:** If task + intermediate work would add 3,000+ tokens to parent context → use a subagent.

## Model tiers

| Tier | Work | Model | Runner |
|------|------|-------|--------|
| high | architecture, planning, hard debugging, security, multi-file refactors, long research | latest Sonnet (`claude-sonnet-5-5`) | the parent Claude / Anthropic API |
| medium | normal edits, implementation, review, tests, docs, analysis | Together (`AITS_MEDIUM_MODEL`) | Together chat API |
| small | search, lookup, fetch, rename, formatting, summaries, **image generation** | GPT luna (`luna`) | Codex CLI, `low` reasoning |

`model_router.py` implements this table: `route(kind, tokens=...)` returns the tier, provider, model and (for Codex) the exact command. Override model ids with `AITS_HIGH_MODEL`, `AITS_MEDIUM_MODEL`, `AITS_SMALL_MODEL`; provider model names change. `AITS_MEDIUM_MODEL` has no default and must be set.

## Instructions

1. **Clarify intent.** Infer from inline args; ask only if unclear. Buckets: second-opinion review, refactor, plan validation, feature implementation, fresh perspective on a stuck bug, parallel comparison.
2. **Pick the tier** with `route(...)` using the table above. When unsure, go one tier up.
3. **Spawn the subagent** with the invocation for that tier (below). Pipe long prompts via stdin.
4. **Act autonomously while it runs.** Pause only for destructive operations (data loss, external impact, security).
5. **Monitor, don't fire-and-forget.** Check completion, verify quality, retry on failure. Parallel and sequential subagents are fine.
6. **Present results, don't dump them.** Summarize in your own words, surface concrete changes, leave the next move to the user. Subagent output is input for your synthesis.

## Intelligent prompting

Subagents only see what you give them. Always include: **Context**, numbered **Objectives**, **Constraints** (focus / ignore), **Output format**, **Success criteria**.

```
[TASK CONTEXT] You are researching/analyzing/coding [TOPIC].
[OBJECTIVES] 1. ... 2. ...
[CONSTRAINTS] - Focus on: ... - Ignore: ...
[OUTPUT FORMAT] Return: ...
[SUCCESS CRITERIA] Complete when: ...
```

Vague prompts ("Research authentication") produce vague work. Name the directories, the questions, and the exact return shape ("Return as a markdown table: method, path, auth, schemas").

## Invocations

**Small tier (Codex CLI, GPT luna).** Pipe the prompt via stdin with `-`; capture output with `-o`:

```bash
cat <<'EOF' | codex exec --yolo --skip-git-repo-check \
  -m luna -c 'model_reasoning_effort="low"' \
  -o /tmp/codex-result.txt -
[TASK CONTEXT] ...
EOF
result=$(cat /tmp/codex-result.txt)
```

Use `--json` instead of `-o` only for machine-parsable output (`jq -r 'select(.event=="turn.completed") | .content'`). For image generation use the same command with a prompt that asks for the image file path as the return value.

**Medium tier (Together).** OpenAI-compatible endpoint; `TOGETHER_API_KEY` stays in the environment, never in prompts or saved context:

```bash
jq -n --arg m "$AITS_MEDIUM_MODEL" --rawfile p /tmp/prompt.txt \
  '{model:$m,messages:[{role:"user",content:$p}]}' |
curl -sS https://api.together.xyz/v1/chat/completions \
  -H "Authorization: Bearer $TOGETHER_API_KEY" -H 'Content-Type: application/json' \
  -d @- | jq -r '.choices[0].message.content' > /tmp/together-result.txt
```

**High tier (latest Sonnet).** Do the work in the parent, or dispatch a Sonnet subagent with the host's own subagent tool.

## Parallel subagents

Each subagent writes its own output file; `wait`, then read all:

```bash
cat <<'EOF' | codex exec --yolo --skip-git-repo-check -m luna -c 'model_reasoning_effort="low"' -o /tmp/agent-a.txt - &
Approach A: ... Return diff + rationale.
EOF
cat <<'EOF' | codex exec --yolo --skip-git-repo-check -m luna -c 'model_reasoning_effort="low"' -o /tmp/agent-b.txt - &
Approach B: ... Return diff + rationale.
EOF
wait
```

Give both the same problem under different framings, then synthesize the better answer in the parent. Tiers can be mixed.

## Sequential subagents

call → read → decide → call. The parent composes each prompt fresh from what just landed. Always use a quoted heredoc (`<<'EOF'`) and `cat` prior output on stdin; never interpolate `$STEP_N` into an unquoted heredoc, because model output often contains backticks and `$()` that bash would execute.

```bash
{ cat <<'EOF'
Review the changes summarized below for security holes. Return: issues + line refs.

[PRIOR WORK]
EOF
cat /tmp/codex-step-1.txt; } | codex exec --yolo --skip-git-repo-check -m luna -o /tmp/codex-step-2.txt -
```

Upgrade the tier for a review or fix pass if the first result was weak.
