---
name: contact-intelligence-systems
description: "Build and operate evidence-backed multi-source contact intelligence systems (Kardex-style): ingest messages/media, resolve identities, extract relationship context, maintain dossiers, and inject relevant context only when useful."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [contacts, memory, relationship-intelligence, ingestion, qdrant, postgres, multimodal, kardex]
---

# Contact Intelligence Systems

> **State on 2026-11-01.** Kardex is now the `kardex` schema of Walter Memory (decision A10, 2026-10-11), fed only by walter-memory processors from `core.events` and read through `person_lookup` / `memory_context`. Qdrant and `kardex-hindsight-sync.timer` are retired: semantic search is `search.chunks` (pgvector). Read the Qdrant sections below as design history; check `/walter/docs/ARCHITECTURE.md` before building anything.

Use this skill when Monsieur asks to build, extend, audit, or operate a Kardex-style system: a living contact dossier that aggregates conversations across Beeper, Instagram, Facebook Messenger, WhatsApp, iMessage, Gmail, Android/SMS/calls, images, audio, and video.

## Core Principle

A contact intelligence system is **not** a flat summary. It is an evidence-backed temporal dossier:

```text
raw source data
→ normalized immutable records
→ identity resolution
→ episode segmentation
→ evidence-backed claims
→ preferences / events / psychology / style / open loops
→ contact context packs injected only when useful
```

PG is the source of truth. Qdrant is a derived semantic index. Never reverse that, unless one enjoys archaeology after data corruption.

## Mandatory Architecture

### 1. Raw data stays immutable
Store raw normalized items from every source before synthesis:
- source: `beeper`, `gmail`, `android_sms`, `whatsapp`, `imessage`, `call_log`, etc.
- external thread/message IDs
- participants
- timestamps
- direction
- raw payload
- media references

Synthetic data can be recalculated. Raw data is not overwritten.

### 2. Identity resolution before extraction
Do not mix contacts across platforms by name alone.

Strong merge signals:
- same phone number
- same email
- explicit message: “this is my WhatsApp / IG / email”
- Android contact card
- user manual correction

Medium signals:
- same handle
- same display name + profile photo similarity
- same birthday/location/job/social graph
- message continuity across channels

Weak signals:
- same first name
- same city
- similar interests

Weak signals must not auto-merge. Duplicate records are better than one Frankenstein contact.

### 3. Evidence for every claim
Every extracted item needs provenance:
- message/media/raw item ID
- timestamp
- speaker
- quote or media analysis
- confidence
- extraction method
- claim type: explicit / inferred / speculative

No evidence means no confirmed fact.

### 4. Episode-first analysis
Do not shove 100k+ messages into one prompt and ask for “analysis”. Segment first:
- time gaps
- topic shifts
- media bursts
- emotional shifts
- conflict/repair sequences
- date/travel/event clusters

Then extract per episode, consolidate across episodes, and only then synthesize the contact dossier.

## What to Extract

### Identity
- real names, handles, emails, phones
- platform display names
- genuine aliases
- terms of address
- roleplay terms
- joke references

**Rule:** `daddy`, `sir`, `babe`, `baby`, `darling`, `dear`, `miss`, `bb`, `bby` are not aliases by default. They are terms of address or contextual/sexual roleplay terms unless repeatedly used as stable identifiers outside intimate/joke contexts.

### Timeline
Extract relationship milestones, not keyword spam:
- first contact
- first media exchange
- first meeting/date
- physical intimacy
- emotional disclosures
- conflicts and repairs
- jealousy moments
- boundaries set
- travel arrivals/departures
- moving intentions
- health/pet/work/family events
- relationship shifts
- silence gaps and reconnections

Mentioning “BKK” is not an event. “I’ll be in BKK tomorrow for two weeks” is.

### Preferences and Boundaries
Track categories:
- food/drink
- anime/film/music/books
- travel/places/hotels/bars
- date activities
- communication style
- gifts
- sexual preferences and limits
- emotional boundaries
- health/substances/sleep/sport

### Psychological Claims
Use evidence-backed dimensions:
- attachment pattern
- emotional availability
- defense mechanisms
- conflict style
- vulnerability triggers
- love language
- insecurities
- agency/initiative
- desire/intimacy model
- reliability/consistency
- power dynamics with Monsieur
- interaction strategy

