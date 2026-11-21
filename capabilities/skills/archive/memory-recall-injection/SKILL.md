---
name: memory-recall-injection
category: devops
description: "Use when auditing memory injection: relevance, budgets."
version: 1.0.0
author: hermes
license: MIT
created: 2026-08-17
metadata:
  tags: [memory, hindsight, recall, prefetch, injection, token-budget, relevance]
  related_skills: [hindsight-qdrant-hybrid-search, hindsight-debug-and-repair, hermes-memory-plugin]
---

# Memory Recall → Context Injection

Class-level map of how external memory providers' recalled content actually reaches
the LLM in Hermes, who enforces what (server vs client), and where to make changes
when the user asks for "targeted retrieval with a hard token budget and relevance
threshold". Verified against the working tree on 2026-08-17.

## When to Use

- Auditing or tuning why/when recalled memory (Hindsight, Honcho, Mem0, Qdrant
  hybrid-search) appears or doesn't appear in agent context.
- Implementing "targeted retrieval with a hard token budget and relevance
  threshold" against any memory provider.
- Tracing where memory retention on compression happens (or doesn't).
- Routing between Hindsight PG recall (8888, no scores) and Qdrant
  hybrid-search / memory-gateway (8889, scored).

## Architecture: two injection surfaces, not one

- **System prompt — STATIC only.** `agent/system_prompt.py:534-541` appends
  `agent._memory_manager.build_system_prompt()` (agent/memory_manager.py:486-503,
  joins each provider's `system_prompt_block()`). For Hindsight that is a fixed
  "# Hindsight Memory" header (plugin `__init__.py:1694-1714`) — **no retrieved
  content ever goes through the system prompt**.
- **User message — the ONLY per-turn injection point.** The prologue in
  `agent/turn_context.py:1264-1271` runs `prefetch_all()` and the result is
  wrapped in a `<memory-context>` fence + system note
  (`agent/memory_manager.py:347-361`) and **appended to the API copy of the user
  message**, never the stored content (`agent/turn_context.py:77-85`,
  `compose_user_api_content`). The stored message stays clean; the sidecar
  `api_content` persists the exact sent bytes (prompt-cache invariant).

## Prefetch data flow

1. **Gate:** per-turn `prefetch_all` runs only when
   `not is_trivial_prompt(query)` — `agent/turn_context.py:1268` and the post-turn
   mirror `run_agent.py:4231`. `TRIVIAL_PROMPT_RE` is the single source of truth
   (`agent/memory_provider.py:52-78`). Bare greetings/acks/slash-commands skip
   both recall and injection.
2. **Fan-out:** `MemoryManager.prefetch_all` (agent/memory_manager.py:525-545)
   strips skill scaffolding, then `_prefetch_provider` (547-595) runs external
   providers in a daemon thread joined at `_external_prefetch_timeout` (default
   8s, agent/memory_manager.py:47). A still-running prefetch skips the turn
   (567-577).
3. **Warm cache:** after each completed turn, `run_agent.py:4218-4235` calls
   `sync_all` + `queue_prefetch_all` (trivial-gated). The provider's
   `queue_prefetch` fills `_prefetch_result`; next turn's `prefetch()` serves it.
   Hindsight: plugin 1734-1786 (queue) / 1716-1732 (serve).

## Server vs client responsibility split (Hindsight)

The Hindsight API (server engine) does ranking, dedup, staleness and token
filtering; the Hermes plugin does almost none of it:

| Concern | Where | Evidence |
|---|---|---|
| Ranking (RRF → cross-encoder rerank → recency/temporal-boosted sort) | SERVER | hindsight_api/engine/memory_engine.py:4666-4737, 5500-5515 |
| Relevance threshold (`min_scores` reranker/final) | SERVER, OPT-IN, DEFAULT OFF, UNWIRED | memory_engine.py:5516-5538; NOT on RecallRequest REST model; NOT on client `arecall()`; results carry NO score |
| Token budget (`max_tokens`) | SERVER ONLY | memory_engine.py:5813, 6244-6277 `_filter_by_token_budget` (counts cl100k tokens of `text`, breaks before overflow) |
| Budget→retrieval depth (`low/mid/high`) | SERVER | memory_engine.py:764-795 fixed {100,300,1000} or adaptive ratio of max_tokens |
| Dedup | SERVER | memory_engine.py:5574-5620 `prefer_observations` provenance dedup; MMR claimed in docstrings (4672, 5012) but no MMR call found in the traced async pipeline |
| Staleness | SERVER | search/reranking.py:36-52 recency decay; invalidated/superseded excluded in retrieval; `created_after`/`query_timestamp` engine-side but NOT exposed via `arecall()` |
| Client-side cap / relevance gate on injected text | **NONE** | plugin joins every `r.text` verbatim (see fix points) |

## Verified gaps (2026-08-17, hindsight-client 0.6.1 / hindsight-api-slim 0.9.0)

1. **A client-side relevance threshold is IMPOSSIBLE with the current client
   API**: `RecallResult` has no score/relevance field, `arecall()` has no
   `min_scores` param, the REST `RecallRequest` carries no `min_scores`. Server
   `min_scores` exists but is engine-internal and default-off. The Hermes plugin
   reads only `r.text` — every returned result is injected. The only in-plugin
   relevance levers are `recall_types` (default `['observation']`, plugin
   793/1585-1597) and `recall_tags`.
2. **Hard token budget is server-enforced only.** The plugin forwards
   `recall_max_tokens` (default 4096) and trusts the server's token filter; there
   is no client-side cap on the joined string.
3. **Hindsight does NOT implement `on_pre_compress`** — compression triggers no
   retain; write protection is purely per-turn `sync_turn`/`auto_retain`
   (`retain_every_n_turns`). Older skills claim an "on_pre_compress retains last
   10 turns" hook — that is STALE (grep 0 hits in the plugin).

## Where to fix "targeted recall + hard budget + relevance threshold"

- **In-repo Hermes fix:** apply a shared budget cap + (trace-score) relevance
  prefilter at the two join sites in `plugins/memory/hindsight/__init__.py` —
  `:1778` (prefetch) and `:2014` (`hindsight_recall` tool). Enable
  `arecall(trace=True)` to pull normalized reranked scores out of the trace
  payload for the threshold.
- **Config-only (no code):** `/root/.hermes/hindsight/config.json` —
  `recall_max_tokens`, `recall_budget`, `recall_types=['observation']`,
  `recall_max_input_chars`, `recall_tags`/`recall_tags_match`.
- **Real scores / Memory Sniper:** route auto-recall through the Qdrant
  hybrid-search / memory-gateway service (port 8889) which returns per-result
  scores and already implements budget/min-score/MMR-dedup compilation; the
  Hindsight plugin's `api_url` points at 8888 (PG recall, no scores) by default.
- **Server+pkg change (bigger):** expose engine `min_scores` on `RecallRequest`
  + `arecall()` and add a `score` field to `RecallResult`.

## Test points

- `tests/plugins/memory/test_hindsight_provider.py` — TestPrefetch (494-535),
  `test_recall_success` (444-450), TestConfig (257-269): extend for budget-cap
  and relevance-prefilter behavior; mock `arecall` returning
  over-budget/multi-result payloads and assert the joined output is
  capped/filtered.
- `tests/agent/test_turn_context.py:228-240` — trivial-prompt prefetch gate
  (skip on "hi!", run on substantive query).
- `tests/agent/test_memory_provider.py:154-300` — `prefetch_all` /
  `queue_prefetch_all` manager behavior incl. thread-skip coverage.
- `tests/run_agent/test_pre_compress_memory_context.py` — on_pre_compress →
  compressor handoff (used if the provider ever implements the hook).

## Pitfalls

- Per-turn memory is in the **user message**, not the sysprompt — so a memory
  change does NOT break the stable prompt prefix, but it DOES append variance to
  the user turn on non-trivial prompts.
- The provider's `system_prompt_block()` runs inside a bare `try/except` in
  system_prompt.py:540-541 — a throwing provider is silently dropped, no log.
- `is_trivial_prompt` guards BOTH the per-turn prefetch and the post-turn warm
  prefetch — a one-word turn never triggers a network recall, which is normally
  what you want; remember it when you expect recall to fire on an image/emoji-only
  input (it won't; content is flattened first in run_agent.py:4214).
- Server `max_tokens` counts the `text` field only; chunks/entities are fetched
  independently of it (memory_engine.py:4693-4697) — irrelevant here because the
  plugin never enables them.
- Don't conclude "Hindsight is broken" from empty injection: check `auto_recall`
  (plugin 1585), `memory_mode != 'tools'` (1735), `_recall_types` narrowing, the
  server's `reranker_max_candidates`/`recall_budget`, and read-after-write gating
  (`prefetch_waits_for_retain`, plugin 1244-1358) before trusting a missing result.

## Full audit trace

`references/recall-injection-audit-2026-08-17.md` — complete file:line walkthrough
of the injection path, server engine references, and exact fix/test citations.
