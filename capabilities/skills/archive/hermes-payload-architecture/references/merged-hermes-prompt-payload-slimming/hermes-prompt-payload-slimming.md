---
name: hermes-payload-architecture
category: devops
description: Optimize Hermes LLM payloads by separating raw conversation ledgers from slim prompt-render views, especially oversized tool results and repeated skill_view outputs.
created: 2026-07-04
updated: 2026-07-26
---

# Hermes Prompt Payload Slimming

Use this when Hermes calls become expensive or slow because either:

- recent conversation history is dominated by `role=tool` messages, repeated `skill_view` outputs, large terminal/execute results, or raw tool JSON in the tail; or
- the fixed wire payload is dominated by instructions, the complete skills catalog, and serialized tool schemas even when the user input is tiny.

Start with a whole-wire audit before choosing a remedy. See `references/wire-payload-audit-and-prioritization.md` for evidence hierarchy, payload reconstruction, component measurement, cache analysis, and percent-of-total prioritization.

## Live-runtime audit guardrails

Before recommending deletion or threshold changes:

1. Measure the running session's actual platform resolution, enabled toolsets, model, and working directory. Nominal prompt-size output can describe a different payload than Desktop/Gateway sends.
2. Separate cold fixed layers (`instructions`, repository context, skill index, serialized tools) from dynamic history and tool results.
3. Use provider usage as the authoritative total; use local tokenization only to allocate that total across layers.
4. Inspect the compressor's effective runtime threshold, including provider/model auto-raises and absolute caps. Raw YAML percentages may not be the active threshold.
5. Count provider calls per user message. A healthy cache can still carry an oversized prompt repeatedly; cache-hit percentage alone is not an optimization verdict.
6. Treat project context as task-dependent: keep it for repository engineering and use a neutral workspace for unrelated concierge work.

A dated measured example, including a 38.5K-to-168.6K twelve-call growth trace, live Desktop toolset mismatch, and compression-threshold interpretation, is in `references/runtime-payload-audit-2026-07.md`.

## Principle

Keep two layers separate:

1. Raw ledger: exact complete events for audit and recall.
2. Prompt view: cost-aware render copy sent to the LLM.

Do not delete raw tool results to save tokens. Slim only the prompt-render view.

## Preferred injection point

Apply slimming immediately before provider payload assembly and prompt caching, after the turn has selected `api_messages` for the call.

Pattern:

```python
api_messages = slim_prompt_history(agent, api_messages)
```

This must run before the next LLM request. Historical compaction alone is too late because the newest raw tail can still contain huge tool outputs.

## Tool result rules

Recommended thresholds:

- `TOOL_RESULT_INLINE_MAX = 1200` chars
- `TOOL_RESULT_HARD_CAP_IN_PROMPT = 4000` chars
- `TOOL_ROLE_BUDGET_TARGET = 0.15-0.20`

Rules:

- Keep small tool results inline.
- Replace old consumed large tool results with a digest.
- Keep medium pending tool results raw once for immediate synthesis (`inline_once`).
- After the assistant has answered, future payloads must use digest form.
- For huge pending results, use digest + short excerpt + recall reference even in the current turn.
- Preserve assistant `tool_calls` → `role=tool` adjacency. Only change prompt-view `content`.

Digest should include:

- tool name
- tool_call_id
- status success/error
- short operational summary
- key results, errors, blockers, paths touched
- stable `state_db://session:.../tool_call:...` recall reference
- `raw_available_in_state_db: true`

Keep digest bytes deterministic: do **not** add timestamps or other changing metadata. Treat an existing `[TOOL RESULT DIGEST]` / `[SKILL ALREADY LOADED]` block as immutable so retries and later prompt builds cannot digest a digest and invalidate the prompt-cache prefix. Exact recall should resolve the reference directly (for example `session_search(state_ref=...)`) without loading or searching the whole session.

## skill_view special case

`skill_view` can dominate the prompt because skills are long and stable within a session. The first pending load must remain raw once, regardless of size: slimming instructions before the model has read them defeats the skill contract. After any later assistant turn, replace that consumed output with a digest; repeated loads of the same skill can use `[SKILL ALREADY LOADED]` immediately.

Maintain a per-session loaded-skill registry when available with:

- skill name
- version hash
- loaded_at
- source message id
- recall reference
- short digest
- relevant sections

If a skill is already loaded, render only:

```text
[SKILL ALREADY LOADED]
name: ...
version_hash: ...
state_ref: ...
digest: ...
raw_available_in_state_db: true
```

Never keep full long skill content in the prompt tail across later turns.

## Budget-aware second pass

### Lessons from the 2026-08 payload-bloat implementation
- Treat `state.db` flags (`active`, `compacted`) as ledger metadata, not proof of provider payload size. Verify the actual post-middleware request at the provider assembly boundary.
- The shared measurement seam is the live loop after `_build_api_kwargs()` and LLM request middleware, before transport dispatch. Emit a bounded context report there; keep full sanitized payload dumping opt-in.
- Preserve raw results in the ledger, but always render a copied provider view. A helper that is not imported by the live loop is only a test artifact; require an end-to-end test for digest-on-wire plus raw-in-ledger.
- Use a hard working-set budget in addition to per-result caps. If the first reduction pass still exceeds budget, collapse the oldest consumed results to one-line `state_db://` references; do not exempt old consumed `skill_view` bodies from the budget.
- Benchmark reconstructed payloads as a diagnostic only. A real provider request dump and provider usage/cache comparison are required before claiming wire parity or cost savings.
- Track pre-existing digest strings as working-set records on every retry; otherwise a second render pass can bypass the cap even though the source ledger is unchanged.
- Deep-copy nested message structures before rendering. A shallow outer copy can mutate nested content parts or image data in the canonical history.
- Keep the first pending `skill_view` readable exactly once; if the hard budget is under pressure, evict older consumed results before that first-load skill content.

Before the provider call, estimate payload size by role. If `role=tool` exceeds target budget:

1. Digest all consumed oversized tool results.
2. Deduplicate repeated `skill_view` outputs.
3. Move evidence into a compact tool evidence section or one-line digests.
4. Keep only recall references for old raw outputs.

Record metrics on the agent/session for inspection:

- total estimated tokens
- role chars/tokens and percentages
- top 10 largest messages
- top tool results by size
- number of full skill_view payloads
- number of digests
- number of recall references

## Tests to require

- large tool result is not re-injected raw while source transcript remains raw
- repeated skill_view is deduped
- long skill_view is slimmed with recall reference
- current-turn inline-once then digest after assistant response
- huge current-turn result uses digest + excerpt
- tool role stays under budget on many tool messages
- static prefix contains no dynamic timestamp/session/model/provider metadata
- rendering is byte-idempotent: a digest remains exactly unchanged on every later prompt build
- `state_ref` exact recall returns byte-identical persisted raw content, including compacted/inactive rows

## Pitfalls

- Do not mutate persisted/raw conversation rows for token savings.
- Do not break provider tool-call protocol pairs.
- Do not rely on compression alone; the render layer must slim before the next payload.
- Do not put session summaries or implementation notes into memory files; keep procedure here and session specifics in references.
- When `token_count` is NULL in `state.db` (common in older sessions), boundary calculations rely on rough char-based estimates — less precise, but the role breakdown remains directionally correct.

See `references/prompt-view-tool-result-slimming.md` for a concrete implementation recipe and measurement checklist.

For payload composition measurement from live sessions and ContextCompressor bug patterns (IndexError on all-tool middle), see also the companion skill `hermes-context-management`.
