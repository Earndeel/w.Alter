# Kardex Implementation Status (as of 2026-05-20)

## Current Infrastructure

- **PG**: `hindsight-pg`, schema `kardex`
- **Qdrant**: collection `kardex_ctx` (768d, Gemini Embedding) — NOT YET CREATED
- **Connection**: Verify IP with `docker inspect hindsight-pg | grep IPAddress` (commonly `172.17.0.3` or `172.17.0.4` — changes on container recreate)

## Schema (7 tables + 3 views)

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

**Schema file**: `/root/.hermes/services/kardex/schema.sql`

## V2 Migration (planned, not yet applied)

Adds 32 tables + 7 views including: `raw_items`, `source_threads`, `identity_clusters`, `identity_links`, `identity_mentions`, `evidence`, `claims`, `claim_evidence`, `conversation_episodes`, `episode_items`, `relationship_events`, `preferences`, `boundaries`, `psychological_claims`, `communication_patterns`, `relationship_metrics`, `open_loops`, `action_recommendations`, `style_profiles`, `recommendations`, `health_notes`, `social_graph`, `context_packs`, `corrections`, `extraction_runs`.

Migration file: `/root/.hermes/services/kardex/migrations/002_kardex_v2.sql`

## Sources

| Source | Status | Data |
|--------|--------|------|
| Beeper | ✅ Accessible | IG DMs, Bumble, Telegram, iMessage, Facebook — 24 contacts |
| Email (Gmail) | 🔴 Future | Emails, attachments |
| Android smartphone | 🔴 Future | SMS, WhatsApp native, calls, contacts, location |

## Scripts

- **Schema**: `/root/.hermes/services/kardex/schema.sql`
- **Beeper sync**: `/root/.hermes/services/kardex/scripts/beeper_sync.py`
- **Context builder**: `/root/.hermes/services/kardex/scripts/build_context.py`

### Usage

```bash
# Sync specific contact (by Beeper handle)
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --contact cl_ld8228

# Sync all single chats
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --all

# Dry run
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --contact cl_ld8228 --dry-run

# Build context (names, events, actions, personality via LLM)
python3 /root/.hermes/services/kardex/scripts/build_context.py --contact-id 1
```

## LLM for Extraction

**Model**: `meta-llama/llama-4-scout` via OpenRouter (~$0.009 per 500 messages)

**Do NOT claim Gemini 2.5 Flash is free on OpenRouter** — it is NOT. Free models are frequently rate-limited (429). `llama-4-scout` is cheap and reliably available.

## Implementation Status

- ✅ Schema PG created (7 tables + 3 views)
- ✅ Beeper sync script working
- ✅ Context builder with LLM extraction
- ✅ First contact synced: Annie (CL) — 7,411 messages, 4 events, 3 actions
- ✅ Kérian_wmb synced — 183 messages, personality profile extracted via LLM
- ✅ Name/nickname extraction via regex
- ✅ Personality profiling via LLM
- ⏳ Multimodal analysis not yet integrated
- ⏳ Qdrant collection `kardex_ctx` not yet created
- ⏳ API endpoint (port 8897) not yet built
- ⏳ Style learning not yet built
- ⏳ Auto-reply not yet built

## Key Design Decisions

- Same PG container (hindsight-pg), separate schema `kardex` — isolation without new infrastructure
- NOT merged into Jarvis memory (public schema) — Kardex is contact-centric, Jarvis is fact-centric
- Qdrant collection `kardex_ctx` (future) for semantic search across conversations
- Events and Actions are extracted automatically from conversations via NLP

## Pitfalls (Implementation-Specific)

- **PG connection IP changes on container recreate**: Both `beeper_sync.py` and `build_context.py` hardcode `DB_HOST`. After `docker-compose down/up` or container recreation, the IP changes. Always verify with `docker inspect hindsight-pg | grep IPAddress` and update both scripts.
- **Beeper chat pagination**: API returns 25 chats/page. Contacts beyond page 15 are missed with default `--chat-pages=15`. Use `--chat-pages 30` or higher for full coverage (719 chats = 29 pages as of June 2026).
- **Beeper handle case/accent matching**: `--contact` search is case-insensitive Python `in`, but the Beeper chat title may include accents (e.g., `Kérian_wmb`). Searching `kerian` works; the accent is handled by Python's casefold.
- **PG schema isolation**: Always prefix queries with `kardex.`
- **Event extraction via regex is noisy**: 800 events for one 8000-message conversation. Use LLM-based extraction.
- **Beeper handle != real name**: Chat titles are handles (e.g., `cl_ld8228`), not display names.
- **Message cleaning**: Strip HTML tags, Instagram "Reacted to @..." prefixes, duplicate URLs before inserting.
- **Pagination cap**: Full history for active chats can be 400+ pages (8000+ messages). Cap at ~400 pages.
- **No auto-reply yet**: Text-only sync for now, no outbound actions.
