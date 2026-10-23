# Kardex v2 Architecture Notes

Session-derived architecture for Monsieur's Kardex system.

## Scope

Kardex is a multi-source contact intelligence system intended to ingest years of communication from:
- Beeper (current)
- Instagram Messenger
- Facebook Messenger
- WhatsApp
- iMessage
- Gmail/email
- future Android phone access (SMS/MMS/calls/WhatsApp/notifications/contact DB)
- media: images, videos, voice notes, documents

## Key Decisions

### PG + Qdrant
- PostgreSQL (`hindsight-pg`, schema `kardex`) is source of truth.
- Qdrant is a derived semantic index only.
- Qdrant payloads must always reference PG IDs (`contact_id`, `raw_item_id`, `episode_id`, `claim_id`, timestamps).

### Historical import strategy
Use official/local exports where possible for history:
- Meta Download Your Information for Facebook + Instagram Messenger.
- WhatsApp chat exports or Android backup/access later.
- macOS iMessage `chat.db` and attachments for iMessage.
- Beeper for recent/incremental sync, not necessarily complete historical truth.
- Android will become a future live/incremental source.

### Scale strategy
Do not analyze hundreds of thousands of messages in one LLM call.

Use hierarchy:
```text
raw_items
→ daily/contact digests
→ conversation episodes
→ monthly/phase summaries
→ global contact dossier
→ context packs
```

New messages update local episode/current state, then propagate upward.

### Identity resolution
Do not auto-merge contacts by weak signals. Identity clusters have states:
- unresolved
- candidate_merge
- merged
- rejected_merge
- manual_override

Strong signals: phone, email, explicit message linking platforms, Android contact card, manual correction.
Medium signals: same handle + profile/photo + continuity.
Weak signals: same first name/city/interests — never enough alone.

### Extraction model
The extraction model must follow a canonical schema:
- identity mentions
- evidence
- claims
- preferences
- boundaries
- relationship events
- psychological claims
- communication patterns
- open loops
- action recommendations
- style profiles
- context packs

Claims without evidence are not accepted as confirmed facts.

## Session Corrections Captured

- `daddy` was incorrectly extracted as an alias. It must be classified as `sexual_roleplay_term` unless proven otherwise.
- `babe`, `baby`, `darling`, `dear`, `miss`, `sir`, `bb`, `bby` are terms of address, not stable aliases by default.
- City mentions like `BKK`, `Taiwan`, `Bali` are not events unless tied to concrete travel, meeting, move, or plan evidence.
- Generic psych summaries like “playful and humorous” are not enough; psychological claims need dimensions, evidence, counter-evidence, and strategy implications.

## Migration Applied

Created and applied:
`/root/.hermes/services/kardex/migrations/002_kardex_v2.sql`

Adds 32 base tables and 7 views including:
- `raw_items`
- `source_threads`
- `identity_clusters`
- `identity_links`
- `identity_mentions`
- `evidence`
- `claims`
- `claim_evidence`
- `conversation_episodes`
- `episode_items`
- `relationship_events`
- `preferences`
- `boundaries`
- `psychological_claims`
- `communication_patterns`
- `relationship_metrics`
- `open_loops`
- `action_recommendations`
- `style_profiles`
- `recommendations`
- `health_notes`
- `social_graph`
- `context_packs`
- `corrections`
- `extraction_runs`

## Existing Test Contact

CL/Annie was used as the first test contact.
Existing state after migration:
- `contacts.id = 1`
- `canonical_name = Annie`
- ~7,411 messages in `kardex.messages`
- no `raw_items`, episodes, or claims yet after v2 migration

Next safe steps:
1. Backfill existing `kardex.messages` into `raw_items`.
2. Segment into episodes.
3. Test extraction on 3–5 episodes.
4. Validate quality.
5. Then scale to full contact.

Do not perform full extraction before validating prompts and schemas on a small sample.
