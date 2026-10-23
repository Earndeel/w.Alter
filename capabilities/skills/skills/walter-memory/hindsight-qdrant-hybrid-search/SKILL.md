---
name: hindsight-qdrant-hybrid-search
description: "Deploy and maintain Hindsight hybrid memory: Qdrant (local vector DB), Gemini Embed 2 (API), ZeRank-2 reranking (API), async write path worker. Replaces PG+pgvector for 40x faster search."
triggers:
  - Qdrant deployment or migration
  - Hindsight memory performance issues
  - Hybrid search setup
  - Hybrid Search read-path changes or API compatibility checks
  - Memory context injection compiler / "Memory Sniper" tuning
  - Write path / async extraction
  - Reranker swap (FlashRank ↔ ZeRank-2 ↔ Cohere)
---

# Hindsight Qdrant Hybrid Search

## Architecture

```
READ PATH (synchrone, ~970ms avg):
  Query → Gemini Embed 2 API (~530ms)
       → Qdrant dense search (~5ms)      ← 40x faster than PG
       → ZeRank-2 API rerank (~390ms)
       → Top 5 injected into LLM context

WRITE PATH (asynchrone, ~15s/batch):
  10 conversation turns
    → Gemini 3.1 Flash Lite (AI Studio free tier) extract facts
    → Gemini Embed 2 vectorize facts
    → Qdrant upsert with metadata + invalidation
```

## Stack

| Component | Location | Port | Role |
|---|---|---|---|
| Qdrant v1.17.1 | Docker `qdrant` | 6333/6334 | Vector DB (ARM native) |
| Hybrid Search | `hybrid-search.service` | 8889 | Read path API |
| Write Worker | `write-worker.service` | 8890 | Async batch extraction |
| Hindsight API | `hindsight-api.service` | 8888 | Consolidation/dreaming |

## Setup Steps

### 1. Deploy Qdrant

```bash
docker volume create qdrant-data
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant-data:/qdrant/storage \
  --memory=4g \
  qdrant/qdrant:latest
```

### 2. Create Collections

```bash
curl -X PUT http://127.0.0.1:6333/collections/memories \
  -H "Content-Type: application/json" -d '{
    "vectors": {"dense": {"size": 768, "distance": "Cosine"}},
    "optimizers_config": {"default_segment_number": 2}
  }'

curl -X PUT http://127.0.0.1:6333/collections/entities \
  -H "Content-Type: application/json" -d '{
    "vectors": {"dense": {"size": 768, "distance": "Cosine"}}
  }'
```

### 3. Migrate from PG

Script at `/root/.hermes/scripts/migrate_pg_to_qdrant.py`:
- Exports memory_units + entities from PG
- Generates BM25 sparse vectors (optional)
- Upserts into Qdrant with named vectors

**CRITICAL — Named vectors**: When using named vectors in Qdrant, PointStruct must use `vector={"dense": vector}`, NOT `vector=vector`.

### 4. Hybrid Search Service

File: `/root/.hermes/services/hybrid_search.py`
Service: `hybrid-search.service`

Key env vars:
```
QDRANT_URL=http://127.0.0.1:6333
GEMINI_API_KEY=<key>
RERANKER_PROVIDER=zeroentropy   # or flashrank
ZEROENTROPY_API_KEY=ze_...
ZEROENTROPY_MODEL=zerank-2
```

### 5. Write Worker

File: `/root/.hermes/services/write_worker.py`
Service: `write-worker.service`

Key env vars:
```
QDRANT_URL=http://127.0.0.1:6333
GEMINI_API_KEY=<key>
EXTRACT_MODEL=gemini-3.1-flash-lite-preview
WRITE_BATCH_SIZE=10
```

Current extraction model: **Gemini 3.1 Flash Lite via AI Studio** (free tier). Previous models: Qwen 3.6 Flash → Gemini 2.5 Flash.

Current reranker: **ZeRank-2** (ZeroEntropy). Previous: FlashRank MiniLM.

Tested and validated: 8/8 extraction test battery passes, ~4.4s avg, ~$1/month for 500 extractions. See `references/extraction-quality-testing.md`.

See `references/model-selection-for-extraction-consolidation.md` for benchmark-backed model recommendations per tier (compression / extraction / consolidation) and how to swap them safely.

See `references/extraction-quality-testing.md` for a battery of 8 test cases to validate extraction quality after model swaps, including cost benchmarks and recall verification.

### AI Studio Free Tier Integration Pattern

When the workload is Gemini-native (extraction, consolidation, compression), route directly through Google AI Studio instead of OpenRouter to use the free tier.

**Key differences from OpenRouter/OpenAI-format APIs:**
1. **No system messages** — prepend system instructions to the user prompt text
2. **Response format** — `data["candidates"][0]["content"]["parts"][0]["text"]` instead of `choices[0].message.content`
3. **Structured output** — use `"responseMimeType": "application/json"` in `generationConfig`, NOT `"response_format": {"type": "json_object"}`
4. **Embedding dimension** — always include `"output_dimensionality": 768` or Gemini returns 3072d by default
5. **URL pattern** — `https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}`

**Minimal Gemini API caller (async):**
```python
async def call_gemini_api(prompt: str, model: str, key: str, max_tokens: int = 4000, temperature: float = 0.1) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=180.0)
    resp.raise_for_status()
    data = resp.json()
    candidate = data["candidates"][0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        logger.warning("Gemini response truncated")
    return candidate["content"]["parts"][0]["text"]
```