Avoid vague horoscope output. “Playful and humorous” alone is useless. Cite patterns and counter-evidence.

### Current State and Open Loops
Maintain a short-lived state:
- temperature: cold / neutral / warm / hot / conflict
- who owes reply
- unanswered questions
- unresolved conflicts
- plans not scheduled
- promises not fulfilled
- opportunity windows
- next best action
- risk notes

### Style Profiles
Learn Monsieur’s style **per contact**, not only globally:
- language used
- grammar/spelling quirks
- message length
- emojis
- teasing style
- sexual directness
- phrase templates
- what worked / failed

## Model Routing

Do not use one model for everything.

- Raw ingestion/dedupe/dates/IDs: Python/SQL/regex, no LLM.
- Embeddings/search: local embeddings and/or quality API embeddings; Qdrant payloads must point back to PG IDs.
- High-volume extraction: cheap/fast structured-output model, episode-level, JSON schema enforced.
- Consolidation/psychology/strategy: stronger reasoning model, used sparingly on episode summaries + claims.
- Reply drafting: orchestrator/current main model with a small Kardex reply pack.
- Multimodal: Whisper for audio; vision model for images/keyframes; OCR for screenshots/documents.

Prefer structured schemas (Pydantic/JSON schema/Outlines-style constraints) over “please output JSON”, because optimism is not a parser.

## Qdrant Sync Pattern

Index derived units, not the whole database indiscriminately:
- raw message chunks
- episode summaries
- claims
- relationship events
- context packs

Each Qdrant payload must include PG references:

```json
{
  "contact_id": 1,
  "raw_item_id": 123,
  "episode_id": 45,
  "claim_id": 88,
  "source": "instagram",
  "timestamp": "2026-05-20T14:02:00Z"
}
```

Qdrant retrieves candidates; PG verifies and provides truth.

## Context Injection

Inject contact context only when useful:
- user asks about a contact
- drafting/replying to that contact
- incoming message from known contact
- before a call/meeting
- daily/weekly briefing
- reminder/action due

Pack sizes:
- Tiny: identity + current state + last exchange + one risk/action
- Reply: recent messages + style + open loops + suggested strategy
- Deep: timeline + psychology + preferences + evidence
- Full: manual request only

## Automation Safety

Auto-reply comes later and must be mode-gated:
- `suggest_only`
- `approval_required`
- `low_risk_auto`
- `disabled`

Never auto-send without explicit policy for romantic escalation, sexual messages, conflict repair, money, health crisis, legal/professional comms, secrets, or credentials.

## Contact Lookup Workflow

When Monsieur asks "who is X?" or "what's the profile for Y?", follow this sequence:

### 1. Verify DB connectivity first
```bash
# Check PG container is running
docker ps | grep hindsight-pg

# Get current IP (changes on container recreate!)
docker inspect hindsight-pg | grep IPAddress

# Test connection
psql -h <IP> -U postgres -d hermes -c "SELECT 1 FROM kardex.contacts LIMIT 1;"
```

If connection fails → report the connectivity issue, do NOT conclude "contact not found."

### 2. Search Kardex contacts
```sql
-- By canonical name
SELECT * FROM kardex.contacts WHERE canonical_name ILIKE '%lcomte63%';

-- By aliases
SELECT * FROM kardex.contacts WHERE 'lcomte63' = ANY(aliases);

-- By handles JSONB
SELECT * FROM kardex.contacts WHERE handles::text ILIKE '%lcomte63%';

-- By Beeper handle (channels table)
SELECT c.*, ch.platform_handle 
FROM kardex.contacts c 
JOIN kardex.channels ch ON c.id = ch.contact_id 
WHERE ch.platform_handle ILIKE '%lcomte63%';
```

### 3. If not in Kardex → search Beeper directly
```bash
# List all Beeper chats, grep for the handle
python3 /root/.hermes/services/kardex/scripts/beeper_sync.py --list | grep -i lcomte63
```

### 4. If not in Beeper → search session history
Use `session_search` with variations:
- Full handle: `lcomte63`
- Without prefix: `comte63`
- Name only: `Lucas comte`
- Platform-specific: `instagram lcomte63`

