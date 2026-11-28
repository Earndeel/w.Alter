# Walter Memory — detailed guide

## Purpose
Keep the durable truth of {{owner.address}}'s life and make it usable by every agent: what happened (messages,
e-mails, calendar, conversations with W.Alter, files), what was learned from it, and who the people are. Success = a
correct, sourced answer within a bounded context.

## How to use it
1. **Prepared context**: on the engine, the turn's `<walter-context>` block already holds `memory_context` for the
   message and the cards of the people named. Elsewhere, `memory_context(query)` gives the same block (~2k tokens).
2. **Go deeper**: `memory_search` (knowledge + original evidence, source and date; `evidence_only` for raw history);
   `memory_events` for the exact text of canonical events (filters source, type, thread, date; `order`, `next`
   window); `person_lookup` for a person's full social card; `memory_recall` for synthesised facts; `memory_reflect`
   for an argued synthesis from permitted evidence.
3. **Write**: `memory_retain` records a durable fact once (`note.recorded`). Never a secret, never a transient log.
   Tasks: `task_create` / `task_update` / `tasks_list`.

## Organisation
| Part | Role |
|---|---|
| `core.events` | Canonical append-only history, idempotent, privacy-classed |
| `core.objects` | Registry of raw files (Raw Vault, module `raw-vault`) |
| `core.derived_items`, `core.provenance` | Extracted knowledge (generations g0 and g1), always linked to its evidence; superseded items keep their history |
| `kardex.*` | Social layer: identities, relationships, measures, communication deviations; written only by Walter Memory processors |
| `search.chunks` | Multilingual full-text index + local vectors; rebuildable |
| `processing.*` | Event-driven assimilation state (queue, memoised model decisions) |
| Connectors (`walter-memory-*` timers, bus consumers) | Beeper, Google (Gmail, Calendar), agent sessions (Claude Code, Codex, engine), index, social, extraction, triage |
| `walter_memory.llm` | The only door to models: refuses `local_only` where required, pseudonymises `redacted_cloud`, budgets |
| Gateway `:8890`, library | The only write doors |

The agent logs (`walter_logs`, module `logs`) and the event bus (module `bus`) live in the same repository but are
separate modules.

## Interfaces
| Need | MCP | CLI |
|---|---|---|
| Context for a request | `memory_context` | `walter-memory context` |
| Unified search | `memory_search` | `walter-memory search` |
| Exact events | `memory_events` | `walter-memory events` |
| Person | `person_lookup` | `walter-memory social` |
| Recall / reflect / retain | `memory_recall`, `memory_reflect`, `memory_retain` | `walter-memory agent-memory` (JSON on stdin) |
| Tasks | `tasks_list`, `task_create`, `task_update` | `walter-memory tasks` |
| Health | `walter_health` | `walter-memory health` |

## Privacy and limits
- Classes `cloud_allowed`, `redacted_cloud`, `local_only` can only be tightened; MCP tools expose only what the
  client is allowed. Credentials are always masked.
- Real deletion only through `walter-memory purge` (break-glass, dry run by default).
- A source that is not connected (e.g. waiting for authorisation) proves nothing by its absence in a result.
- Operations and plan: `/walter/cognition/memory/docs/` (PLAN, STRUCTURE, RUNBOOK sections), README of the module.