**Pitfall**: Some Gemini model names differ between AI Studio and OpenRouter:
- AI Studio: `gemini-3.1-flash-lite-preview`, `gemini-3.1-pro-preview`, `gemini-3-flash-preview`
- OpenRouter: `google/gemini-3.1-flash-lite-preview`, `google/gemini-3.1-pro-preview`
- Test availability first with a minimal `generateContent` call before integrating into the pipeline.

**Hindsight API provider naming**: The hindsight-api package expects `gemini` as the provider name, NOT `google`. Using `HINDSIGHT_API_LLM_PROVIDER=google` throws `ValueError: Invalid LLM provider: google. Must be one of: ... gemini ...`. Always use `HINDSIGHT_API_LLM_PROVIDER=gemini`.

**hindsight-api.env syntax bug (pre-existing)**: The env file at `~/.hermes/hindsight/hindsight-api.env` had a duplicated key name `HINDSIGHT_API_DATABASE_URL=HINDSIGHT_API_DATABASE_URL=...` which caused SQLAlchemy URL parse failures on every hindsight-api restart. Fix: `HINDSIGHT_API_DATABASE_URL=postgresql://hindsight@172.17.0.3:5432/hindsight`.

### Qwen 3.6 Flash via OpenRouter — Critical Quirks

1. **`response_format: json_schema` with `strict: true` causes 524 timeouts** on OpenRouter. Use `{"type": "json_object"}` instead — still forces JSON output but without the schema constraint overhead.

2. **`reasoning_effort: "max"` makes Qwen think for 2+ minutes** per request. Remove this parameter for write worker use — default thinking is fast enough for fact extraction.

3. **`content` can be `None` in response** when thinking mode is active — the JSON output appears in `choices[0].message.reasoning` instead. Always check both fields: `content or reasoning`.

4. **Qwen uses different field names and wrapper shapes** than the expected schema. A robust `normalize_facts(raw: dict | list)` is required. It should accept direct lists and wrappers such as `extracted_facts`, `facts`, `items`, `memories`, `data`, `results`, and `output`; map `fact`/`text`/`content`/`statement`/`memory`/`value`/`description` → fact text; map `fact_type`/`type`/`category` → fact_type; and preserve/normalize `importance`, `confidence`, `categories/tags`, `entities`, `source`, and metadata.

5. **Alternate compact schema**: Qwen may return records like `type + subject + context + attribute + value + confidence` without a `fact` field. Do not drop these silently; synthesize a readable fact string from the available fields and then normalize it.

6. **httpx timeout must be 180s** for OpenRouter calls (default 60s causes silent failures).

7. **Logging hygiene**: never log the full OpenRouter response body when `choices` is missing, and never dump the first normalized fact in logs. Log only response keys / fact keys to avoid leaking sensitive memory content.

### Self-Invalidation Bug

When a new fact has `obsoletes_previous_fact: true`, the invalidation search can match the **newly written fact itself** and invalidate it. Fix: collect all new fact texts in the batch and skip them during invalidation search. Also add `must_not=[FieldCondition(key="invalidated", match=MatchValue(value=True))]` to the query filter to skip already-invalidated facts.

### Hybrid Search Must Filter Invalidated Facts

The read path MUST include `must_not=[FieldCondition(key="invalidated", match=MatchValue(value=True))]` in the Qdrant query filter. Without this, invalidated facts (old versions) still appear in search results with high scores.

### Memory Sniper / Injection Compiler (read-path add-on)

Use this pattern when improving Hindsight recall quality without breaking existing Hermes clients. The rule is: `results[]` stays the compatibility source of truth; compiled injection context is additive.

**API compatibility contract**
- Preserve existing `/recall` request fields and `results[]`, `timings`, `query` response fields.
- Add optional fields only: `memory_context`, `injection_context`, `sniper`.
- Hermes' Hindsight plugin may only read `resp.results` and concatenate `r.text`; do not rename/remove result fields or require clients to consume `memory_context`.

**Recommended compiler flow**
1. Detect intent and budget before injection. Trivial acknowledgements/greetings should get budget `none` or empty `memory_context`.
2. Retrieve broader than you inject (`prefetch_limit` candidates), then score/gate down.
3. Use composite scoring: semantic/Qdrant score + reranker score + entity/token overlap + recency/source-quality if available.
4. Add a minimum retrieval-signal gate. Composite scores can accidentally lift irrelevant memories via generic metadata/recency; require either semantic/rerank signal or strong entity overlap before candidates enter MMR.
5. Use MMR/dedup before compiling the final context. Penalize or skip near-duplicates rather than injecting multiple versions of the same fact.
6. Apply a strict token budget: `none=0`, `low≈450`, `mid≈900`, `high≈1800` unless explicitly changed by env vars.
7. Redact secrets before adding any memory text to `memory_context` or logs. Keep logs to counts/keys/timings, not full memory contents.

**Useful env vars**
```bash
MEMORY_SNIPER_ENABLED=true
MEMORY_SNIPER_DEFAULT_BUDGET=mid
MEMORY_SNIPER_MAX_ITEMS=5
MEMORY_SNIPER_MIN_SCORE=0.20
MEMORY_SNIPER_MIN_RETRIEVAL_SCORE=0.15
MEMORY_SNIPER_MMR_LAMBDA=0.72
MEMORY_SNIPER_DUPLICATE_SIMILARITY=0.50
MEMORY_SNIPER_BUDGET_NONE=0
MEMORY_SNIPER_BUDGET_LOW=450
MEMORY_SNIPER_BUDGET_MID=900
MEMORY_SNIPER_BUDGET_HIGH=1800
```

