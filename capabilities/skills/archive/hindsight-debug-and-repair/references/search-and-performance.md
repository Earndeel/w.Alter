## Prometheus Metrics (detailed timing)

The `/metrics` endpoint exposes detailed histograms. Key metrics for performance analysis:

```bash
# Get all hindsight metrics (filtered from Prometheus exposition format)
curl -s http://127.0.0.1:8888/metrics | grep '^hindsight_' | grep -v '_bucket' | grep -v '_created'
```

### Key metric families:
- `hindsight_llm_duration_seconds_sum` — LLM call durations by scope:
  - `retain_extract_facts`: avg ~15.7s per call (gemini-3.1-flash-lite-preview)
  - `consolidation`: avg ~156s per call (2.6 min!)
  - `reflect`: avg ~8.2s per call
  - `reflect_tool_call`: avg ~63.8s per call
- `hindsight_operation_duration_seconds_sum` — End-to-end operation durations:
  - `recall` (budget=mid): avg ~2.38s across 151 calls
  - `retain`: avg ~7.53s across 10 calls
- `hindsight_http_duration_seconds_sum` — Per-endpoint HTTP durations
- `hindsight_db_pool_*` — Connection pool stats

### Automated test scripts (production-ready)
```bash
# Full test suite (10 tests, exit code 0=pass, 1=fail)
python3 /root/.hermes/scripts/test_hindsight.py --verbose

# Component speed benchmark (uses Prometheus /metrics)
python3 /root/.hermes/scripts/bench_hindsight.py
```
Both scripts auto-cleanup test data they create.

### Component Speed Reference (Prometheus /metrics, 2026-04-26)

Use `/metrics` endpoint for internal timings — `trace=true` does NOT expose phase timings.

| Component | Avg Latency | Source |
|---|---|---|
| Recall end-to-end | 2.36s | `hindsight_operation_duration_seconds` (budget=mid) |
| Retain end-to-end | 7.53s | `hindsight_operation_duration_seconds` |
| LLM extract_facts | 15.7s/call | `hindsight_llm_duration_seconds` (scope=retain_extract_facts) |
| LLM consolidation | 155.9s/call | `hindsight_llm_duration_seconds` (scope=consolidation) |
| LLM reflect | 8.2s/call | `hindsight_llm_duration_seconds` (scope=reflect) |
| Health check | 0.002s | `hindsight_http_duration_seconds` |
| Entities list | 0.005s | `hindsight_http_duration_seconds` |
| Entity graph | 0.007s | `hindsight_http_duration_seconds` |

**Bottleneck:** Cross-encoder rerank = 68% of recall latency (~1.6s out of 2.36s total).

24. **Gemini model name suffix:** `gemini-3.1-flash-lite` returns 403 Forbidden. The correct name is `gemini-3.1-flash-lite-preview`. This applies everywhere: systemd env vars, Python script defaults, Hindsight config. Always include `-preview` suffix. This broke `dream_cycle.py` silently — the merge task failed while health checks passed, masking the issue for 14 days.
25. **Script corruption from key redaction:** When tools or scripts redact API keys from Python source files, they can corrupt `os.getenv()` calls. Pattern: `os.getenv("OPENROUTER_API_KEY", "")` becomes `os.get...EY", "")` (truncated, unterminated string literal). Check with `python3 -c "import py_compile; py_compile.compile('script.py', doraise=True)"` after any automated key redaction. Also `grep -rn 'os\.get\.\.\.' /root/.hermes/scripts/ /root/.hermes/services/` to find corrupted files.
26. **Guarded maintenance max_delete too low:** The `memory-guarded-maintenance` systemd service default `--max-delete 50` is too low for active systems. With 174 duplicate groups and 251 excess rows, the guard blocks every run. Set `--max-delete 200` in the systemd unit. Check with: `cat /root/.hermes/logs/memory-autopilot/pg-exact-dedup-latest.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'blocked={d.get(\"blocked\")} reason={d.get(\"reason\")}')"`
27. **PG query patterns:** The `memory_units` table has NO `norm_text` column. For exact duplicate detection, use `md5(text)` grouping. Table name is `entities` NOT `memory_entities`. Use `docker exec hindsight-pg psql -U hindsight -d hindsight -c "..."` since psql is not installed on the host.
28. **Cron failures from provider cascading:** When the primary provider AND fallback both have connection errors simultaneously (e.g. 3AM UTC), cron jobs fail silently. The job's `last_status: error` is the only signal. Check: `grep "APIConnectionError" /root/.hermes/logs/gateway.log | tail -20`

