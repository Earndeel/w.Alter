---
name: kardex-contact-intelligence
description: Kardex contact intelligence system — multi-source relationship dossiers with raw messages, evidence-backed facts, episodes, psychology, preferences, actions, and style-aware reply strategy.
version: 1.1.0
author: W.Alter
metadata:
  hermes:
    tags: [kardex, contacts, intelligence, beeper, memory, relationships, postgres, qdrant]
---

# Kardex — Contact Intelligence System

Kardex is W.Alter’s contact intelligence layer: a living, multi-source dossier for each person Monsieur communicates with. It is not a flat address book and not an LLM vibe-summary. It stores raw communications, analyzes them into evidence-backed facts, and maintains current relationship state, preferences, events, open loops, and reply strategy.

## Current Implementation Notes

- PostgreSQL source of truth: `hindsight-pg`, schema `kardex`.
- Existing core tables: `contacts`, `channels`, `messages`, `media`, `events`, `actions`, `sync_state`.
- Scripts live under: `/root/.hermes/services/kardex/scripts/`.
- Canonical model document: `/root/.hermes/services/kardex/KARDEX_MODEL.md`.
- Plan file: `/root/.hermes/plans/2026-05-20-kardex.md`.
- Beeper is the first source; future sources include email and Android smartphone extraction.
- Qdrant should be used only as derived semantic index (`kardex_ctx`), not source of truth.

## Fundamental Rule: Evidence First

Every synthetic fact must include provenance:

- source (`beeper`, `gmail`, `sms`, `whatsapp`, `android_call`, manual)
- source message/media ID
- timestamp
- speaker
- quote or media analysis excerpt
- confidence
- claim type: `explicit`, `inferred`, or `speculative`

No evidence → no confirmed fact. Store it as a hypothesis at most. Quite a revolutionary concept: knowing why we believe things.

## Correct Extraction Pipeline

Do **not** do:

```text
8,000 raw messages → “analyze this relationship” → vague soup
```

Do:

```text
Raw ingestion
  → identity resolution
  → episode segmentation
  → episode summaries
  → atomic fact extraction
  → evidence linking
  → deduplication
  → contradiction / evolution detection
  → timeline synthesis
  → psychological synthesis
  → current state
  → next-best-action
```

## Identity Rules

Separate identity concepts strictly:

| Type | Examples | Storage |
|---|---|---|
| Real name | Annie | `real_names` / `canonical_name` |
| Platform handle | `cl_ld8228` | `handles.instagram` |
| Stable alias | CL, Annie | `aliases` |
| Term of address | babe, darling, miss, lady | `terms_of_address` |
| Sexual/roleplay term | daddy, sir, master | `roleplay_terms`, never aliases by default |
| Joke identity | “56 years old Indian man” | `joke_references`, never aliases |

**Pitfall learned:** Do not regex every affectionate/sexual term into `aliases`. “daddy” is not an alias.

## Relationship Data to Extract

Use the full model in `references/kardex-canonical-model.md`. Key classes:

- identity and cross-platform handles
- social graph (family, exes, friends, pets, rivals, ambiguous people)
- locations, travel windows, hotels, frequent places
- relationship timeline and milestones
- conversation episodes
- preferences (food, culture, travel, dates, gifts, substances)
- sexual preferences and boundaries (sensitive, evidence-backed)
- psychological claims with evidence and counter-evidence
- dynamic with Monsieur (initiative, push/pull, jealousy, repair)
- communication style and response triggers
- Monsieur’s per-contact style profile
- open loops and opportunity windows
- actions / reminders / “do nothing” recommendations
- emotional memory (sadness, grief, pride, vulnerability)
- recommendations and shared media backlog
- health/body notes, work/ambitions, boundaries/risks
- contradictions and evolution over time
- metrics: reply latency, initiation ratio, warmth, conflict, plan follow-through

## Model Selection

- Prefer cheap/free long-context models for extraction, but verify availability before relying on them.
- Free OpenRouter models can be rate-limited; do not hard-code them as always available.
- For large relationship extraction, use episode-level summarization to reduce cost and improve quality.
- The orchestrator/current model may be used for reasoning/design, but scripts need an explicit provider/model.

## Media Analysis Pipeline

| Type | Model | Provider | Notes |
|------|-------|----------|-------|
| Images | vision-capable model | OpenRouter or configured provider | Use JSON file payloads; avoid shell arg length issues |
| Audio/Voice | Whisper large-v3-turbo | Groq | ~0.9s per clip when available |
| Video | key frames + audio transcription | vision + Whisper | Extract frames with ffmpeg, analyze frames + audio |

**User correction:** CL/Annie may be used as text-only test data, but do **not** run multimodal media analysis until explicit go.

## Beeper Source Notes

- Use the `beeper-messages` skill for API details and sortKey pagination.
- Start with a single contact test before `--all`.
- Beeper full history may require hundreds of pages; cap defensively and deduplicate by source message ID.
- View-once Instagram media is not useful after the fact: Beeper often stores placeholder GIFs, not the actual content.

## Safety / Reply Automation

Future Kardex may suggest or send replies in Monsieur’s style. Until explicitly authorized:

- Never auto-send messages.
- Generate drafts and strategy only.
- Reply automation must use current state + contact dossier + Monsieur’s per-contact style profile.
- Internal/private APIs for social/dating platforms carry ban risk; prefer Android/app-side extraction later.

## Required DB Evolution

Current schema is a foundation, not enough. Add normalized tables before serious extraction:

- `identities`, `identity_mentions`
- `evidence`, `claims`, `claim_evidence`
- `conversation_episodes`
- `relationship_events`
- `preferences`, `boundaries`
- `psychological_claims`
- `communication_patterns`
- `relationship_metrics`
- `open_loops`
- `action_recommendations`
- `style_profiles`
- `recommendations`
- `health_notes`
- `social_graph`
- `corrections`
- `extraction_runs`

## Quality Checklist

Before presenting Kardex output:

- [ ] Are aliases clean and not roleplay/generic terms?
- [ ] Are events meaningful, deduplicated, and episode-level?
- [ ] Does each claim have evidence IDs or quoted evidence?
- [ ] Are facts separated from interpretations and strategies?
- [ ] Are current-state recommendations based on recent messages?
- [ ] Are sensitive sexual/health claims stored carefully and not overgeneralized?
- [ ] Did user corrections become persistent extraction rules?

## References

- `references/kardex-canonical-model.md` — full taxonomy of what to extract over years of relationships.
- `references/batch-media-retrieval.md` — Beeper media retrieval details from earlier work.
