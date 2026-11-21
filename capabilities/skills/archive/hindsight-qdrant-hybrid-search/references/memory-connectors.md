# Memory Connectors — Telegram/Beeper → Hindsight Integration

## Overview

The memory connectors ingest messages from external platforms (Telegram, Beeper) into Hindsight for long-term memory. They run as a Hermes cron job (`Memory External Connectors`, daily 5h UTC).

## Script

`/root/.hermes/scripts/memory_connectors.py`

### State Tracking

Incremental state in `~/.hermes/scripts/.connector_state.json`:
```json
{
  "telegram_last_update": 123456789,
  "beeper_last_seen": {
    "!chat_id:beeper.local": "2026-05-18T18:45:50.954Z"
  },
  "beeper_last_run": "2026-05-18T19:26:54.252879+00:00"
}
```

### Token Retrieval

Always read tokens from the vault, never from environment variables (cron env is empty):
```python
def vault_get(key):
    result = subprocess.run(["vault", "get", key], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else None
```

## Hindsight Retain API

**Endpoint**: `POST /v1/default/banks/{bank_id}/memories`

**Payload format** (critical — wrong field names cause 422):
```json
{
  "items": [
    {
      "content": "The actual message content",
      "context": "beeper:chat_id or telegram:chat_id",
      "tags": ["beeper", "network:whatsapp", "chat:Name"]
    }
  ]
}
```

**Common mistakes**:
- `/documents` endpoint → 405 Method Not Allowed (correct: `/memories`)
- `"text"` field → 422 validation error (correct: `"content"`)
- Missing `items` wrapper → 422 "Field required"

## Beeper Integration

**Correct API flow**:
1. `GET /v1/chats` → list all chats
2. Filter `type == "single"` (exclude groups)
3. `GET /v1/chats/{id}/messages?limit=10` → fetch recent messages per chat
4. Track `timestamp` of newest message per chat in state file
5. Only ingest messages with `timestamp > last_seen[cid]`

**Wrong endpoint**: `/v0/messages` → 404 Not Found

**Limit**: Process max 10 chats per run to avoid rate limits and long execution.

## Telegram Integration

**Pitfall**: `getUpdates` returns 409 Conflict if Hermes gateway is already polling the same bot. Solutions:
- Skip Telegram in the connector (gateway already ingests via `hindsight_retain` during conversations)
- Use a separate bot token for memory ingestion
- Use `drop_pending_updates=True` on first run

## Batch Processing

Batch items in groups of 20 before calling the retain API:
```python
for i in range(0, len(items), 20):
    batch = items[i:i+20]
    result = hindsight_retain(batch)
```

## Testing

```bash
# Dry run (fetches but doesn't retain)
python3 memory_connectors.py --all --dry-run

# Real run (fetches + retains)
python3 memory_connectors.py --all

# Specific platform
python3 memory_connectors.py --beeper
python3 memory_connectors.py --telegram --chat-id 1146774717
```

## Dream Cycle Script Corruption Pitfall

The dream_cycle.py script at `/root/.hermes/services/dream_cycle.py` can become corrupted when secrets are redacted from files. The redaction tool may replace `os.getenv("OPENROUTER_API_KEY", "")` with `os.get...EY", "")`, creating a Python SyntaxError that silently breaks the dream cycle for weeks.

**Symptoms**: `dream-cycle.service` fails with `SyntaxError: unterminated string literal` at line containing API key.

**Fix**: Replace corrupted lines with proper `os.getenv()` calls:
```python
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
```

**Detection**: `grep -n 'os\.get\.\.\.' /root/.hermes/services/dream_cycle.py`

**Model name pitfall**: The extraction model default must be `gemini-3.1-flash-lite-preview` (not `gemini-3.1-flash-lite`). Missing `-preview` suffix causes 403 Forbidden from Gemini API.

## Guarded Maintenance max-delete Pitfall

The `memory-guarded-maintenance.service` runs with `--max-delete 50` by default. If there are 25 duplicate groups with 81+ total duplicate rows, the script blocks and does nothing (`planned delete 81 exceeds max_delete 50`).

**Fix**: Increase to `--max-delete 200` in the systemd unit:
```bash
sed -i 's/--max-delete 50/--max-delete 200/' /etc/systemd/system/memory-guarded-maintenance.service
systemctl daemon-reload
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