## Qdrant Vector Store (2026-04-27 — replaces PG for vector search)

**Deployment:** Docker container `qdrant` on Oracle ARM (aarch64), ports 6333 (API) / 6334 (gRPC)
```bash
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant-data:/qdrant/storage \
  qdrant/qdrant:latest
```

**Collections:**
- `memories` — dense vectors (768d), payload: text, bank_id, source, tags, fact_type, timestamps, access_count, metadata
- `entities` — dense vectors (768d), payload: name, entity_type, bank_id, observations, properties

**Performance vs PG:**
| Backend | Vector search (264 memories) | Notes |
|---|---|---|
| PG (pgvector) | ~200ms | Docker container at 172.17.0.3 |
| **Qdrant** | **~5ms** | 40x faster, same data |

**Migration script:** `/root/.hermes/scripts/migrate_pg_to_qdrant.py`
- Exports memory_units + entities from PG with embeddings
- Generates BM25 sparse vectors (hash-based) for hybrid search
- Upserts into Qdrant collections
- Usage: `HINDSIGHT_PG_PASSWORD=<pass> python3 migrate_pg_to_qdrant.py`

**Pitfall: BM25 sparse vectors** — The hash-based sparse vector approach (python hash → sparse indices) does NOT produce consistent indices between query and stored documents. Dense search alone is sufficient for <1000 memories. For 10k+ memories, use Qdrant's built-in text index or a proper BM25 vocabulary.

**Pitfall: FlashRank passage format** — FlashRank expects passages as dicts with "text" key:
```python
# WRONG: passages=["text1", "text2"]
# RIGHT: passages=[{"text": "text1"}, {"text": "text2"}]
```
And returns `{"text": "...", "score": float32}` (NOT `{"rank": ..., "score": ...}`). Match back to original docs by text content.

## Hybrid Search Service (2026-04-27)

Standalone FastAPI service on port 8889 — separate from Hindsight API (8888).

```bash
systemctl status hybrid-search    # service
journalctl -u hybrid-search -f    # logs
curl http://127.0.0.1:8889/health  # health check
```

**Architecture — Read/Write path separation:**
```
READ PATH (synchronous, blocking):
  Agent → POST /recall → Gemini embed (500ms) → Qdrant search (5ms) → FlashRank rerank (1.3s) → Top 5
  Total: ~1.8s avg (min 1.1s, max 3.7s)
  LLM waits for results before generating response.

WRITE PATH (asynchrone, non-bloquant):
  Agent → Hindsight API (8888) → retain/consolidate → PG + background processing
  Results written to Qdrant by migration/connector scripts.
```

**Env vars (in systemd unit):**
```bash
GEMINI_API_KEY=<key>           # for embedding
RERANKER_PROVIDER=flashrank    # or: cohere, zeroentropy
QDRANT_URL=http://127.0.0.1:6333
```

**API endpoint:**
```bash
curl -X POST http://127.0.0.1:8889/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "Lucas preferences", "top_k": 5, "prefetch_limit": 50}'
# Returns: {results: [...], timings: {embed_ms, search_ms, rerank_ms, total_ms, candidates_count}}
```

**Config:** `/root/.hermes/services/hybrid_search.py`

**Pitfall: prefetch_limit** — Default 50. With FlashRank on ARM CPU, 100 candidates takes ~2.5s rerank, 50 takes ~1.3s. Quality difference is negligible for <500 memories.