**Validation commands**
```bash
/root/.hermes/hermes-agent/venv/bin/python3 -m py_compile \
  /root/.hermes/services/hybrid_search.py \
  /root/.hermes/scripts/test_memory_sniper.py
/root/.hermes/hermes-agent/venv/bin/python3 /root/.hermes/scripts/test_memory_sniper.py
systemctl restart hybrid-search
curl -s --max-time 5 http://127.0.0.1:8889/health
curl -sS --max-time 30 -X POST http://127.0.0.1:8889/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"Lucas preferences Hindsight","bank_id":"walter","top_k":5,"prefetch_limit":25,"budget":"low","compile_context":true}'
```

Expected smoke response properties: `results` present, `memory_context` present, `injection_context.format="hindsight.memory_context.v1"`, `sniper.enabled=true`, `sniper.selected_count <= MEMORY_SNIPER_MAX_ITEMS`, `timings.sniper_ms` small (usually single-digit ms). Also test `compile_context:false`; it should still return `results[]` and an empty compiled context.

### Gateway Hooks (on_pre_compress + manual triggers)

- **`on_pre_compress` hook** in `plugins/memory/hindsight/__init__.py` — fires a background thread that POSTs conversation turns to `write-worker:8890/process`. Non-blocking.
- **`/remember <fact>`** command — gateway dispatches to `_handle_remember_command()` which calls write worker directly, returns confirmation.
- **`[SAVE] <content>`** prefix — detected in `_run_agent()` before LLM call, stripped from message, triggers immediate extraction.

### Write Worker Pydantic Model

`BatchResponse.error` must be `Optional[str] = None` (not `str = None`). Pydantic v2 rejects `None` for non-Optional string fields.

### Auto-retain Pollution Loop (Critical)

Do not let the Hindsight plugin retain every conversation turn directly into the Hindsight API while the PG-first `write-worker` also exists. This creates a feedback loop: session text → auto extraction → injected memories → repeated discussion → more extracted variants. Production policy: `/root/.hermes/hindsight/config.json` must keep `auto_retain=false`; retain only explicit durable markers/tools and the PG-first write path. `write_worker.py` must run ingestion-time semantic dedup (`MEMORY_WRITE_DEDUP_ENABLED=true`, `MEMORY_WRITE_DUPLICATE_SIMILARITY≈0.85`) before insertion. Existing `memory_facts` need `fact_key` + `value_hash` backfilled, otherwise lifecycle refresh/supersede cannot work and Qdrant fallback must resolve `pg_memory_id` back to PG.

### User Profile Compiler / Living User Model

For Monsieur's self-model, do not dump Hindsight into `USER.md`. Use the dedicated compiler:
- Schemas: `/root/.hermes/services/user_model/001_user_model_schema.sql` and `002_user_model_v2_decision_psychology.sql`.
- Core tables: `signal_candidates`, `profile_state`, `compiler_runs`, `compiler_state`.
- V2 specialized tables: `decision_events`, `outcomes`, `bias_hypotheses`, `life_signals`, `psychological_profile`, `preference_history`, `proactive_advice_rules`.
- Script: `/root/.hermes/scripts/user_profile_compiler.py`.
- Timer: `user-profile-compiler.timer` runs every 5 minutes.
- Source: Hermes `state.db` user messages only; strips `<memory-context>` before extraction. Recalled Hindsight memory is evidence/context, not new input.
- Extraction: Gemini `gemini-3.1-flash-lite-preview` when keys are available, heuristic fallback otherwise.
- Routing rule: extraction first creates evidence-backed `signal_candidates`, then routes decision/outcome/bias/life/psychology/preference signals into V2 tables.
- Promotion rule: explicit high-confidence signals become `profile_state`; sensitive data (`medical_sensitive`, precise location, communications, sexuality, secrets) is `manual_only`/contextual, never `always`.
- Guardrail: one-off task questions must not become global preferences just because the model phrases them as "Monsieur préfère..."; demote ambiguous question evidence below promotion threshold.
- `USER.md` remains a compact always-injected profile; Hindsight/PG keep proofs and history; Kardex keeps contacts.

Read-path integration:
- The Hindsight plugin (`/root/.hermes/hermes-agent/plugins/memory/hindsight/__init__.py`) now adds a separate `# User Model` branch to auto-prefetch memory context before the regular Hindsight episodic recall.
- Config keys in `/root/.hermes/hindsight/config.json`: `user_model_recall_enabled=true`, `user_model_recall_max_items=8`.
- The branch queries PostgreSQL `user_model.*` directly and injects only policy-safe rows: `always` low/medium, query-matched `contextual` low/medium, and bias/psychological contextual high only for relevant profile/bias/decision intents.
- `critical` and `manual_only` data are never auto-injected; Hindsight remains evidence/history, not the canonical profile.

Validation:
```bash
/root/.hermes/hermes-agent/venv/bin/python3 -m py_compile /root/.hermes/scripts/user_profile_compiler.py /root/.hermes/hermes-agent/plugins/memory/hindsight/__init__.py
PYTHONPATH=/root/.hermes/hermes-agent /root/.hermes/hermes-agent/venv/bin/python3 - <<'PY'
from plugins.memory.hindsight import _fetch_user_model_context
print(_fetch_user_model_context('profil utilisateur préférences biais décision mémoire', 8))
PY
systemctl --user status user-profile-compiler.timer hermes-gateway.service
cat /root/.hermes/logs/user-profile-compiler/latest.json
```

