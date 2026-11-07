---
name: kardex
description: "Kardex — Contact intelligence system. Multi-source contact aggregation (Beeper, email, future Android), media analysis, event extraction, per-contact context profiles. Schema PG `kardex` in hindsight-pg."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [contacts, kardex, beeper, memory, context]
---

# Kardex — Contact Intelligence System

Unified contact database that aggregates all communication sources, analyzes media, and maintains evolving per-contact profiles.

**Name origin:** Like a medical chart (fiche patient), but for relationships.

## Architecture

```
Sources → Ingestion Pipeline → PostgreSQL (kardex schema) → Qdrant (kardex_ctx) → Context Builder → API
```

**PG (hindsight-pg)** = source of truth, schema `kardex`
**Qdrant** = semantic search, collection `kardex_ctx` (768d, Gemini Embedding)

## Sources

| Source | Status | Data |
|--------|--------|------|
| Beeper | ✅ Accessible | IG DMs, Bumble, Telegram, iMessage, Facebook — 24 contacts |
| Email (Gmail) | 🔴 Future | Emails, attachments |
| Android smartphone | 🔴 Future | SMS, WhatsApp native, calls, contacts, location |

## Schema (PostgreSQL, schema `kardex`)

7 tables + 3 views in `hindsight-pg`:

| Table | Purpose |
|-------|---------|
| `contacts` (30 cols) | Central profile — identity, relationship, personality, interests, AI synthesis |
| `channels` (8 cols) | Communication platforms per contact (IG, Telegram, email, SMS...) |
| `messages` (12 cols) | All messages, all sources |
| `media` (15 cols) | Images, videos, voice notes with AI analysis |
| `events` (16 cols) | Extracted events (birthdays, travel, meetings, deadlines) |
| `actions` (11 cols) | Things to do (reply, call, plan, follow up) |
| `sync_state` (9 cols) | Sync cursor per source |

Views: `contact_summary`, `upcoming_events`, `pending_actions`

**Schema file:** `/root/.hermes/services/kardex/schema.sql`

## Key Design Decisions

- **Same PG container** (hindsight-pg), separate schema `kardex` — isolation without new infrastructure
- **NOT merged into Jarvis memory** (public schema) — Kardex is contact-centric, Jarvis is fact-centric
- **Qdrant collection `kardex_ctx`** (future) for semantic search across conversations
- **Events and Actions** are extracted automatically from conversations via NLP
- **Contact profiles** are AI-synthesized from messages + media analyses

## Future Features (planned, not yet built)

1. **Style learning** — analyze Lucas's messages to calibrate auto-reply tone
2. **Auto-reply** — respond to conversations on Lucas's behalf when indisponible
3. **Periodic reports** — briefing on conversation status, pending actions, upcoming events
4. **Email connector** — Gmail/IMAP integration
5. **Android connector** — SMS, WhatsApp, calls via smartphone access

## Integration Points

- **Jarvis Context Builder (8893)** — pre-loads Kardex contact profile before voice calls
- **Memory Gateway (8891)** — new `/recall/contact` endpoint for contact-specific context
- **Beeper sync** — fills messages + media tables (not yet automated)

## Implementation Status (as of 2026-05-20)

- ✅ Schema PG created (7 tables + 3 views)
- ✅ Beeper sync script working (`beeper_sync.py`)
- ✅ Context builder with LLM extraction (`build_context.py`)
- ✅ First contact synced: Annie (CL) — 7,411 messages, 4 events, 3 actions
- ✅ Name/nickname extraction via regex
- ✅ Personality profiling via LLM
- ✅ PG connection verified: host `172.17.0.4`, user/pass `hindsight/hindsight`
- ⏳ Multimodal analysis not yet integrated
- ⏳ Qdrant collection `kardex_ctx` not yet created
- ⏳ API endpoint (port 8897) not yet built
- ⏳ Style learning not yet built
- ⏳ Auto-reply not yet built

## Scripts

- **Schema**: `/root/.hermes/services/kardex/schema.sql`
- **Beeper sync**: `/root/.hermes/services/kardex/scripts/beeper_sync.py`
- **Context builder**: `/root/.hermes/services/kardex/scripts/build_context.py`

```bash
# Sync specific contact (by Beeper handle)
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --contact cl_ld8228

# Sync all single chats
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --all

# Dry run (no DB writes)
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --contact cl_ld8228 --dry-run

# Build context (names, events, actions, personality via LLM)
python3 /root/.hermes/services/kardex/scripts/build_context.py --contact-id 1
```

## LLM for Extraction

**Model:** `meta-llama/llama-4-scout` via OpenRouter (~$0.009 per 500 messages)

**Do NOT claim Gemini 2.5 Flash is free on OpenRouter** — it is NOT. Free models (deepseek-v4-flash:free, qwen3-coder:free) are frequently rate-limited (429). Always test availability before committing. `llama-4-scout` is cheap and reliably available.

Extraction types:
1. **Names/Nicknames** — regex (no LLM needed), scans for pet names and proper nouns
2. **Events** — LLM reads last 300 messages, extracts travel/meetings/birthdays/plans with dates
3. **Actions** — LLM reads last 50 messages, finds unanswered messages/promises/follow-ups
4. **Personality** — LLM reads 200 messages, builds trait/style/interest profile

## Database Connection

```python
import psycopg2
conn = psycopg2.connect(
    host="172.17.0.4",  # Docker internal IP, NOT localhost
    port=5432,
    dbname="hindsight",
    user="hindsight",
    password="hindsight"
)
```

## Pitfalls

- **Schema naming**: Lucas prefers "W.Alter memory" over "Jarvis" — Jarvis is internal codename only
- **PG connection**: Must use Docker internal IP `172.17.0.4`, NOT `localhost` (no port binding to host)
- **PG schema isolation**: Kardex tables are in schema `kardex`, NOT `public`. Always prefix queries with `kardex.`
- **Event extraction via regex is noisy**: Simple patterns (e.g., "bkk", "taiwan") match too frequently. Use LLM-based extraction for production quality. The regex approach produced 800 events for one 8000-message conversation.
- **Beeper handle != real name**: Chat titles are handles (e.g., `cl_ld8228`), not display names. Need manual mapping or LLM inference from conversation content.
- **Message cleaning**: Strip HTML tags, Instagram "Reacted to @..." prefixes, and duplicate URLs before inserting. Empty messages (after cleaning) should be skipped.
- **Pagination cap**: Full history for active chats can be 400+ pages (8000+ messages). Cap at ~400 pages.
- **No auto-reply yet**: Do NOT respond to conversations automatically. Text-only sync for now, no outbound actions until style learning is built.
