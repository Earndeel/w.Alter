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