### User Profile vs Hindsight Stratification

When building W.Alter's long-term understanding of Monsieur, do not inject every remembered fact. Use a layered model: USER.md/user store for compact canonical identity, current preferences, and the active decision/psychological model; Hindsight for evidence, episodes, previous preference versions, and historical proofs; Kardex for people/conversations; life/medical/location data as sensitive raw signals summarized only when needed. See `references/user-profile-memory-stratification.md`.

## Extraction Model Selection

Use Gemini 3.1 Flash Lite for memory extraction. Tested 2026-05-15: 8/8 tests passed, $0.002 for 8 tests (~$1/month for 500 extractions). Structured JSON output works with `responseMimeType: application/json`.

```bash
# Test extraction quality via Hindsight API
curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/walter/memories" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"content": "test text", "context": "test", "document_id": "test_1"}], "async": false}'
```

## Memory Connectors (Telegram/Beeper → Hindsight)

Script: `/root/.hermes/scripts/memory_connectors.py`
State file: `~/.hermes/scripts/.connector_state.json`
Cron: `Memory External Connectors` (Hermes cron, daily 5h UTC)

### Beeper/WhatsApp Personal Chat Ingestion Guard

External chat connectors must not bulk-retain personal chat logs into Hindsight by default. Require either explicit durable-memory markers (`[SAVE]`, `#remember`, `à retenir`, etc.) or operational W.Alter/Hermes terms before retaining Beeper/WhatsApp messages. Personal chat ingestion should stay disabled unless `HINDSIGHT_INGEST_PERSONAL_CHATS=1` is set for a deliberate run. If noisy content is already present, backup first, invalidate `memory_facts`, delete legacy `memory_units` + dependent links, remove matching Qdrant points, and process the PG→Qdrant outbox.

### Retain API format

The correct Hindsight API endpoint for ingesting external messages:


```
POST /v1/default/banks/{bank_id}/memories
Content-Type: application/json

{
  "items": [
    {
      "content": "[Beeper:whatsapp:Name] sender: message text",
      "context": "beeper:chat_id",
      "tags": ["beeper", "network:whatsapp", "chat:Name"]
    }
  ]
}
```

**Field name is `content`, NOT `text`.** Using `text` returns 422 validation error.

### Beeper connector pattern

Fetch recent messages from each single chat via `/v1/chats/{id}/messages?limit=10`, track last-seen timestamp per chat in state file. Only ingest messages newer than last-seen.

**Do NOT use `/v0/messages`** — returns 404. The correct endpoints are:
- `/v1/chats` — list all chats
- `/v1/chats/{id}/messages?limit=N` — fetch messages from a specific chat

### Telegram connector pitfall

Telegram Bot API `getUpdates` returns 409 Conflict if another process (e.g., Hermes gateway) is already polling the same bot. The connector script should skip Telegram when the gateway is running, or use a separate bot token for memory ingestion.

### Cron environment

The Hermes cron scheduler does NOT inherit shell environment variables. Tokens must be read from the vault inside the script:
```python
subprocess.run(["vault", "get", "telegram/bot_token"], capture_output=True, text=True)
```

Never use `os.environ.get("TELEGRAM_BOT_TOKEN")` in cron-scheduled scripts — the variable won't be set.

See **`references/memory-connectors.md`** for the full integration pattern and troubleshooting.

## Pitfalls

### FlashRank passage format
FlashRank expects `[{"text": "..."}]`, NOT `["string"]`. Returns `[{"text": "...", "score": float32}]` sorted by score desc. Match back to originals by text content (no `rank` key).

### Qdrant named vectors
When collection uses named vectors (`"dense"`), PointStruct must be `vector={"dense": [0.1, 0.2, ...]}`. Passing `vector=[0.1, 0.2, ...]` or adding `vectors={"dense": [...]}` to `upsert()` both fail.

### Systemd empty Environment line
An empty `Environment=` line in a .service file silently drops ALL subsequent Environment lines. Always `grep` the env vars from `/proc/<pid>/environ` after starting.

### Systemd Environment Override Pitfall
The systemd service file (`/etc/systemd/system/hindsight-api.service`) can hardcode `Environment=HINDSIGHT_API_LLM_MODEL=...` which **silently overrides** the `.env` file. The `.env` at `~/.hindsight/profiles/hermes.env` may say `gemini-3-flash-preview` while the running process actually uses `gemini-3.1-pro-preview` (or whatever the systemd unit says). This caused $50+ in 2 weeks when Pro was left running for extraction.

**Diagnosis**: compare ALL running process env vars vs .env — not just LLM_MODEL:
```bash
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep -E 'LLM_MODEL|RERANKER|EMBEDDINGS|ZEROENTROPY' | sort
cat ~/.hindsight/profiles/hermes.env | grep -E 'LLM_MODEL|RERANKER|EMBEDDINGS'
```

This pitfall affects ALL environment variables in the systemd unit, not just LLM_MODEL. In one session, three mismatches were found simultaneously:
- `HINDSIGHT_API_LLM_MODEL` — had `gemini-3.1-pro-preview` instead of `gemini-3-flash-preview` (40× cost difference)
- `HINDSIGHT_API_RERANKER_PROVIDER` — had `flashrank` instead of `zeroentropy`
- `HINDSIGHT_API_RERANKER_*_MODEL` — had `ms-marco-MiniLM-L-12-v2` instead of `zerank-2`

