# Walter Router

The Walter module that chooses, for every task, the best model Walter can actually run — and the cheapest way to
run it. It researches leaderboards, prices and plans on the web, understands and ranks them, keeps an active model
library, proposes changes to the owner (never switches by itself), and serves the choice to every other module.

A module in its own right: the software here carries no owner data; his declarations, plans, accesses and history
live in his Walter instance (`walter instance`). Other modules only use the `walter-router` command (and walter-llm
for text calls). Data: schema `models` in PostgreSQL. Design: `docs/DESIGN.md` · data reference: `docs/DATA.md` ·
text tiers: `docs/TIERS.md` · dated decisions: `docs/HISTORY.md`.

## Documentation et contrats d’usage

Commencer par [docs/README.md](docs/README.md). Les guides couvrent l’usage optimal, le branchement à un harness,
l’exécution et ses permissions, l’exploitation et la maintenance documentaire. La référence générée comprend tous
les paramètres, commandes, champs SQL, tâches/poids, constantes et clés de configuration livrée.

```bash
walter-router schema                 # schémas publics versionnés, sans appel de modèle
walter-router docs --check           # vérifie code + métadonnées PG, sans écriture
walter-router docs --check --offline # vérifie contre le dernier schéma public enregistré
walter-router docs --write           # régénère la référence, sans modifier les modèles ou données privées
walter-router brief --json           # note courte versionnée pour walter-context et les harnesses
```

[docs/ORCHESTRATOR.md](docs/ORCHESTRATOR.md) décrit la note, sa publication et sa conservation par tour.
Le composeur général de walter-context reste distinct de cette source de capacité. Le contrat des permissions
et les limites actuelles des outils natifs sont explicités dans [docs/EXECUTION.md](docs/EXECUTION.md).

## Layout

| Folder | Part | What it holds |
|---|---|---|
| `research/` | **Research** — fetches, periodically or on demand, by API or straight from the page | `categories/` (text, image, video, audio, memory, decision, prices, hosts, plans: each runnable alone) · `benchmarks/` one reader per site · `prices/` provider catalogues and the hosts behind OpenRouter · `agent/` the research agent of the cycle · `web.py` shared web access · `sources.py` registry, partial reads merged into the last snapshot · `run.py` the `research` command |
| `analysis/` | **Analysis** — understands the data and keeps the active library | `parse`, `ingest` (snapshots → benchmarks / offers with identities) · `identity`, `aliases`, `media`, `catalog` · `knowledge` (owner's declarations) · `scoring`, `select`, `pareto`, `tiers`, `decision_pareto`, `postes`, `dossier` · `changes`, `alerts` (detection, verdicts), `telegram` (messages, buttons, sending), `recommend` · `refresh` (the cycle) |
| `plan/` | **Plan** — the owner's subscriptions | `declared` (his plans: one writer) · `subscriptions` (meters, real usage, cost price of a token) · `quota_watch` (service) · `mail` (subscription mails) · `watch` (web research per plan) · `news` (new benefits or changes → notices) |
| `interface/` | **Interface** — the library page | `library` (rows, publishing) · `page` (HTML) · `translate` (English) · `site/` (Cloudflare Pages functions) |
| `serve/` | What Walter calls at run time | `api` (schémas) · `brief` (note) · `run` / `text_agent` (exécution native) · `choose` (pick) · `routes` (execution routes, free-text entry) · `intent` (decision model) · `execution` (provider order, hosts, probes, reliability) · `media_exec` (image / video / music / voice) · `oneshot` (economic-tier answers) · `hermes_sync` |
| `guardian/` | **Guardian** — the module's own maintenance (2026-10-26) | `checks` (detection, no model) · `run` (incidents, decisions, Telegram) · `repair` (the L2 agent on a copy of the module, deterministic gates, landing) · `prompt.md` · README |
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
   page) among the models Walter can run. A hard constraint (`--require unrestricted | open_weights | video_input`) keeps
   only the models — and the routes — that meet it (video_input: the offers that declare video input). Text tiers L1 / L2 / L3 come from the owner's Pareto method (`docs/TIERS.md`);
   decision models are compared on three axes (Decision Index, time, cost per task).
3. **The owner decides** — his pins and roles (`config/knowledge.json`, `prefer`) always win. A model that beats an
   active one on the task's global score, a new #1, a nerf, a board down, a plan change or a plan news becomes one
   Telegram message with buttons; nothing switches without his button (`verdict`).
