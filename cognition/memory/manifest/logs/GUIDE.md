# walter-logs — detailed guide

## Purpose
Keep what W.Alter's agents **did**, whatever the runtime (Walter Engine and its sub-agents, Claude Code, Codex; Hermes
and DSH sessions before their retirement): messages, reasoning, tool calls with full arguments, full results,
compaction summaries, model choices. Walter Memory keeps {{owner.address}}'s life; walter-logs keeps the agents' work.

## How to use it
1. `logs_search(query, runtime, event_type, tool, session, since, until)`: words (full text, accent-insensitive) or an
   exact string (path, error message, identifier). Each hit carries a `session#seq` reference.
2. `logs_timeline(session, seq, before, after)`: the sequence around an event, in order.
3. `logs_get(session, seq)`: one event in full, with the linked tool call or result.

## Organisation
| Part | Role |
|---|---|
| PG schema `walter_logs` (`sessions`, `events`) | Append-only journal, one privacy class per event |
| `walter_memory/logs.py` | Writing, secret masking at write |
| `walter-logs-watch` | inotify synchronisation within seconds + hourly catch-up; no timer |

## Interfaces
| Need | MCP | CLI |
|---|---|---|
| Search | `logs_search` | `walter-memory logs search` |
| Timeline | `logs_timeline` | `walter-memory logs timeline` |
| Full event | `logs_get` | `walter-memory logs get` |

## Limits
- Secrets are masked at write; a secret transformed in an unusual way can escape the mask.
- `local_only` events are invisible to cloud clients (`--cloud-safe`).
- Running sessions appear a few seconds late.
- Observability is not memory: tool calls are never copied into `core.events`.
