# Recall-Injection Audit — 2026-08-17

Full file:line walkthrough of the Hermes memory/Hindsight injection path,
verified against `/root/.hermes/hermes-agent` working tree (branch main) and the
installed packages `hindsight-client 0.6.1` / `hindsight-api-slim 0.9.0`.
Read-only audit — no files were modified.

## Injection path

1. **Static sysprompt block** — `agent/system_prompt.py:534-541` appends
   `agent._memory_manager.build_system_prompt()` into the volatile tier, inside a
   bare `try/except` (swallowed exceptions). `MemoryManager.build_system_prompt()`
   = `agent/memory_manager.py:486-503` (joins each provider's
   `system_prompt_block()`). Hindsight's block is static only
   (`plugins/memory/hindsight/__init__.py:1694-1714`).
2. **Per-turn prefetch gate** — `agent/turn_context.py:1264-1271`:
   `prefetch_all()` fired only when `not is_trivial_prompt(query)`; result stored
   in `ext_prefetch_cache`. Trivial = `agent/memory_provider.py:52-78`
   (`TRIVIAL_PROMPT_RE`, slash commands, empty).
3. **Injection into the API copy of the USER message** —
   `agent/turn_context.py:77-85` (`compose_user_api_content`) wraps the cached
   text in `<memory-context>` fences (`agent/memory_manager.py:347-361`) and
   appends; stored message stays clean, sidecar `api_content` carries sent bytes.
4. **Post-turn warm cache** — `run_agent.py:4218-4235`: `sync_all` +
   `queue_prefetch_all`, trivial-gated at 4231; interrupted turns skipped (4208).
5. **Manager fan-out** — `prefetch_all` `agent/memory_manager.py:525-545` (skill
   scaffolding strip 531), `_prefetch_provider` 547-595 (daemon thread, join at
   `_external_prefetch_timeout` = 8s, memory_manager.py:47; still-running prefetch
   ⇒ skip turn, 567-577), `queue_prefetch_all` 597-622 (background executor).

## Hindsight plugin recall implementation

- `queue_prefetch` — plugin 1734-1786: tools-mode skip (1735), auto_recall skip
  (1738), shutting-down skip (1741), query truncation to `_recall_max_input_chars`
  (1745-1746), optional retain-drain wait (1756-1757), then
  `client.arecall(bank_id, query, budget=_budget, max_tokens=_recall_max_tokens,
  tags?, types?)` (1764-1775). Result `text = "\n".join(f"- {r.text}" ...)` over
  EVERY result (1778) — no score use, no token cap, no dedup.
- `prefetch` — plugin 1716-1732: waits 3s for the bg thread, pops
  `_prefetch_result`, prepends preamble.
- Tool `hindsight_recall` — plugin 1993-2018: same kwargs (1998-2006); returns all
  results numbered (2014); "No relevant memories found." only when empty.
- `_get_client` — plugin 1101-1152 (local_embedded → `HindsightEmbedded`, else
  `hindsight_client.Hindsight`).
- `sync_turn` writer — plugin 1862-1960 (`retain_every_n_turns` buffering, single
  writer thread, async retain-op tracking).
- Provider does NOT implement `on_pre_compress` / `on_turn_start` /
  `on_session_end` / `on_memory_write` / `on_delegation` (grep 0 hits).

## Server-side machinery (hindsight-api-slim 0.9.0, via venv site-packages)

- `recall_async` pipeline — `engine/memory_engine.py:4633-4737`; combined scoring
  + sort 5500-5515; truncate to `thinking_budget*2` (5622+); trace phase metrics
  5550-5560.
- Budget → thinking_budget — `memory_engine.py:764-795`: fixed {LOW:100,
  MID:300, HIGH:1000} (`recall_budget_fixed_*`) or adaptive
  `round(max_tokens * ratio)` clamped [20,2000]; `reranker_max_candidates` scaling
  797-811.
