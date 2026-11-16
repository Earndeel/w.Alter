# Context-bloat audit reference — 2026-08

Session-specific evidence and implementation guardrails for the class-level payload-slimming workflow. This file records what was measured and what was actually verified; it is not a claim of provider-wire parity.

## Baseline evidence

The audited `state.db` session contained 134 messages and 98 tool calls. Raw `role=tool` content totalled 660,359 characters (roughly 165,114 chars/4 tokens). The largest single result was 104,376 characters. All 134 rows had `active=1` and `compacted=0`; those flags described the raw ledger and did not prove what the provider received.

The provider-facing truth was obtained by reconstructing the request-local message copy and, in the live code, by instrumenting the common seam after `_build_api_kwargs()` and request middleware but before transport dispatch. The report is deliberately bounded and records category overlays plus the ten largest elements.

## Correct architecture

- `state.db` remains the immutable/raw ledger for audit and exact recall.
- `api_messages` is a request-local copy. Never mutate the persisted transcript to save tokens.
- Apply `slim_prompt_history(agent, api_messages)` after context selection, orphan/thinking cleanup, whitespace/tool-call normalization, and before prompt-cache decoration/provider kwargs assembly.
- A helper that is not imported by the live loop is only a test artifact; require an end-to-end digest-on-wire test.

## Tool-result policy

Use these defaults as starting points, not universal constants:

- inline result: <= 1,200 chars;
- pending huge result: digest plus short excerpt, capped at 4,000 chars;
- consumed result: digest with tool name, call id, status/summary, `state_ref`, and `raw_available_in_state_db: true`;
- whole tool working set: hard cap 12,000 chars in the provider copy.

Important edge cases:

1. The first pending `skill_view` result must remain readable once so the model can consume the instructions. It becomes digest-eligible after a later assistant turn.
2. Pre-existing digest strings from a previous retry must still be tracked as tool records. Otherwise a second projection can bypass the working-set cap.
3. If normal digests still exceed the cap, collapse the oldest entries to one-line references or omission markers. The raw bytes remain in the ledger.
4. Deep-copy nested message structures before slimming; a shallow outer copy can mutate nested content parts or image data in the canonical history.
5. Preserve assistant `tool_calls` and tool `tool_call_id` pairing; only replace prompt-view content.

## Measured reconstruction

On the audited session, the request-local reconstruction changed:

| metric | raw ledger view | slim provider view |
|---|---:|---:|
| total messages-only estimate | 189,849 tokens | 20,010 tokens |
| tool-result chars | 660,359 | 11,898 |
| loaded `skill_view` chars | 173,133 | 825 |
| reclaimed tool-result chars | — | 648,461 |

This is a local reconstruction, not a provider usage report. A real request dump and provider usage/cache counters are still required before claiming wire parity or cost savings.

## Context report

Emit `CONTEXT REPORT` at the last common pre-dispatch seam. Use Hermes' existing `estimate_tokens_rough`/chars-per-four estimator when a provider tokenizer is unavailable, and label the method. Category fields such as `skill_index`, `loaded_skill_content`, and `hindsight_memory` are diagnostic overlays; do not sum them again into `TOTAL_INPUT_TOKENS`.

The report must include model limit, output reservation, reserve, system, tool schemas, skills, memory, summary, recent user/assistant messages, tool calls, tool results, current user message, total input tokens, headroom, and ten largest elements. Full sanitized payload dumping stays opt-in.

## Compaction and memory lessons

- A global threshold is not a working-set policy. Use pre-provider rendering bounds plus proactive pruning before the global compactor fires.
- Proactive pruning that rewrites already-sent history breaks prompt-cache prefixes; keep it episodic with a minimum reclaim gate. The request-local prompt view does not have that cache-boundary cost.
- Hindsight should be retrieval, not a permanent dump: cap tokens, deduplicate, apply a conservative relevance floor, and inject zero when no candidate is useful. If the client result type exposes no score, record a clearly labelled local lexical proxy rather than inventing a server score.
- Skill indexes need a character/token budget and a cache key that includes that budget. Full skill bodies remain JIT; the index is registry metadata only.
- If session-memory helpers move modules, keep compatibility wrappers at the old import boundary and add an import-collection regression test. Missing helper exports can prevent the whole suite from collecting.

## Required validation

1. Run the focused regression suite, including prompt-view budget, wire-pruning, skill-index, Hindsight budget, session-memory-layer, and context-report tests.
2. Run `py_compile` on every changed runtime module and `git diff --check`.
3. Reconstruct raw vs provider-view metrics for a real session as a diagnostic.
4. For production claims, enable request dumping, execute a real turn, inspect the post-middleware dump for Chat Completions/Responses/Anthropic shapes, verify `state_ref` exact recall, verify ledger hashes/lengths are unchanged, and compare two consecutive cache-aware turns.
5. Report helper/reconstruction metrics separately from real provider metrics.
