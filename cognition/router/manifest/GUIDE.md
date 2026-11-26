# Walter Router — detailed guide

## Purpose
Choose, for each task, the model and provider that fit ({{owner.address}}'s subscriptions, benchmarks, prices,
preferences) and run it when asked. The agent remains the orchestrator: it defines the work and the permitted data,
and checks the result. Its own model does not change when it calls the router. No W.Alter module writes a model name
in its code: it asks the router for a poste.

## How to use it
| Tool | Use |
|---|---|
| `walter_run` | Run a text sub-task (a sub-agent with tools) or a media generation asked by {{owner.address}} |
| `walter_route` | Examine a choice, its routes and prices without running anything |
| `walter_decide` | A short or repeated choice among named options |
| `audio_transcribe` | Transcribe audio files on the server (voice notes) through the `stt` poste |
| `walter_plans` | Read the subscriptions; record a change {{owner.address}} announces |
| `walter_web` | Talk to a chat web service enabled by {{owner.address}}: message, attached files, optional model; verbatim answer, produced files as paths |

The index (`module_index("router")`) lists the available tasks (key, label, interface). Full guide:
`/walter/cognition/router/docs/USAGE.md`; documentation map: `/walter/cognition/router/docs/README.md`;
data model: `/walter/cognition/router/docs/DATA.md`.

## Organisation
| Part | Role |
|---|---|
| `research/`, `analysis/` | Leaderboards (Artificial Analysis, Arena, Design Arena, BridgeBench, MTEB…) and provider prices → PostgreSQL schema `models` |
| `plan/` | The owner's subscriptions at real token cost |
| `serve/` | Choice per task, execution (`run`, media), decisions, the usage note (`walter-router brief`) |
| `interface/` | Public model library page, Telegram proposals with buttons |
| `llm/` (walter-llm, :8894) | OpenAI-compatible gateway for modules and runtimes: `model` = a router poste (module `llm`) |
| `walter-router-refresh.timer` | 48 h cycle; proposals with buttons, never an automatic switch |
| `guardian/` | Autonomous maintenance of the module after each cycle: detect, repair what is internal on a copy, deterministic checks before applying; Telegram only when useful |

## Interfaces
| Need | MCP | CLI |
|---|---|---|
| Run / examine / decide | `walter_run`, `walter_route`, `walter_decide` | `walter-router run|route|decide` |
| Subscriptions | `walter_plans` | `walter-router plans` |
| Chat web service | `walter_web` | `walter-router web` |
| Tasks | `module_index("router")` | `walter-router tasks` |
| Health | `walter_health` | `walter-router health` |
| Maintenance | — | `walter-router-guardian status` |

## Rules and limits
- If {{owner.address}} names a model, pass it (`model`, `provider`); no substitute.
- Paid media generation only at their request.
- Never a secret or `local_only` data to a cloud model.
- Favourites and postes change only on {{owner.address}}'s decision (proposals, never automatic switches).
