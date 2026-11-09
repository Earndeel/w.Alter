# Kardex as Psyche Layer — Implementation Notes (2026-06-07)

## Lucas = contact_id 0

Lucas (Monsieur) is registered as contact_id=0 in `kardex.contacts` with:
- canonical_name: 'Lucas'
- aliases: ['Monsieur', 'boss', 'patron', 'earndeel']
- relationship_type: 'self'
- location_current: 'Bangkok, Thailand (UTC+7)'
- occupation: 'entrepreneur tech / AI'

## journal_entries Table Schema

```sql
CREATE TABLE kardex.journal_entries (
  id BIGSERIAL PRIMARY KEY,
  contact_id INTEGER NOT NULL DEFAULT 0 REFERENCES kardex.contacts(id),
  content TEXT NOT NULL,
  title TEXT,
  mood TEXT,                           -- serene, anxious, excited, frustrated, melancholic, neutral
  energy_level SMALLINT CHECK (energy_level BETWEEN 1 AND 10),
  emotional_tags TEXT[] DEFAULT '{}',
  context TEXT,                        -- 'late night bangkok', 'after meeting'
  related_contacts INTEGER[],
  related_topics TEXT[] DEFAULT '{}',  -- career, relationship, health, money, identity, creativity
  entry_type TEXT DEFAULT 'thought',   -- thought, dream, reflection, rant, decision, memory, aspiration
  privacy_level TEXT DEFAULT 'intimate', -- intimate, private, shareable
  entry_date DATE DEFAULT CURRENT_DATE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  source TEXT DEFAULT 'direct',        -- direct, telegram_journal, voice, extracted
  source_ref TEXT
);
```

Indexes: contact_id, entry_date DESC, mood, entry_type, GIN on related_topics and emotional_tags.

## Initial Psychological Claims (contact_id=0)

| Dimension | Confidence | Stability |
|---|---|---|
| cognitive_style (architecte-systèmes) | 0.9 | stable |
| control_need (besoin élevé) | 0.95 | stable |
| perfectionism (technique) | 0.85 | stable |
| autonomy (indépendance forte) | 0.9 | stable |
| cost_consciousness (maximise free) | 0.9 | stable |
| directness (ultra-direct, déteste fluff) | 0.95 | stable |
| builder_identity (se définit par ses créations) | 0.85 | moderate |

## Initial Preferences (contact_id=0, 15 entries)

Categories: communication (5), tech (5), lifestyle (3), work (2).
Key negatives (polarity=negative):
- Sur-explications non sollicitées
- Formules de politesse creuses
- Modifications silencieuses de ses processus
- Substitution silencieuse de modèle LLM

## How Kardex is fed and read (current, 2026-11-09)

Kardex is the `kardex` schema of Walter Memory (same PostgreSQL database), fed **only** by walter-memory processors
from `core.events` (timer `walter-memory-social`, bus consumers). Read it through `person_lookup` / `memory_context`
(MCP) or `walter-memory social person "Nom"`; never write it from a script or an agent.

History: until 2026-10-19 a `kardex-hindsight-sync` timer pushed Kardex rows to the Hindsight API (cursor table
`kardex.hindsight_sync_state`). Hindsight was retired on 2026-10-19 and that table dropped on 2026-11-09 (Memory
cleanup phase 1); neither exists any more.

## USER.md vs Kardex — Division of Responsibility

| USER.md (1375 chars, every turn) | Kardex (PG, recalled semantically) |
|---|---|
| Timezone, handles | Personality profile |
| Interaction rules (vouvoiement, format) | Dreams, aspirations |
| Operational preferences (vault, no kill) | Behavioral patterns |
| Current provider/model notes | Evolution over time |
| Security rules (CF = approval) | Deep preferences with evidence |

Rule: if it's needed EVERY turn regardless of topic → USER.md. If it's contextual → Kardex.