**Fix**: edit the systemd unit directly for ALL mismatched vars, then reload+restart:
```bash
sed -i 's/HINDSIGHT_API_LLM_MODEL=.*/HINDSIGHT_API_LLM_MODEL=gemini-3.1-flash-lite-preview/' /etc/systemd/system/hindsight-api.service
sed -i 's/HINDSIGHT_API_RERANKER_PROVIDER=.*/HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy/' /etc/systemd/system/hindsight-api.service
systemctl daemon-reload && systemctl restart hindsight-api
# Verify
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep -E 'LLM_MODEL|RERANKER'
```

Same check applies to `write-worker.service` and `hybrid-search.service` — always verify the running process env, not just the .env files.

### ZeroEntropy API Key Location
The ZeRank-2 API key is stored in:
- `/root/.hermes/hindsight/.env.service` as `HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=ze_...`
- Systemd unit: `Environment=HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=ze_...`

### Gemini Embed dimension mismatch
`gemini-embedding-2-preview` returns **3072 dimensions** by default. Qdrant collection expects 768. Always include `"output_dimensionality": 768` in the embed request body. Symptom: `Wrong input: Vector dimension error: expected dim: 768, got 3072`.

### Gemini 2.0-flash deprecated
`gemini-2.0-flash` is no longer available. Use `gemini-2.5-flash` for extraction LLM.

### ZeRank-2 endpoint
URL: `https://api.zeroentropy.dev/v1/models/rerank`
Payload: `{"model": "zerank-2", "query": "...", "documents": [...], "top_n": 5}`
Auth: `Authorization: Bearer ze_...`

## PG↔Qdrant Sync (Jarvis Memory System)

The PG↔Qdrant drift problem (entries added via retain API go to PG only, not Qdrant) has been solved by the Jarvis Memory System:

- **Sync Worker**: `/root/.hermes/services/jarvis/pg_qdrant_sync_worker.py`
  - `--dry-run`: show what would be synced
  - `--sample-run --limit N`: sync N entries
  - `--full-run`: complete backfill
  - `--incremental`: process outbox only
  - `--health`: sync health check

- **Memory Gateway**: `/root/.hermes/services/jarvis/memory_gateway.py` (port 8891)
  - Single access point for all agents
  - `/recall/fast` (Qdrant only, <800ms)
  - `/recall/balanced` (Qdrant+PG, <1500ms)
  - `/recall/deep` (PG full, <5000ms)

- **Outbox pattern**: New facts get `memory_outbox` entries → sync worker processes them → Qdrant updated

- **Full backfill performance**: ~500 entries/5.5min (Gemini Embedding 2, free tier). 7,692 entries ≈ 1.5h.

See `jarvis-memory-system` skill for full architecture.

## Dual-Path Recall Architecture

There are TWO independent recall paths — knowing which one does what is critical for debugging search quality:

| Path | Port | Backend | Scores | Coverage |
|---|---|---|---|
| Hindsight API `/memories/recall` | 8888 | PostgreSQL (embedding column) | Often weak/0.000 or text/recency-biased depending API version | Broad PG history |
| Hybrid Search `/recall` | 8889 | Qdrant (dense vectors) + reranker | Proper cosine/rerank scores | Only entries synced/vectorized into Qdrant |

Hermes' Hindsight plugin reads `~/.hermes/hindsight/config.json`. If `api_url` is `http://127.0.0.1:8888`, both auto-recall prefetch and the `hindsight_recall` tool call port 8888 (Hindsight API → PG). This means broad coverage but noisier ranking and potentially verbose context injection.

**Important terminology pitfall**: plugin `memory_mode: "hybrid"` does **not** mean PG+Qdrant hybrid search. In the plugin it means "auto context injection + tools enabled". The Qdrant hybrid-search service on port 8889 is separate and is not used unless the plugin/client is explicitly routed through it or a gateway layer calls it.

The dream cycle health checks, Memory Sniper, and direct hybrid-search probes use port 8889 (Hybrid Search → Qdrant), which has proper vector/reranker scoring but only covers entries processed by the write worker/sync pipeline.

**Implication**: Entries added via the retain API (connectors, manual retain) may land in PG before Qdrant. They are searchable via `hindsight_recall` on 8888 but may not appear in hybrid search or Memory Sniper until sync/reconcile processes them. The reconcile dry-run tracks this drift (`pg_unique_texts_absent_from_qdrant`).

### Debug checklist for "why did Hindsight inject so much/noisy context?"

1. Read `~/.hermes/hindsight/config.json` and check `api_url`, `memory_mode`, `recall_budget`, `auto_recall`, and `recall_prefetch_method`.
2. If `api_url` points to 8888, expect PG recall behavior, not Qdrant hybrid ranking.
3. Compare counts: PG `memory_units` vs Qdrant `/collections/memories` or `hybrid-search /health` `memories_count`.
4. Lower `recall_budget` or route auto-recall through 8889/Memory Gateway if injection is too verbose; use PG as deep fallback.

## Full Memory Stack Audit Runbook

Use this when asked for a complete memory-system checkup, not just a single endpoint fix. Audit the whole chain: config, systemd/Docker services, endpoints, PG/Qdrant integrity, read/write/retain/recall paths, benchmarks, logs/timers, cleanup, and final risk report.

### Audit order

