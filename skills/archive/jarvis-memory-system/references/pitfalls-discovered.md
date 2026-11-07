# Pitfalls Discovered During Jarvis Build (2026-05-18 to 2026-05-19)

## Embedding Dimension Mismatch
- Gemini Embedding 2 returns **3072 dimensions** by default
- Qdrant collection `memories` is configured for **768 dimensions**
- Write Worker passes `"outputDimensionality": 768` — sync worker MUST do the same
- Symptom: Qdrant returns `400 Bad Request: Vector dimension error: expected dim: 768, got 3072`
- Fix: Add `"outputDimensionality": 768` to the embedContent request body

## Python 3.11 f-string Backslash Restriction
- Python 3.11 does NOT allow backslashes inside f-string expressions
- `f"{x.replace('"', '\"')}"` → SyntaxError
- Fix: extract to a variable first: `escaped = x.replace('"', '\"'); f"{escaped}"`
- Affected: memory_gateway.py line 436

## PG Column Naming
- `memory_units` uses `text` for the main content column
- `memory_facts` (new Jarvis table) uses `content`
- `memory_events` uses `content`
- Always check which table you're querying before writing SQL

## Qdrant Point ID Format
- Qdrant expects UUID strings (e.g., `001d9cf0-0454-4862-9d5e-52d8c70eba49`)
- MD5 hex strings work as valid UUIDs when formatted properly
- hashlib.md5(id.encode()).hexdigest() produces a valid 32-char hex string

## Background Process Issues
- `tee` in background pipes fails with "open terminal failed: not a terminal"
- `nohup ... &` is blocked by Hermes terminal tool (must use terminal background=true)
- Background processes with `|` pipe to tee don't work — redirect via script wrapper instead
- Solution: create a bash wrapper script with `exec > file 2>&1`, then run that script in background

## Variable Shadowing in Sync Worker
- Loop variable `eligible` shadowed by function call `eligible, reason = is_eligible_for_qdrant(...)`
- When the loop also needs the variable, rename to `fact_eligible`
- Symptom: `NameError: name 'eligible' is not defined`

## Hindsight API Endpoints
- Retain: `POST /v1/default/banks/{bank_id}/memories` (NOT `/documents`)
- Body: `{"items": [{"content": "...", "context": "...", "tags": [...]}]}`
- Field name is `content`, not `text`
- Recall: `POST /v1/default/banks/{bank_id}/memories/recall`

## Beeper API v1 Endpoints (not v0)
- Chat list: `GET /v1/chats`
- Messages: `GET /v1/chats/{chat_id}/messages?limit=N`
- Old `/v0/messages` endpoint returns 404
- Filter `type == "single"` for 1-on-1 chats

## Memory Connectors Token Access
- `os.environ.get("TELEGRAM_BOT_TOKEN")` fails in cron environment (env vars not set)
- Must read from vault: `vault get telegram/bot_token`
- Same for Beeper: `vault get beeper/token`

## Full Backfill Performance
- ~500 entries per 5.5 minutes (Gemini Embedding 2, rate-limited free tier)
- 7,692 entries ≈ ~1.5 hours total
- Run in batches of 500-2000 via foreground terminal calls
- Each batch: `full_run(limit=N)` with timeout=600s

## Dream Cycle Corrupted Lines
- Lines 40/43 had `os.get...EY` instead of `os.getenv("API_KEY", "")`
- Caused by a previous search-and-replace that truncated the code
- Also: model name `gemini-3.1-flash-lite` → correct is `gemini-3.1-flash-lite-preview`

## Qdrant Named Vectors API (v1.17)
- Collection with named vectors requires `{"name": "dense", "vector": [...]}` in search
- Using `{"dense": [...]}` returns 400 "Wrong input: Not existing vector name error"
- `/points/search` and `/points/query` are different endpoints with different body formats
- Search: `{"vector": {"name": "dense", "vector": [...]}, "limit": N}`
- Query: `{"query": {"dense": [...]}, "limit": N, "using": "dense"}`
- Result parsing differs too: search returns `result` as array, query returns `result.points`

## Mixing Embedding Models in Same Collection
- **NEVER** mix vectors from different embedding models in one Qdrant collection
- Cosine similarity is meaningless across different embedding spaces
- all-MiniLM-L6-v2 (384d) vectors are INCOMPATIBLE with Gemini Embedding 2 (768d) vectors
- Even padding 384d→768d with zeros doesn't help — the dimensions don't correspond
- Zero-padding preserves cosine ONLY when BOTH vectors are padded from the same model
- When model A's dim 1-384 ≠ model B's dim 1-384 semantically, padding is meaningless
- Solution: separate collections per embedding model (memories=768d, memories_local=384d)
- Symptom: searches return results but with very low scores (0.03-0.09 vs normal 0.5-0.8)
- We tested this explicitly: padded 384d→768d scored 0.03-0.09, same query on proper 384d collection scored 0.5-0.8

## Gemini Embedding API Rate Limiting (429)
- Free tier has ~1500 requests/day limit
- Backfill of 7,692 entries + query testing exhausted the quota
- Symptom: hybrid-search returns 500 errors, recall/fast returns 0 results
- Recovery: wait for quota reset or use local embedding (recall/ultra) as primary
- Local embedding is immune to API rate limits — always works

## Voice-Call Server Browser WebSocket Stale State
- After restarting hermes-voice-call service, browser WebSocket becomes stale
- Server logs show: connect → 2 POST /calls/event → disconnect (cycle repeats)
- Token creation succeeds (200 OK) but WebSocket closes immediately
- **Fix: User MUST hard-refresh the browser page (Ctrl+Shift+R / Cmd+Shift+R)**
- This is a browser-side issue — server-side is healthy
- Restart order matters: restart voice-router BEFORE voice-call to avoid transient failures

## Local Embedding Service Startup
- sentence-transformers downloads model from HuggingFace on first load (~2-3s)
- Systemd service may appear "failed" during download — check journalctl logs
- Model is cached after first download (~/.cache/huggingface/)
- CPU inference: ~11ms per embedding (all-MiniLM-L6-v2 on ARM64)
- Batch encoding: ~56 facts/second for backfill

## Voice Recall — 3-Layer Strategy
- Layer 1 (Pre-load): Context Builder at call start, 0ms during call
- Layer 2 (Cache): LRU in Memory Gateway, <5ms for repeated queries
- Layer 3 (Local): sentence-transformers + Qdrant, ~35ms for new queries
- Use `/recall/ultra` endpoint for voice, falls back to `/recall/fast` on failure