4. **Serve** — routes in the owner's order: a subscription first at its cost price while its weekly quota is under
   90 %, Kie when reliable and not much dearer, OpenRouter last on the cheapest usable host it is told to use (never
   below the model's native precision, ≥ 95 % uptime over 24 h; flex tier only for background postes). Text execution stays on the selected model: only its ordered providers are tried, with an explicit
   `user_notice` on failover. Exhaustion is an error, never an implicit subscription/model substitution.
   A media model falls back to its next provider (another model only when declared). Providers: OpenRouter, Kie, Codex, Arnict.

## Who uses it

| Consumer | How |
|---|---|
| Hermes | plugin `walter-router` (tools `walter_route`, `walter_run`, `walter_decide`, `walter_plans`, plus `walter_verdict`, `walter_feedback` for the Telegram buttons and the owner's verdicts); the brief as a system-prompt section; `sync-hermes` writes its auxiliary jobs, cron postes and `provider_routing.models.<id>.order` |
| Modules (walter-memory, Hindsight, voice, Kardex…) | walter-llm with `model` = a router task; `pick` for service postes (STT, rerank, embeddings) |
| walter-memory triage | `decision-chain` (d1-ultra, then Mercury Decide, then Clef) |
| Claude Code, Codex, DSH | the `walter` MCP: the same four tools under the same names, the same runs; the brief in the MCP server instructions (Claude Code) and in their W.Alter profile (Codex, DSH). Their own model stays theirs |
| walter-context (planned) | the decision model (`classify` / `ask`) to set the agentic level of a turn |
| walter-core | `walter-router health` in `walter_health` |

## Operating it

The 48 h cycle (`walter-router-refresh.timer`, `bin/walter-router-cycle`): research + analysis → research agent on the
economic tier (names checked on the web) → plan research (meters, mails, web, news, cost price) → final analysis and
Telegram → Hermes follows, the page is republished → the guardian follows up what is still broken. Services:
`walter-router-quota` (meters after each agent turn), `walter-router-control` (page trigger), `walter-llm`,
`walter-router-guardian.timer` (every 6 h, and after each cycle).

The guardian ([guardian/README.md](guardian/README.md)) keeps the module working without the owner: it detects stale
or failing sources, a failed cycle, providers down, failing tests and an out-of-date generated reference; probes and
re-reads first; waits out outside outages; has the L2 text tier repair what is ours on a copy of the module; lands a
patch only through deterministic gates and only on files nobody is editing; regenerates the reference itself.
Telegram only for a repair that landed, a decision only the owner can take, or an outage lasting 48 h.

```
walter-router health | status | review | alerts [--all]
walter-router research [text|image|video|audio|memory|decision|prices|hosts|plans|all] [--analyse] | --list | --source KIND
walter-router refresh [--skip-collect] [--no-notify]          # recompute (the cycle does it)
walter-router pick TASK [--level L1|L2|L3] [--role R] [--require unrestricted|open_weights|video_input] [--agent]
walter-router route "<request>" [--task T] [--level L] [--context "<what the conversation was about>"] [--agent]
walter-router route "<request>" --model M [--provider P]  # a model named by the owner: exactly that one, or why not
walter-router run < spec.json        # do the job: native text/tool loop | media = generation
walter-router ask "<question>" --option a="…" --option b="…" [--context …]   # the decision model, any choice
walter-router classify "<request>" [--context …] | decide TASK "<request>" | dossier TASK | tasks | library
walter-router generate "<request>" [--task …] [--role …]      # costs money: on request only
walter-router prefer TASK [--pin MODEL[/VARIANT]] … | verdict ALERT adopted|dismissed | feedback MODEL RATING
walter-router plans list | set ID [--vendor --plan --price --models --since --until --note] | retire ID
walter-router subscriptions [refresh | calibrate anthropic-pro PERCENT]
walter-router brief [--write]        # what an agent must know to use the router: tools, levels, specialities,
                                     # generation, analysis, constraints — never a model or provider name
walter-router sync-hermes [--apply] | publish-library | declare | migrate | probe | decision-chain
walter-router alias-add | alias-remove | alias-list | postes | log-exec | notify-failure | instance-env
walter-router-guardian check [--no-tests] | run [--no-agent] [--no-tests] [--no-notify] [--dry-run] | status
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

## Text execution and provider failover (2026-10-23)

`walter-router run` executes text natively: its tool loop sends each model call to the module’s own
`walter-llm call` transport (JSON on stdin). That transport executes exactly one provider/model,
with no hidden retry or model fallback; provider keys remain inside the gateway process. No Hermes
runtime is started by text runs. Terminal/code and text-file tools are native; web/skills/memory
commands can be invoked through the terminal when that toolset is enabled. A vision-only toolset
without an image input returns an explicit unsupported-input error.

On provider failure the router tries the next provider of the **same** model. It keeps conversation and
completed tool results, so changing provider does not restart the task. Each physical model attempt
is recorded in `models.exec_log`, and the result includes response ids, actual provider, tool trace and
bounded execution status. A different provider’s native spelling of the model is kept in `routed.model`;
`routed.model_id` remains the router’s canonical model. A model explicitly tied to a provider continues
to respect that provider restriction.

`notices` records every switch, with source, destination and reason. When `user_notification_required`
is true the caller **must tell the user `user_notice`**, including on failure. `output` remains the task’s
answer so structured-output requests remain usable. If every provider of a model fails, the run moves to the
next model the owner declared as its fallback (`knowledge.json`: `unrestricted_favourites` for an unrestricted request,
the tier's `fallback`), with a `model_fallback` notice; a model that was not declared is never substituted. If the whole
chain fails, `ok` is false. `routed.executed_model_id` names the model that answered. The budget covers all providers and tools together.

## Route d’abonnement Claude

La route `claude-pro` est exécutée dans la passerelle du Router, avec les messages, outils et paramètres du consommateur. Le transport natif ne conserve que l’attribution technique du fournisseur ; sa boucle d’agent et son contexte ne sont pas délégués. Configuration, renouvellement, quotas réels, streaming et limites : [docs/CLAUDE-SUBSCRIPTION.md](docs/CLAUDE-SUBSCRIPTION.md).

## Route d’abonnement Google AI Pro

La route `antigravity` sert les modèles de l’abonnement Google AI Pro (Gemini 3.8 Flash, Claude Sonnet/Opus 4.6,
GPT-OSS 120B) par la CLI officielle Antigravity, texte seul, tous ses outils refusés, rien de conservé après l’appel :
[raisons, transport, quota et vérification](docs/ANTIGRAVITY-SUBSCRIPTION.md).

La collecte Arena dispose d’un repli public borné par le navigateur partagé, avec contrôle de l’identité
des classements : [transport, limites et vérification](docs/ARENA.md).