1. Load `hindsight-debug-and-repair`, `hindsight-qdrant-hybrid-search`, and `hermes-agent` when Hermes/Hindsight configuration is involved.
2. Redact secrets before displaying config/env/logs. Never print API keys, tokens, full connection strings, or auth headers.
3. Check services and ports:
   - `systemctl status hindsight-api hybrid-search write-worker dream-cycle.timer`
   - `docker ps` for `qdrant` and `hindsight-pg`
   - health endpoints: `:8888/health`, `:8889/health`, `:8890/health`, Qdrant `:6333`
4. Inspect PG via schema introspection first. Do not assume columns like `source` exist. Confirm counts, embedding nulls/dimensions, extensions, duplicate groups, recent rows, async operation status, and orphan references in `unit_entities`/`memory_links`.
5. Inspect Qdrant collections (`memories`, `entities`), point counts, vector size/distance, and payload source distribution. Compare PG vs Qdrant cardinality, but report whether the difference is expected active-index behavior or a reconciliation risk.
6. Test runtime paths with process-level timeouts:
   - Use `curl --max-time` for retain/recall/write-worker tests. Python client timeouts can still hang during external LLM/provider calls.
   - Recall: `POST /v1/default/banks/walter/memories/recall` and `POST http://127.0.0.1:8889/recall`.
   - Retain: `POST /v1/default/banks/walter/memories` with `{"items":[...]}`.
   - Write worker: `POST http://127.0.0.1:8890/process` with durable, realistic facts. Prompts explicitly marked `test`, `temporary`, or `audit` may correctly return `facts=0` due to the extractor prompt.
7. Run official validation:
   - `python3 /root/.hermes/scripts/test_hindsight.py --verbose`
   - `python3 /root/.hermes/scripts/bench_hindsight.py`
8. Cleanup any audit artifacts explicitly created during the audit. Do not trust test scripts to fully clean themselves: after `test_hindsight.py` / `bench_hindsight.py`, explicitly check PG for markers like `TEST_SUITE:`, `BENCHMARK`, `MEMCHECK`, and `AUDIT_MEMORY_CHECK`. For PG, delete related rows from `memory_links` (`from_unit_id`/`to_unit_id`) and `unit_entities` (`unit_id`) before deleting `memory_units`. For Qdrant, scroll small collections and delete exact marker payload matches by point ID; snapshot/count before and after.
9. Scan maintenance/logs:
   - `journalctl -u hindsight-api -u hybrid-search -u write-worker --since '24 hours ago' -p warning..alert`
   - `docker logs --since 24h qdrant` and `docker logs --since 24h hindsight-pg`
   - `systemctl list-timers --all | grep -Ei 'hindsight|memory|dream|hermes'`
   - cron files only if relevant; this setup mainly uses `dream-cycle.timer`.
10. Final report should be concrete: OK/attention/critical by component, measured latencies, data integrity status, cleanup performed, risks, and prioritized actions.

### Audit findings to specifically check for

- PostgreSQL log spam from missing maintenance functions, e.g. repeated `SELECT * FROM schemas_with_pending_work()` every ~0.5s. If present, identify the caller before patching. Safe repair pattern: add an idempotent SQL helper function (`schemas_with_pending_work() RETURNS SETOF text`) and also patch the Python poller with a fallback/cache so the worker does not re-enter an error loop if the DB helper disappears.
- For PostgreSQL commands, prefer SQL via stdin with `docker exec -i hindsight-pg psql -U hindsight -d hindsight -t -A -F '|' -P pager=off`; inline escaped newlines can produce confusing `invalid command \nSELECT` errors.
- Inspect table schemas before cleanup. In this deployment `memory_links` uses `from_unit_id` and `to_unit_id`, not `source_unit_id`; deleting artifacts with the wrong column only creates noisy PG errors.
- Qdrant telemetry errors to `https://telemetry.qdrant.io/` are usually non-blocking noise. Disable telemetry or ignore if all local endpoints are healthy.
- `write-worker` may log `extracted_facts len=1` but `Normalized 0 facts` when Qwen returns an alternate schema like `type + subject + context + attribute + value + confidence`. Patch `normalize_facts()` to synthesize a `fact` string from those fields instead of dropping it silently.
- When testing the write worker, avoid content words like `test`, `temporary`, or `audit` if the goal is to verify durable extraction; the extraction prompt may correctly filter them as non-durable and return zero facts.
- For HTTP checks that may touch external LLM providers, use `curl --max-time`; Python `urllib`/client tests can hang until the outer harness timeout.
- If a Docker json log grew due to a loop, rotate/copytruncate it or configure Docker `json-file` rotation (`max-size`, `max-file`) before relying on `docker logs`; direct tail of the log file can be safer than scanning a huge log.
- Duplicate counts are not automatically delete-worthy. Report exact and near duplicates, but prefer dream-cycle/consolidation merge/invalidation over destructive manual deletes.
- PG/Qdrant count mismatches require interpretation. Qdrant may be the active fast index while PG stores broader history. Check `pg_unique_texts_absent_from_qdrant` in the reconcile dry-run to quantify drift. If Qdrant is intended to mirror PG, run reconciliation/migration. The dual-path recall architecture means PG-only entries ARE searchable (via port 8888) but lack proper vector scoring (scores=0.000).

## Benchmarks (Oracle ARM, 7.7k active memories, measured 2026-05-22)

