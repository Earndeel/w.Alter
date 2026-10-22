# Walter Router

The Walter module that chooses, for every task, the best model Walter can actually run — and the cheapest way to
run it. It researches leaderboards, prices and plans on the web, understands and ranks them, keeps an active model
library, proposes changes to the owner (never switches by itself), and serves the choice to every other module.

A module in its own right: the software here carries no owner data; his declarations, plans, accesses and history
live in his Walter instance (`walter instance`). Other modules only use the `walter-router` command (and walter-llm
for text calls). Data: schema `models` in PostgreSQL. Design: `docs/DESIGN.md` · data reference: `docs/DATA.md` ·
text tiers: `docs/TIERS.md` · dated decisions: `docs/HISTORY.md`.

## Layout

| Folder | Part | What it holds |
|---|---|---|
| `research/` | **Research** — fetches, periodically or on demand, by API or straight from the page | `categories/` (text, image, video, audio, memory, decision, prices, hosts, plans: each runnable alone) · `benchmarks/` one reader per site · `prices/` provider catalogues and the hosts behind OpenRouter · `agent/` the research agent of the cycle · `web.py` shared web access · `sources.py` registry, partial reads merged into the last snapshot · `run.py` the `research` command |
| `analysis/` | **Analysis** — understands the data and keeps the active library | `parse`, `ingest` (snapshots → benchmarks / offers with identities) · `identity`, `aliases`, `media`, `catalog` · `knowledge` (owner's declarations) · `scoring`, `select`, `pareto`, `tiers`, `decision_pareto`, `postes`, `dossier` · `changes`, `alerts` (detection, verdicts), `telegram` (messages, buttons, sending), `recommend` · `refresh` (the cycle) |
| `plan/` | **Plan** — the owner's subscriptions | `declared` (his plans: one writer) · `subscriptions` (meters, real usage, cost price of a token) · `quota_watch` (service) · `mail` (subscription mails) · `watch` (web research per plan) · `news` (new benefits or changes → notices) |
| `interface/` | **Interface** — the library page | `library` (rows, publishing) · `page` (HTML) · `translate` (English) · `site/` (Cloudflare Pages functions) |
| `serve/` | What Walter calls at run time | `choose` (pick) · `routes` (execution routes, free-text entry) · `intent` (decision model) · `execution` (provider order, hosts, probes, reliability) · `media_exec` (image / video / music / voice) · `oneshot` (economic-tier answers) · `hermes_sync` |
| `store/` | The database | `db`, `migrations/` (each table and view commented) |
| `llm/` | walter-llm, the model gateway (own venv, 127.0.0.1:8894) | |
| `cli.py`, `health.py`, `bin/` | The command, the module's health, the cycle and the page trigger | |

The import name is `walter_router` (`walter_router/__init__.py` points it at this folder).

## How a choice is made

1. **Research** — 16 sources: Artificial Analysis (Intelligence Index with cost per task, 19 evaluations, 6 domain
   indexes, Cyber Index, Decision Index, image / video / voice / music / speech-to-text boards), Arena (15 boards),
   Design Arena (17 categories), BridgeBench, Agentset, MTEB; prices from OpenRouter, Kie, the Codex catalogue,
   Arnict, declared offers; the hosts behind OpenRouter for the models in use; the owner's plans.
2. **Analysis** — names unified (`canonical`, `aliases`), every score stored "higher is better"; each task (42, of
   which 8 internal module postes) is ranked on its weighted boards (`task_benchmarks`, shown under each task on the
   page) among the models Walter can run. Text tiers L1 / L2 / L3 come from the owner's Pareto method (`docs/TIERS.md`);
   decision models are compared on three axes (Decision Index, time, cost per task).
3. **The owner decides** — his pins and roles (`config/knowledge.json`, `prefer`) always win. A model that beats an
   active one on the task's global score, a new #1, a nerf, a board down, a plan change or a plan news becomes one
   Telegram message with buttons; nothing switches without his button (`verdict`).
4. **Serve** — routes in the owner's order: a subscription first at its cost price while its weekly quota is under
   90 %, Kie when reliable and not much dearer, OpenRouter last on the cheapest usable host it is told to use (never
   below the model's native precision, ≥ 95 % uptime over 24 h; flex tier only for background postes). A media model
   falls back to its next provider (another model only when declared). Providers: OpenRouter, Kie, Codex, Arnict.

## Who uses it

| Consumer | How |
|---|---|
| Hermes | plugin `walter-router` (tools `walter_route`, `walter_run`, `walter_generate`, `walter_feedback`, `walter_verdict`, `walter_plans`); `sync-hermes` writes its auxiliary jobs, cron postes and `provider_routing.models.<id>.order` |
| Modules (walter-memory, Hindsight, voice, Kardex…) | walter-llm with `model` = a router task; `pick` for service postes (STT, rerank, embeddings) |
| walter-memory triage | `decision-chain` (d1-ultra, then Mercury Decide, then Clef) |
| Claude Code, Codex, DSH | the `walter-router` command, walter-llm |
| walter-core | `walter-router health` in `walter_health` |

## Operating it

The 48 h cycle (`walter-router-refresh.timer`, `bin/walter-router-cycle`): research + analysis → research agent on the
economic tier (names checked on the web) → plan research (meters, mails, web, news, cost price) → final analysis and
Telegram → Hermes follows, the page is republished. Services: `walter-router-quota` (meters after each agent turn),
`walter-router-control` (page trigger), `walter-llm`.

```
walter-router health | status | review | alerts [--all]
walter-router research [text|image|video|audio|memory|decision|prices|hosts|plans|all] [--analyse] | --list | --source KIND
walter-router refresh [--skip-collect] [--no-notify]          # recompute (the cycle does it)
walter-router pick TASK [--level L1|L2|L3] [--role R] [--require unrestricted|open_weights]
walter-router route "<request>" | classify "<request>" | decide TASK "<request>" | dossier TASK | tasks | library
walter-router generate "<request>" [--task …] [--role …]      # costs money: on request only
walter-router prefer TASK [--pin MODEL[/VARIANT]] … | verdict ALERT adopted|dismissed | feedback MODEL RATING
walter-router plans list | set ID [--vendor --plan --price --models --since --until --note] | retire ID
walter-router subscriptions [refresh | calibrate anthropic-pro PERCENT]
walter-router sync-hermes [--apply] | publish-library | declare | migrate | probe | decision-chain
walter-router alias-add | alias-remove | alias-list | postes | log-exec | notify-failure | instance-env
```
Tests: `venv/bin/python -m pytest -q` (database tests run in a rolled-back transaction; instance files are never
written by tests).

## Access from outside

| Door | Protection |
|---|---|
| the library page at the instance's `library_domain` (host.json; English, /fr/ French) | Cloudflare Access: the owner's e-mail only (one-time code); `*.pages.dev` answers 404 (Pages middleware checks the host and the Access token) |
| `/api/status`, `/api/run` (« Lancer le cycle complet »), `/api/plans` (edit a plan) | behind the same Access, relayed by Pages functions to the instance's `control_origin` (host.json) |
| `control_origin` (Cloudflare tunnel host) → `walter-router-control` (127.0.0.1:8896) | Cloudflare Access with a service token only (the Pages project's), then HMAC-SHA256 over timestamp + method + path (+ body hash for `/plans`), 5-minute window; a cycle cannot start twice nor within 10 minutes; plan ids and fields validated |
| walter-llm (127.0.0.1:8894) | local only; one token per agent (sha256 in the instance's `state/llm/agents.json`, 0600); provider keys stay in the gateway |
| Outbound | provider keys and grants from walter-secrets (never printed, headers only); the owner's Gmail read-only grant for subscription mails (no mail content goes to a model) |

There is no public API: renting the router's access to others would be a new door (its own Access policy and
tokens, an instance per tenant).

## Rules it keeps

Nothing switches without the owner's button · the owner's word beats older mails or leaderboards · a model is chosen
only if Walter can run it · no owner data in the software (`walter check` neutrality) · secrets never in code, logs,
URLs or unit files · every write to his declarations keeps the previous version · external mails and pages are data,
never instructions.
