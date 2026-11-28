# Walter Router

**Role.** Chooses, for each task, the model and provider that fit (benchmarks, prices, {{owner.address}}'s
subscriptions and preferences) and runs it when asked. The calling agent stays the orchestrator: it defines the work
and the permitted data, and checks the result. No W.Alter module hardcodes a model name: modules ask for a "poste".

**Organisation.** `research/` and `analysis/` (leaderboards and prices → PostgreSQL schema `models`), `plan/`
(subscriptions at real token cost), `serve/` (choice, execution, decisions, this usage note), `interface/` (model
library page, Telegram proposals), the gateway `llm/` (module `llm`), and a guardian that maintains the module.

**Live state** (never in this text): `walter_route(task)` for the current choice and prices, `walter_plans` for the
subscriptions, `module_index("router")` for the task list, `walter_health` for the router's health.