**Cloud reranker (ZeRank-2 — now in production):**
ZeRank-2 is now the primary reranker. Config in systemd:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy
HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL=zerank-2
HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=<key>
```
Estimated total with ZeRank-2 API: ~740ms (500ms embed + 5ms search + 200ms API rerank).
Fallback: `HINDSIGHT_API_RERANKER_PROVIDER=flashrank` with `ms-marco-MiniLM-L-12-v2`.

## Recall Performance Optimization (2026-04-27)

### Latency breakdown (hybrid search service)
- `Gemini embedding`: ~500ms (API round trip)
- `Qdrant vector search`: ~5ms (40x faster than PG)
- `FlashRank rerank`: ~1300ms avg (highly variable on ARM: 675-3241ms)
- `Total`: ~1819ms avg (min 1137ms, max 3720ms)

### Latency breakdown (legacy Hindsight API)
Use `{"query":"...", "trace":true}` in recall to get `phase_metrics`:
- `generate_query_embedding`: ~0.5s (Gemini API round trip)
- `parallel_retrieval`: ~0.07s (PG vector + BM25 + graph)
- `reranking`: **1.6-1.9s** (cross-encoder on 80 candidates) ← **main bottleneck**
- Total: ~2.2-2.5s

### Reranker FlashRank model comparison (tested 2026-04-26)

| Model | Size | Avg recall | Quality (top-1 match) | Notes |
|---|---|---|---|---|
| `ms-marco-MiniLM-L-12-v2` | 34MB | 2.2s | 100% (baseline) | **Current production** |
| `ms-marco-TinyBERT-L-2-v2` | 4MB | 0.7s | 50% vs baseline | 3x faster but loses quality on technical queries |

**Conclusion:** TinyBERT confuses context on technical/architecture queries (e.g. "Scena Factory architecture" returns "creator of Scena Factory" instead of "Workers, D1, PiAPI"). Since reranking is async (prefetch), speed doesn't matter — **stay on MiniLM-12 for quality**.

### Reranker config options
```bash
# Limit candidates sent to cross-encoder (default: 300)
# 40 is the sweet spot — quality matters more than speed (async reranking)
HINDSIGHT_API_RERANKER_MAX_CANDIDATES=40

# Bucket batching — sorts by length for efficient batching
# ⚠️ COUNTERPRODUCTIVE on ARM (Neoverse-N1) with small candidate counts!
# Made things 30% SLOWER in testing. Only useful with 200+ candidates on fast CPUs.
HINDSIGHT_API_RERANKER_LOCAL_BUCKET_BATCHING=false  # keep false on ARM

# FP16 — may help on CPUs with AVX-512/VNNI, not tested on ARM
HINDSIGHT_API_RERANKER_LOCAL_FP16=false
```

### Reranker provider: `rrf` (fast alternative)
The `rrf` (Reciprocal Rank Fusion) provider is a **passthrough** that skips the cross-encoder entirely:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=rrf
```
- **Speed:** 0.7s vs 2.5s (3.8x faster)
- **Quality:** Slightly lower — gives more weight to recency/entity than semantic similarity
- **When to use:** <500 memories, or as a pre-filter stage
- **When NOT to use:** 500+ memories where cross-encoder quality matters
- **Tested 2026-04-26:** 5 queries, same top-3 results as cross-encoder on 83 memories

### Reranker provider options (all valid values)
`local`, `tei`, `cohere`, `zeroentropy`, `siliconflow`, `google`, `flashrank`, `litellm`, `litellm-sdk`, `rrf`, `jina-mlx`

### Cloud reranker options (for scaling to 100k+ memories)

**Jina reranker v2 via Cohere provider (RECOMMENDED):**
Jina's API is Cohere-compatible — use the `cohere` provider pointed at Jina:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=cohere
HINDSIGHT_API_RERANKER_COHERE_API_KEY=<jina_api_key>     # Free: 1M tokens/month
HINDSIGHT_API_RERANKER_COHERE_MODEL=jina-reranker-v2-base-multilingual
HINDSIGHT_API_RERANKER_COHERE_BASE_URL=https://api.jina.ai/v1
```
- Multilingual (French included), 0.3B params, ~200-400ms via API
- Free tier: 1M tokens/month (sufficient for 100k+ memories daily use)
- Get key: https://jina.ai/?key=key-manager
- **Not yet tested in production** — benchmark quality vs MiniLM-12 before switching

**Cohere rerank-v3.5 via OpenRouter:**
```bash
HINDSIGHT_API_RERANKER_PROVIDER=openrouter
HINDSIGHT_API_RERANKER_OPENROUTER_MODEL=cohere/rerank-v3.5
# Needs: OPENROUTER_API_KEY in env
# Cost: ~$1/1000 searches, ~300-500ms per search
```

**Key finding (2026-04-26):** Reranking runs **asynchronously** via prefetch — the user never waits for it. The prefetch starts when the turn begins, reranks in a background thread, and results are injected at the next turn. This means **reranker speed does not impact user experience**. Prioritize quality over speed. Use MAX_CANDIDATES=40 (not 25) for best results.

### Legacy HUD CPU hog
The `hermes-hudui` service (legacy HUD on port 3002) can consume **82% CPU** continuously after running for days. This directly impacts reranker latency. Check and kill:
```bash
systemctl stop hermes-hudui
systemctl disable hermes-hudui
```
After killing, recall latency dropped from 2.8s to 2.2s.
