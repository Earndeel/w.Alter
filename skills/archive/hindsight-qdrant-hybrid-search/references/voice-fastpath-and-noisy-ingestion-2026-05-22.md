# Voice Fast Path + Noisy External Ingestion — 2026-05-22

## What happened

During live voice testing, Gemini Live / voice-router successfully called memory without routing through the full Hermes agent:

```text
User speech → Gemini 3.1 Flash Live → /api/voice-router → context_lookup → hybrid-search/Qdrant → spoken response
```

Measured smoke tests on W.Alter:
- `https://127.0.0.1:8765/api/voice-router` local proxy: ~1.3s, route `context_lookup`, useful spoken response.
- Direct voice-router `http://127.0.0.1:12110/route`: ~1.6s.
- Direct hybrid-search `http://127.0.0.1:8889/recall`: ~1.6s with 3 results after payload repair.

## Critical payload pitfall

`hybrid_search.py` filters Qdrant by:

```python
FieldCondition(key="bank_id", match=MatchValue(value="walter"))
```

PG `memory_facts.scope` can be `global`. Do **not** copy `scope` into Qdrant payload `bank_id`; keep them separate:

```python
payload["scope"] = scope          # e.g. global
payload["bank_id"] = BANK_ID      # default walter
```

Symptom of the bug:

```text
Qdrant collection has thousands of points
/recall returns candidates_count=0, reason=no_documents
voice_router may fall back to another memory path or answer inconsistently
```

Repair pattern:
1. Patch `pg_qdrant_sync_worker.py` to set `BANK_ID = os.getenv("BANK_ID", "walter")` and payload `bank_id=BANK_ID`.
2. Remap existing Qdrant payloads with `q.set_payload(..., payload={"bank_id":"walter"})` for active points.
3. Re-test direct `/recall` and `/api/voice-router`.

## Noisy external chat ingestion pitfall

`memory_connectors.py` previously ingested Beeper/WhatsApp personal messages into Hindsight, creating durable memories like birthday/karaoke chatter. Those polluted both PG and Qdrant recall.

Fix pattern:
- Disable personal Beeper ingestion by default unless `HINDSIGHT_INGEST_PERSONAL_CHATS=1`.
- Add a conservative `is_durable_external_message()` gate: only explicit markers (`[SAVE]`, `#remember`, `à retenir`, etc.) or W.Alter/Hermes operational terms should enter durable memory.
- For already-ingested garbage, backup matching rows first, then quarantine `memory_facts` (`status='invalidated'`, `canonical=false`, `qdrant_sync_status='pending'`), delete legacy `memory_units` rows and dependent links, delete matching Qdrant points, then run `pg_qdrant_sync_worker.py --incremental`.

Example verification:

```sql
SELECT count(*) FROM memory_facts
WHERE status='active' AND (content ILIKE '%malika%' OR content ILIKE '%karaoke%' OR content ILIKE '%karaoké%');
```

Expected after cleanup: `0` in active PG and `0` matching Qdrant payloads.

## Practical voice rule

For ultra-fluid speech-to-speech:
- Use `voice_router.context_lookup` for “tu te souviens…” style memory lookups.
- Use Qdrant/hybrid-search directly for fast context.
- Escalate to full Hermes only for deep reasoning, code, deploys, or long-running work.
