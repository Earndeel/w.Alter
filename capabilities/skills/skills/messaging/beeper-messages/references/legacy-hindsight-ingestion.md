# beeper-messages — Hindsight-era ingestion notes (verbatim, moved 2026-11-01)

Hindsight was retired on 2026-10-19; Beeper ingestion is now the walter-memory connector.

## Hindsight Memory Integration

To ingest Beeper messages into Hindsight long-term memory, use the connector script at `/root/.hermes/scripts/memory_connectors.py --beeper`. Key details:

- Fetches from `/v1/chats` + `/v1/chats/{id}/messages` (NOT `/v0/messages` which 404s)
- Tracks last-seen timestamp per chat in `~/.hermes/scripts/.connector_state.json`
- Retains via `POST /v1/default/banks/walter/memories` with `{"items": [{"content": "...", ...}]}`
- Field name is `content`, NOT `text`
- Tokens must be read from vault (cron env has no env vars)

See `hindsight-qdrant-hybrid-search` skill → `references/memory-connectors.md` for full details.

## Memory Connector Integration

The memory connector (`/root/.hermes/scripts/memory_connectors.py`) ingests Beeper messages into Hindsight. Key learnings:

- **API endpoint**: Use `/v1/chats` (NOT `/v0/messages` which returns 404)
- **Token**: Read from vault `vault get beeper/token` (not env var — cron doesn't have it)
- **State tracking**: Incremental via `~/.hermes/scripts/.connector_state.json` — stores `beeper_last_seen` per chat ID
- **Hindsight endpoint**: `POST /v1/default/banks/walter/memories` with `{"items": [{"content": "..."}]}`
- **Cron schedule**: Runs at 5h daily via Hermes cron (job: Memory External Connectors)


## Lines rewritten in SKILL.md on 2026-11-01

- was: 1. Hindsight memory (`hindsight_recall`) — fragments of past sessions
- was: 1. **Check Hindsight FIRST** — `hindsight_recall` with the contact name.
- was: If Hindsight returns a match with
- was: check Hindsight memory — the contact likely existed