| Component / Path | Time | Notes |
|---|---:|---|
| PG raw recent indexed query | ~0.6ms avg | Exact/status/date lookup; fastest for audit/current rows |
| PG simple text scan | ~1.5ms avg | Fine at small scale, not semantic recall |
| Qdrant raw vector search, warm | p50 ~34ms | Vector similarity only; cold calls can spike |
| Hybrid Search `:8889` | ~479ms avg | Gemini embedding + Qdrant + ZeRank-2 rerank |
| Hindsight PG recall `:8888` | ~2265ms avg | Broad PG recall, noisier ranking |
| Hybrid vs PG recall speedup | ~4.7× | End-to-end on this deployment |

Interpretation: PG is best for exact `fact_key`/audit/current-state queries; Qdrant is best for fuzzy semantic recall and context injection. Most end-to-end latency is embedding/reranking, not Qdrant itself.

## Historical Benchmarks (Oracle ARM, 284 memories)

| Component | Time | Notes |
|---|---|---|
| Gemini Embed 2 | ~530ms | API, incompressible network cost |
| Qdrant search | ~5ms | 40x faster than PG (200ms) |
| FlashRank rerank | ~1280ms | Local CPU, highly variable on ARM |
| ZeRank-2 rerank | ~390ms | API, consistent |
| **Total (ZeRank-2)** | **~970ms** | Min 747ms |
| Write batch (6 turns) | ~15s | Qwen 3.6 Flash (OpenRouter) + Gemini embed + upsert |

## Read/Write Path Separation

- **Read path MUST be synchronous/blocking** — the LLM needs memory BEFORE responding, not after
- **Write path MUST be async** — extraction runs in background, never blocks conversation
- Trigger write every ~10 exchanges or on context compression
- The write worker HTTP API: `POST /process` with `{"turns": [...], "bank_id": "walter"}`

## Memory Autopilot Supervisor (non-destructive)

Use this when Lucas wants the memory system to maintain itself invisibly without mutating memory data. It complements, but does not replace, the nocturnal dream cycle.

Installed pattern:
- Main script: `/root/.hermes/scripts/memory_autopilot.py`
- Policy helper: `/root/.hermes/scripts/memory_policy.py`
- Safe cleanup: `/root/.hermes/scripts/memory_safe_cleanup.py`
- Guarded exact PG dedup: `/root/.hermes/scripts/hindsight_pg_exact_dedup.py`
- Service: `memory-autopilot.service` with `--autofix safe`
- Timer: `memory-autopilot.timer`
- Guarded service/timer: `memory-guarded-maintenance.service` / `.timer`
- Reports: `/root/.hermes/logs/memory-autopilot/latest.json`, `alert-latest.json`, `status.log`, `service.log`, `safe-cleanup-latest.json`, `pg-exact-dedup-latest.json`
- Schedule: safe autopilot runs nightly around 06:10 UTC (`RandomizedDelaySec=300`) as a post-flight check after dream-cycle and guarded maintenance; guarded exact dedup runs daily around 05:37 UTC after dream-cycle.

What it does:
1. Detects if `dream-cycle.service` is active and defers to avoid competing with consolidation.
2. Runs stack checker and small `/recall` quality probes.
3. Tracks PG/Qdrant counts, embedding-null count, duplicate pressure, pending async ops, and PG↔Qdrant drift.
4. Runs `/root/.hermes/scripts/hindsight_reconcile_dryrun.py` periodically (default every 12h) and stores only a compact summary in the main report.
5. In `--autofix safe`, automatically cleans generated test artifacts, deletes Qdrant `invalidated=true` points, restarts dead core memory services, and rotates large Docker logs.
6. In guarded maintenance, deduplicates exact normalized PG `memory_units` with snapshot + bounded apply: repoints `unit_entities` and `memory_links`, avoids self-links/duplicate links, then deletes only verified duplicate rows.
7. Treats PG/Qdrant count drift as expected when Qdrant is healthy under the active-index policy: PG is broad history/audit; Qdrant is the active/canonical fast recall set.

Validation commands:
```bash
/root/.hermes/hermes-agent/venv/bin/python3 -m py_compile /root/.hermes/scripts/memory_autopilot.py
/root/.hermes/hermes-agent/venv/bin/python3 /root/.hermes/scripts/memory_autopilot.py --mode quick --output /root/.hermes/logs/memory-autopilot/latest.json
systemd-analyze verify /etc/systemd/system/memory-autopilot.service /etc/systemd/system/memory-autopilot.timer
systemctl start memory-autopilot.service
systemctl show memory-autopilot.service --property=Result,ExecMainStatus,ActiveState,SubState --no-pager
systemctl list-timers --all --no-pager | grep -Ei 'memory-autopilot|dream-cycle|hindsight-stack-check|hermes-docker-log-rotate'
```

Pitfalls:
- Default mode is observe-only, but production uses `--autofix safe`; safe fixes must remain limited to unambiguous hygiene (test markers, invalidated Qdrant points, dead service restart, log rotation).
- Guarded dedup must snapshot before apply and stay bounded (`--limit-groups`, `--max-delete`). Never do semantic PG dedup or mass backfill in the hourly timer.
- Do not read or print env files/drop-ins containing credentials. Reports must redact secret-like strings and should store counts/snippets only. Redact generated dedup reports too, because exact duplicates can include credential memories.
- Do not overlap with `dream-cycle.service`; defer if it is active.
- Treat PG/Qdrant drift as expected while Qdrant recall probes pass and Qdrant is the active fast index. Backfill only classified recent/high-value facts, never the whole PG history blindly.

## Dream Cycle (Nocturnal Consolidation)

