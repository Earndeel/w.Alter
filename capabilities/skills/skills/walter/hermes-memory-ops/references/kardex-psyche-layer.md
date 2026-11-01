# Kardex as Psyche Layer — Monsieur's Intimate Memory

## Overview

The Kardex schema (`kardex.*` in hindsight-pg) serves dual purpose:
1. Social memory — contacts, relationships, communication history
2. Psyche layer — Monsieur's psychological profile, preferences, journal (added 2026-06-07)

Current live schema check (2026-06-29): `kardex` has 43 tables. Monsieur's Kardex contact row is `contacts.id = 0` (`canonical_name = Lucas`, `relationship_type = self`).

## Key Tables for Psyche

### journal_entries (created 2026-06-07)

Personal journal — raw thoughts, dreams, reflections. Never exposed verbatim.

Fields: content, title, mood, energy_level (1-10), emotional_tags[], context, related_contacts[], related_topics[], entry_type (thought/dream/reflection/rant/decision/memory/aspiration), privacy_level (intimate/private/shareable), entry_date, source, source_ref.

### psychological_claims (7 initial claims)

Dimensions populated: cognitive_style, control_need, perfectionism, autonomy, cost_consciousness, directness, builder_identity.

Each has: dimension, claim, confidence, stability (stable/moderate/volatile), trigger_patterns[], counter_patterns[], strategy_implication.

### preferences (15 initial entries)

Categories: communication (5), tech (5), lifestyle (3), work (2).
Each has: category, preference, polarity (positive/negative), strength, confidence, status.

## USER.md vs Kardex Boundary

USER.md (1375 chars max, injected every turn) = operational identity:
- Timezone, handles, location
- Communication rules
- Operational constraints
- Provider preferences

Kardex (queried by recall, unlimited) = deep knowledge:
- Psychological profile (who he IS)
- Preferences (what he likes/hates deeply)
- Journal (raw thoughts, evolving)
- Patterns detected over time

## Feeding the Psyche

Passive: observe corrections, reactions, choices → update claims confidence.
Active: "journal : [thought]" → insert journal_entries.
Synthesis: weekly cron rereads new entries → updates profile.

## Privacy

- journal_entries privacy_level='intimate' → NEVER returned verbatim
- Only synthesized insights used in context
- psychological_claims → can be referenced ("based on your pattern...")
- preferences → directly usable for decisions