- **Token budget ENFORCEMENT (server-only)** — `memory_engine.py:5813`
  `self._filter_by_token_budget(top_dicts, max_tokens)`; implementation
  6244-6277: counts cl100k tokens of `text` only, `break` before overflow.
- **Relevance threshold (unwired)** — `memory_engine.py:5516-5538`:
  `min_scores` (reranker/final) filter, explicitly opt-in with NO default;
  NOT reachable from the REST/client layers:
  - `hindsight_client/.../hindsight_client.py:815-833` — `arecall()` has no
    `min_scores` param.
  - `hindsight_client_api/models/recall_request.py:42` — RecallRequest
    __properties = [query, types, budget, max_tokens, trace, query_timestamp,
    include, tags, tags_match, tag_groups]; no min_scores.
  - `hindsight_client_api/models/recall_result.py:42` — RecallResult
    __properties has NO `score`/`relevance` field, so the Hermes plugin cannot
    filter on relevance client-side either.
- **Dedup** — `memory_engine.py:5574-5620` `prefer_observations` provenance dedup
  (drops raw world/experience facts subsumed by a returned observation). MMR is
  referenced in docstrings (4672, 5012) but no MMR call was found in the traced
  async pipeline (stale docstring in 0.9.0).
- **Staleness** — `engine/search/reranking.py:36-52` `compute_recency_decay`,
  applied in combined scoring (~memory_engine.py:5494-5502); invalidated/
  superseded facts excluded at retrieval; `created_after`/`created_before`/
  `query_timestamp` accepted by `recall_async` (4658-4660) but not exposed via
  `arecall()`.

## on_pre_compress — core vs provider

- Core handoff: `agent/conversation_compression.py:2825-2836` captures
  `agent._memory_manager.on_pre_compress(messages)`, sanitizes, forwards as
  `memory_context` into `compress()` (2838-2846; warns for engines lacking the
  kwarg).
- `MemoryManager.on_pre_compress` — `agent/memory_manager.py:974-991` fans out to
  providers; Hindsight returns ABC default `""` (`agent/memory_provider.py:258-268`).
- Consequence: compression triggers NO retain. Write protection is per-turn
  `sync_turn`/`auto_retain` (`retain_every_n_turns`, currently 1 in config) via
  the completed-turn mirror (`run_agent.py:4218-4235`). Skill claims of an
  "on_pre_compress hook that retains the last 10 turns" are STALE.

## Current live config (`/root/.hermes/hindsight/config.json`)

mode=local_external, api_url=http://127.0.0.1:8888, bank_id=walter,
memory_mode=hybrid, auto_recall=true, auto_retain=true,
retain_every_n_turns=1, retain_async=true, recall_budget=low,
recall_max_tokens=1200, recall_max_input_chars=500,
recall_prefetch_method=recall. (api_url points at Hindsight PG recall 8888,
NOT the scored Qdrant hybrid-search 8889.)

## Root causes vs "targeted retrieval + hard token budget + relevance threshold"

- Hard token budget: PARTIALLY satisfied — server-enforced only; no client-side
  cap at plugin 1778/2014.
- Relevance threshold: NOT satisfiable end-to-end with current packages (no score
  field, min_scores unwired). Only in-plugin levers = `recall_types`
  (default `['observation']`) and `recall_tags`.

## Minimally scoped fix / test points

- Fix: shared budget-cap + (trace-score) relevance prefilter at
  `plugins/memory/hindsight/__init__.py:1778` (prefetch) and `:2014`
  (hindsight_recall tool).
- Secondary: forward `query_timestamp`/`created_after` via `arecall` (client
  param exists at hindsight_client.py:823) for staleness control.
- Server+pkg future: expose `min_scores` on RecallRequest + arecall(), add `score`
  to RecallResult.
- Tests: `tests/plugins/memory/test_hindsight_provider.py` (TestPrefetch
  494-535, test_recall_success 444-450, TestConfig 257-269);
  `tests/agent/test_turn_context.py:228-240` (trivial gate);
  `tests/agent/test_memory_provider.py:154-300`;
  `tests/run_agent/test_pre_compress_memory_context.py`.