Script: `/root/.hermes/services/dream_cycle.py`
Wrapper: `/root/.hermes/scripts/run_dream_cycle.sh` (loads env vars)
Timer: `dream-cycle.timer` → 4h05 UTC daily (±5min random delay)
Logs: `/root/.hermes/logs/dream_status.log` + `dream_last_run.json`

### Three Tasks

1. **Hard Delete** — Scans Qdrant for `invalidated=True` facts, permanently deletes them. Reduces collection bloat from write-path invalidation.

2. **Deduplication** — Loads active Qdrant facts with vectors, computes pairwise cosine similarity. Groups with sim > 0.95 are sent to the consolidation LLM for merge decision. Consolidated facts MUST be written to PostgreSQL first via the memory truth-store path, then synced to Qdrant through `memory_outbox` / `pg_qdrant_sync_worker.py`. Never create direct `dream_dedup` Qdrant-only points; they become orphans without `pg_memory_id` and break PG→Qdrant reconciliation. Old duplicate PG facts should be marked `superseded/canonical=false/valid_until=now/qdrant_sync_status=pending`, then the sync worker deletes their Qdrant points.

3. **Health Check** — Runs 3 recall queries against known entities (Scena, Lucas, Hindsight). Logs PASS/FAIL with ZeRank-2 scores to `dream_status.log`.

### Dream Cycle Pitfalls

- **Script corruption from secret redaction**: If `dream_cycle.py` shows `SyntaxError: unterminated string literal` at API key lines, the file was corrupted by a redaction tool replacing `os.getenv("KEY", "")` with `os.get...EY", "")`. Fix: replace with proper `os.getenv()` calls. See `references/memory-connectors.md` for detection/fix commands.
- **Model name must include `-preview` suffix**: Default `gemini-3.1-flash-lite` → 403 Forbidden. Correct: `gemini-3.1-flash-lite-preview`.
- **Cosine threshold 0.92 is too aggressive** — produces 50+ groups on 280 facts. Use 0.95 (produces ~15 groups).
- **Limit to 15 groups per run** — each group takes ~15s (extraction LLM + Gemini + Qdrant). 50 groups = 12min, too long for cron.
- **Dream-cycle must not write Qdrant directly** — route consolidated facts through PostgreSQL truth-store first (`upsert_facts_to_pg` or equivalent), then let `memory_outbox`/`pg_qdrant_sync_worker.py` update Qdrant. Direct `qdrant.upsert(source="dream_dedup")` creates orphan points without `pg_memory_id`; back them up and delete from the active index if found.
- **Qdrant payload bank label matters** — `hybrid_search.py` filters on `bank_id="walter"`. PG `memory_facts.scope` may be `global`; do not copy `scope` into `bank_id`. `pg_qdrant_sync_worker.py` must set payload `bank_id` from `BANK_ID` env/default `walter`, while keeping `scope` separately. Symptom: Qdrant `/health` shows thousands of points but `/recall` returns `candidates_count=0` / `reason=no_documents`.
- **Gemini embed dimension mismatch** — `gemini-embedding-2-preview` returns 3072 dims by default. Must include `"output_dimensionality": 768` in the request body.
- **qdrant variable scope in async** — pass `qdrant: QdrantClient` as parameter to `merge_duplicates()`, don't call `get_qdrant()` inside the async function.
- **Health checks must use REAL facts** — test data (Yamaha, Nextcloud port, etc.) gets deleted. Use stable facts like Scena Factory, Lucas, Hindsight.
- **Model selection matters** — see `references/model-selection-for-extraction-consolidation.md` for benchmark-backed picks. The consolidation LLM (dedup merge decisions) needs good reasoning; `gemini-3.1-pro-preview` (intel=57, free tier via AI Studio) is recommended over low-intelligence models.

### Systemd Timer

```bash
# /etc/systemd/system/dream-cycle.service
[Unit]
Description=Hindsight Dream Cycle - Consolidation
After=network.target qdrant.service hybrid-search.service write-worker.service

[Service]
Type=oneshot
ExecStart=/root/.hermes/scripts/run_dream_cycle.sh

# /etc/systemd/system/dream-cycle.timer
[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
RandomizedDelaySec=300
```

### Test Data Cleanup

After running integration tests, clean test facts from Qdrant:
```python
# Match by source="write_worker" + test patterns (Yamaha, Nextcloud 8080, Plex port, NAS Synology, Oracle IP)
# Also check source="dream_dedup" for contaminated consolidated facts
# Use regex patterns, not exact match
```

See `references/pg-qdrant-lifecycle-hardening-2026-05-22.md` for the production hardening pattern: PG truth store, `fact_key`/`value_hash`, TTL expiry, outbox sync, deterministic Qdrant IDs, dream-cycle consolidation through PG, orphan cleanup, and measured PG vs Qdrant latencies.

See **`references/dual-path-recall-architecture.md`** for the full PG vs Qdrant recall path breakdown, including which endpoints return what scores and coverage.

See **`references/voice-fastpath-and-noisy-ingestion-2026-05-22.md`** for the validated Gemini Live → voice_router → Qdrant fast-path, the `bank_id=walter` payload pitfall, and the Beeper/WhatsApp noisy ingestion quarantine pattern.

## Scaling to 100k+ Memories

- Qdrant handles millions of vectors natively
- ZeRank-2 free tier: 500K bytes/min (tight at scale) — Starter $50/mo for 2M TPM
- Consider MAX_CANDIDATES=25 to keep rerank fast
- BM25 hybrid search becomes important at scale (sparse vectors in Qdrant)
- Dream cycle keeps collection clean: hard delete invalidated + dedup near-identicals