### 5. If truly not found anywhere
Report honestly:
- DB connectivity status
- Kardex search results (empty)
- Beeper search results (empty)
- Session search results (empty)
- Ask Monsieur: which platform? real name? approximate handle?

**Never conclude "this person doesn't exist" without verifying all layers.** A failed DB connection is not the same as an empty result.

## Current Kardex Files

- Architecture: `/root/.hermes/services/kardex/KARDEX_PIPELINE_ARCHITECTURE.md`
- Canonical model: `/root/.hermes/services/kardex/KARDEX_MODEL.md`
- V2 migration: `/root/.hermes/services/kardex/migrations/002_kardex_v2.sql`
- Implementation plan: `/root/.hermes/services/kardex/IMPLEMENTATION_PLAN_V2.md`

See `references/kardex-v2-architecture.md` for the session-specific architecture notes and schema table list.

For detailed SQL queries, Beeper API patterns, and troubleshooting steps for contact lookups, see `references/contact-lookup-patterns.md`.

## Kardex as Psyche Layer (Lucas = contact_id 0)

The Kardex schema is not only for third-party contacts. **Monsieur (Lucas) is contact_id 0** with `relationship_type = 'self'`. This enables:

- `psychological_claims` → evolving personality profile (Big Five + custom dimensions)
- `preferences` → deep preferences with polarity/strength/confidence
- `journal_entries` → free-form private journal (thoughts, dreams, aspirations)
- `communication_patterns` + `style_profiles` → how Monsieur communicates
- `claims` with `valid_from/to` + `supersedes_claim_id` → temporal evolution

### Journal Entries Table (`kardex.journal_entries`)
Added 2026-06-07. Fields: content, title, mood, energy_level, emotional_tags[], context, related_contacts[], related_topics[], entry_type (thought/dream/reflection/rant/decision/memory/aspiration), privacy_level (intimate/private/shareable), source (direct/telegram_journal/voice/extracted).

### Feeding the Psyche
- **Active**: User says "journal : [pensée]" → insert into journal_entries
- **Passive**: Post-session extraction detects preferences, corrections, emotional state → auto-populate claims/preferences
- **Sync**: `kardex-hindsight-sync.timer` (every 5 min) vectorizes new Kardex entries into Hindsight for semantic recall

### Separation of Concerns
- **USER.md** (1375 chars, injected every turn) = operational identity (timezone, handles, interaction rules)
- **Kardex psyche** (PG, vectorized) = deep knowledge (personality, patterns, aspirations, history)
- USER.md answers "how to interact now". Kardex answers "who Monsieur is deeply".

### Initial Psychological Dimensions (contact_id=0)
- cognitive_style, control_need, perfectionism, autonomy, cost_consciousness, directness, builder_identity
- Each with confidence, stability, trigger_patterns, counter_patterns, strategy_implication

## Current Kardex Deployment (Implementation-Specific)

The Kardex system is deployed on `hindsight-pg` (Docker, schema `kardex`). For current schema, scripts, connection details, and implementation status, see `references/kardex-implementation.md`.

Key scripts:
- **Beeper sync**: `/root/.hermes/services/kardex/scripts/beeper_sync.py`
  - uses paginated `/v1/chats` discovery
  - resolves existing contacts by exact Beeper room/channel first, then strong identity links (phone/email/external identity)
  - same display name/ambiguous handle creates `kardex.contact_merge_candidates`, not an auto-merge
- **Context builder**: `/root/.hermes/services/kardex/scripts/build_context.py`
- **Schema**: `/root/.hermes/services/kardex/schema.sql`
- **Visual navigation pattern**: `references/kardex-visual-navigation.md` — Directus/NocoDB over PostgreSQL; Notion only as curated mirror/export.

- **Identity hardening migration**: `/root/.hermes/services/kardex/migrations/003_identity_resolution_hardening.sql`

## Deep Extraction Taxonomy

For the full relationship extraction taxonomy (identity, social graph, timeline, preferences, psychology, sexual/intimacy model, communication style, open loops, actions, metrics), see `references/kardex-canonical-model.md`.

## Batch Media Retrieval

For extracting and analyzing media from Beeper chats (photos, filtering stickers, SCP, vision analysis), see `references/batch-media-retrieval.md`.
