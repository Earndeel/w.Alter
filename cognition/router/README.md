# Walter Router

Model catalogue + per-task model choice, a Walter module in its own right (software here, the owner's data in his
instance: `walter instance`). Schema `models` in PostgreSQL (`docs/DATA.md`). **End-to-end design: `docs/DESIGN.md`**.
Text tiers method: `docs/TIERS.md`. Other modules only use the `walter-router` command (and walter-llm for text calls).

## Layout (2026-10-21, decided by the owner)
| Folder | Part | Content |
|---|---|---|
| `research/` | **Research** — goes and fetches, periodically, by API or straight from the page; **by category** (`categories/`: text, image, video, audio, memory, decision, prices, hosts, plans — `walter-router research image [--analyse]`) | `benchmarks/` one module per site (AA intelligence, AA evaluations — medical, legal, science, vision, 3D, long context, agents —, AA media incl. music, AA Decision, AA STT, Arena, Design Arena, BridgeBench, Agentset, MTEB) · `prices/` OpenRouter, Kie, Codex catalogue, Hermes providers, declared offers · `plans/` subscriptions (meters, real usage, plan values; `quota_watch` service) · `agent/` the 48 h research agent (prompt + cycle digest) · `web.py` shared web access (FlareSolverr, Next.js data) · `sources.py` registry, snapshots retention |
| `analysis/` | **Analysis** — understands the data, organises the DB, keeps the active library, tells the owner | `parse` + `ingest` (snapshots → benchmarks / offers with identities) · `identity`, `aliases`, `media`, `catalog` · `knowledge` (owner's declarations) · `scoring`, `select`, `tiers`, `decision_pareto`, `postes`, `dossier` · `changes`, `alerts` (Telegram, buttons), `recommend` · `refresh` = the cycle |
| `interface/` | **Interface** — the model library page | `library` (rows, publish), `page` (HTML), `translate` (English), `site/` (Cloudflare Pages functions) |
| `serve/` | What Walter calls at run time | `choose` (pick), `intent` (decision model), `execution` (routes, probes), `media_exec` (generation), `hermes_sync` |
| `store/` | The database | `db`, `migrations/` |
| `llm/` | walter-llm gateway (own venv, service :8894) | |
| `cli.py`, `bin/` | The `walter-router` command, cycle and control entry points | |

The import name stays `walter_router` (`walter_router/__init__.py` points it at this folder): `walter_router.analysis.select`
is `analysis/select.py`.

## Cycle every 48 h (timer `walter-router-refresh`, `bin/walter-router-cycle`; was daily until 2026-10-02)
1. research + analysis: every source is fetched by the router itself (since 2026-10-21 also AA Intelligence, AA media
and Design Arena, absorbed from the aa-pareto-model-optimizer skill — no browser, no Hermes script), understood,
ranked, active library written; 2. research agent on the ECONOMIC text tier (L1 read from the router — GPT-6 Luna max
via Codex today):
`research/agent/prompt.md` + `walter-router review` digest -> `~/.hermes/logs/walter-router/analysis-YYYYMMDD.md`
(read-only, proposals only; Telegram only when the report says `VERDICT: ACTION`).

## Flow
1. **Collect** → `models.snapshots` (deduplicated by sha256, 30-day retention, latest per kind always kept):
   AA intelligence (Next.js data of an AA model page), AA multimodal (server-rendered leaderboard tables), Design Arena (its JSON API), Arena.ai (15 boards read
   from the pages' embedded data: text, French, coding, webdev, vision, document, search, agent, text-to-image,
   image edit, text-to-video, image-to-video, video edit), OpenRouter (`?output_modalities=all` + media prices
   from each model page's `displayPricing`, base unit = price ÷ `displayMultiplier`), Kie pricing, Codex account
   catalogue (read through Hermes), and the live `/models` (with prices) of OpenAI-compatible providers configured
   in Hermes (`config/providers.json`, today Arnict AI; key read at run time from `~/.hermes/.env`, sent as a
   header only). Service postes (2026-10-16): AA Speech-to-Text (`aa_stt`), Agentset rerankers + embeddings
   (`agentset`), MTEB French retrieval (`mteb`, see « Internal postes »). A failing source keeps its last good snapshot.
2. **Parse** → `models.benchmarks` (measured quality) and `models.offers` (callable, priced), linked through
   `models.canonical`/`models.aliases` (deterministic normalisation + justified manual aliases in `aliases.json`).
   Every media offer is classified (`analysis/media.py`): `offer_kind` generation | fee | tool, `modes`
   t2i/i2i/t2v/i2v/r2v/v2v, `resolution`, `audio`, and `norm_price`/`norm_unit` (video per second, image per image,
   voice per 1000 characters). View **`models.catalog`** = one row per model and interface (name, modes,
   providers, price range, resolutions, release date, every leaderboard score, open weights / licence,
   content policy). `models.canonical.open_weights`/`license` come from Arena licences, AA `open_weights` and
   Hugging Face ids; `content_policy = 'unrestricted'` + `base_model_id` for uncensored / abliterated fine-tunes
   (they inherit the base model's score, flagged). View `models.open_models` lists both.
3. **Select** → `models.selection` per task: `best` (quality order among callable models), `value`/`L1-L3`
   (the skill's own Pareto code on the cheapest *real* price: AA list cost × provider/list price ratio),
   `frontier`. Subscription routes (Codex) are listed first, paid route kept as fallback.
4. **Alerts** → `models.alerts`: `challenger` (a model measured better than a pinned favourite on any board of
   the task, `models.task_benchmarks`), `unranked` (one per model: provider release < 30 days without any
   leaderboard score — recorded, **never sent**), `top3` (a model entering the top 3 of a board in a watched
   domain; first run = baseline), `source_stale`. A challenger is only kept when it is in the board's top 3
   (top 3 among models no dearer than the favourite for ratio / budget favourites). Telegram = one line per model
   (`catalog.line`: "🎬 name — modes — price per resolution — providers"; 🖼️ image, 🎬 video, 🗣️ voice,
   🎵 music, 💬 text, 🔓 unrestricted). Telegram via
   `hermes send` only for challengers, stale sources, and unranked models in an interface the owner has a
   preference on. Pinning records already-better models as `baseline` (no message).

## the owner's knowledge (`config/knowledge.json`, applied by `declare` and at every refresh)
Leaderboards rank; the knowledge file says what a model is *for*. `models.profiles` (strengths, workflow,
effort direct|guided|workflow, access/cost notes, content policy override), favourite **roles** per objective in
`models.preferences` (label, description, French request `signals`, priority) and `models.affinities` (close calls:
inside the tie margin — 1 AA point, 10 Elo — the preferred model, then a subscription route, wins).
`decide <task> "<request>"` = signals → role → favourite → route + workflow + a `brief` listing every role so the
orchestrator can overrule the keyword match. Video today: default/équilibré H3 (Kie), premium Seedance 2.5
(workflow: references + adapted prompt), action H3, UGC Omni 1.1 (Flow, Gemini AI Pro credits), budget Grok 1.5.

## Text tiers (the owner's method — docs/TIERS.md)
L1 économique / L2 intermédiaire / L3 haut de gamme on the AA Pareto frontier of callable model x reasoning level at
real provider cost (`tiers.py`): L1 = first knee above 35 AA, L2 = best pts per extra $ from L1, L3 = best pts per
extra $ from L2 within 5 points of the ceiling. Declared tiers live in knowledge.json `levels`; a different nightly
result raises one `tier` alert (adopt/ignore). Specialised tasks keep only their #1 (`best` rank 1).

## Weighting and dossiers
`scoring.composite(task)`: each board of the task (`models.task_benchmarks.weight`) is put on 0-100 (linear from the
board's median model = 0 to its leader = 100), weighted by weight x reliability (votes v/(v+500); provisional 0.5)
and shrunk toward 50 when the evidence is thin (K = 0.25). The `best` level ranks callable models by this composite,
then close calls (margin 1.5 composite points) go to the owner's affinity, then a subscription route.
Every refresh writes one JSON per task to `models.dossiers` (view `models.latest_dossiers`): boards and weights,
the owner's roles with fiches/workflows, the top candidates with per-board evidence, routes, prices, open weights,
content policy, affinity, the level picks, and the decision rules. `walter-router dossier <task>` prints it.
BridgeBench (bridgebench.ai, behind Cloudflare) is fetched through the local FlareSolverr (127.0.0.1:8191).

## Phase A + B (2026-10-02 evening)
- **2026-10-04 — notifications are CHANGES between cycles** (`changes.py`): a model newly on a leaderboard or
  newly listed by a provider, an active model nerfed (score drop > 15 Elo / 2 AA pts / 30 BridgeBench pts on a board
  of the task it is active for), an offer >= 15 % cheaper. challenger / new_best / tier are sent only with such a
  reason (`why`); `nerf` and `pareto` (text frontier entrant thanks to a release or price drop) are new kinds. The
  orchestrator fiche de poste is no longer notified (static comparison). One airy block per new model, all the roles
  it beats grouped, short numbers (`alerts.ref`) — « adopter 1 », « adopter 1 action », « ignorer 2 ».
- **Telegram = model news only** (superseded by the line above for the trigger rule): `challenger` (a favourite overtaken from a top-3 place), `tier` (the owner's method
  designates another text tier, or the orchestrator fiche de poste finds a clearly better orchestrator), `new_best`
  (a specialised task's auto-picked #1 changed and scores higher; « ignorer N » pins the previous one). No credit,
  staleness, podium or analysis messages; a cycle failure is reported only after two failed cycles in a row.
- **Replies**: plugin tool `walter_verdict` (« adopter N » / « ignorer N »); adopting an orchestrator sets Hermes
  `model.default/provider` (config backup + graceful gateway restart).
- **Learning**: `models.exec_log` (every routed attempt; a provider x model failing >= 50 % of its last >= 3 runs in
  14 days is demoted), `models.feedback` + tool `walter_feedback` (the owner's verdicts move a model by +/-3 composite
  points per net rating, capped +/-9).
- **Fallback order**: subscription (Codex) -> Kie when available and <= 1.25 x OpenRouter's price -> OpenRouter; a
  specialised task whose #1 has no subscription route gets the best subscription model of that task appended.
  Hermes' own `fallback_providers`: kie-codex gpt-6-1-sol, then OpenRouter.
- **Names**: `alias-add/alias-remove/alias-list` (validated: unscored -> scored, no chain, evidence; renames need a
  source URL); the 48 h analysis agent applies certain links, then the cycle re-derives (`refresh --skip-collect`).
- **Media execution**: `generate` / tool `walter_generate` (media_exec.py): role -> prompt rewritten by the
  economic tier in the model's style (config/media_models.json) -> workflow (Seedance premium: reference still with
  Sunburst first) -> Kie market API or OpenRouter /videos, /images -> files in ~/.hermes/generated/walter-router.
  Params coerced to each model's schema (config/kie_media_schemas.json, from docs.kie.ai OpenAPI).
- **Fiches de poste** (`postes.py`, knowledge.json `postes`): orchestrator / agent_worker on intelligence (AA),
  agentic (Arena agent), reliability (BridgeBench trustworthiness), speed (BridgeBench), access; context window from
  OpenRouter. `walter-router postes [poste]`.
- Hermes plugin sources are mirrored in `hermes-plugins/` (live copy: ~/.hermes/plugins).

## In production (2026-10-02)
- **Hermes plugin** `~/.hermes/plugins/walter-router` (toolset `walter-router`, enabled for cli + telegram):
  `walter_route` (which model/provider/workflow for a task; video role by objective) and `walter_run` (runs a text
  sub-task on the routed model in a separate `hermes chat --oneshot --provider P -m M` process — plugin tools get no
  parent agent, so `delegate_task` cannot be pinned from a plugin; falls back to the next route; hidden inside its
  own children via `WALTER_ROUTER_CHILD=1`). Tests: `test_walter_router.py` next to the plugin.
- **Execution routes** (`execution.routes`): preferred provider, subscription (Codex), then paid by price; Kie only
  for Claude models (its Hermes provider is the Anthropic endpoint). `probe` = a 5-token live call per provider at
  every refresh (`models.provider_status`); a failed provider goes last.
- **Intent (Jev)**: `route "<request>"` classifies with TypeSafe Jev through OpenRouter's Decisions API
  (`intent.py`; one call = task + video role + level + unrestricted, ~0.3 s, ~0.00005 $; criteria from
  `tasks.intent_hint` / role descriptions in knowledge.json). Eval `eval/intents_fr.json`: task 30/30, video role
  6/7 (keywords 5/7). Keywords stay the fallback. `walter_route` without `task` uses it; the plugin also adds a
  system-prompt rule so the orchestrator calls walter_route before choosing a model.
- **Kie**: `kie` (Anthropic endpoint, Claude) and `kie-codex` (Responses endpoint, GPT; Hermes provider added
  2026-10-02). Kie Claude is often degraded: a 5-token preflight runs before any Kie route in `walter_run`.
  `~/.hermes/plugins/kie-compat` (strip `output_config`) is kept DISABLED: hypothesis not confirmed.
- **Credit**: the OpenRouter probe reads `/api/v1/credits`; below 1 $ its routes go last and a `billing` alert is
  sent once. `walter_run` last resort = GPT-6.1 Sol on the Codex subscription (never for unrestricted requests).
- **Health**: `walter-router health` (exit 1 when not fed), shown in walter-core `walter_health`;
  `walter-router-failure.service` (OnFailure of the refresh) sends one Telegram message.

## Subscriptions (2026-10-14) — information only, no routing effect
the owner's plans in `config/subscriptions.json` (ChatGPT Plus 20 $, Claude Pro 20 $), shown on the library page
(tab 💳 Abonnements / Subscriptions) with two sources only (2026-10-14):
- **Our measurement** (`research/plans/subscriptions.py`): the weekly meter — ChatGPT Plus real, from the Codex usage API
  through Hermes (read-only); Claude Pro estimated from the Claude Code transcripts (no Claude login on the VM): units =
  input + cache writes + 5 x output over a capacity, `walter-router subscriptions calibrate anthropic-pro <weekly %>`
  with the % shown on claude.ai — and the tokens W.Alter's runtimes really used (Hermes state.db sessions billed to
  openai-codex + Codex CLI/Desktop sessions for ChatGPT, Claude Code transcripts for Claude), priced at list API rates
  (OpenRouter first-party pricing). Each ChatGPT reading stores the cumulative API value, so two readings of the same
  week ≥ 3 points apart give the API value of a meter point → the plan's measured capacity (a floor).
- **SemiAnalysis** (2026-10-05): published API value of each plan per model, tokens per month on their agentic mix.
Readings in `models.subscription_usage` (view `latest_subscription_usage`), taken by `walter-router-quota.service`
(Walter bus consumer on `turn.ended`/`session.ended`, sweep every 30 min). `walter-router subscriptions [refresh]`.
Routing and tiers are unchanged.

## Cloudflare access (decision model Clef)
`intent.py` calls Clef on Cloudflare Workers AI with `CLOUDFLARE_AI_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` from
`~/.hermes/.env` (scoped token « W.Alter — Workers AI (walter-router intent) », permission Workers AI Read, created
2026-10-04 with the global key). Any other Cloudflare work goes through the instance's Cloudflare helper (host.json `cloudflare_cli`)
(`check` / `-- <command>`): global key from Bitwarden « W.Alter · cloudflare », account e-mail from `.env`
`CLOUDFLARE_EMAIL` (the vault item has no e-mail; an example e-mail from a skill gives 401/403).

## Internal postes — every W.Alter module that uses AI (2026-10-16)
Tasks the modules call, never offered to the intent classifier (`models.tasks.internal`, `requirements`, `consumers`;
migration 020): `summarization`, `memory_extraction` (objective `level` = the owner's text tier L1 from
`general`, filtered by `requirements.min_context` — they move when he adopts a new tier), `voice_assist` (BridgeBench
speed primary and required, Arena French, BridgeBench trustworthiness; `requirements.reasoning = minimal` is applied to
its routes), `stt`, `embeddings`, `rerank`. `pick` of a transcription / rerank / embedding poste returns `openrouter_id`. Hermes follows through `sync-hermes [--apply] [--no-restart]` (`hermes_sync.py`:
auxiliary compression/title_generation of the main config and the wild/hephaestus profiles + `fallback_chain`, cron
agent jobs in `CRON_POSTES`; run by the cycle and after each verdict); services through walter-llm (`model` = poste or
`general/L2`). `generate --task tts --voice V --style S` = Hermes TTS command provider. Module table: walter-memory
RUNBOOK § Modules IA → Walter Router.

**Service boards — stt, rerank, embeddings (2026-10-16, migration 021, the owner: « rajouter le reranking, embedding
et STT »).** Ranked like any task (`task_benchmarks` → `scoring.composite`, dossiers, challengers), still PINNED on the
models in use (`watch = quality`): a better measured model is only proposed (« Changer »), never switched.
- Sources (collected every cycle): `aa_stt` = artificialanalysis.ai/speech-to-text chart download tables (AA-WER,
  speed factor, price per 1000 min, per model x host; English datasets — **AA publishes no French STT result**);
  `agentset` = agentset.ai/rerankers and /embeddings (pairwise ELO on RAG retrieval, average latency, nDCG@10,
  $/1M tokens; boards last updated 2026-02-15 by Agentset); `mteb` = MIRACL hard-negatives **French** nDCG@10 from
  github.com/embeddings-benchmark/results, for every embedding model OpenRouter serves (GitHub API: 1 listing + 1 call
  per model; `GITHUB_TOKEN` in `~/.hermes/.env` is used if present).
- **Stored scores are always "higher = better"** (podium, challenger, nerf code rely on it): WER -> `100 - WER %`
  (`extra.wer_pct` keeps the measure), latency -> `1000 / ms` (`extra.latency_ms`); proposals print the raw measure.
- Weights: stt = `aa_stt:wer` 0.75 (primary) + `aa_stt:speed` 0.25; rerank = `agentset:rerank` 0.7 + `rerank_speed` 0.3,
  and `requirements.max_latency_s = 0.7` excludes any model measured slower (voice recall budget); embeddings =
  `agentset:embeddings` 0.5 + `mteb:retrieval_fr` 0.5 with `require_primary` (re-vectorising is never decided on a
  single test).
- Interfaces follow the offers: stt -> `transcription` (dedicated STT models + every OpenRouter chat model that hears
  audio, as an extra offer `<id> | audio input`), embeddings -> `embedding`, rerank -> `rerank`. OpenRouter per-second /
  per-hour / per-search prices come from the model pages (`displayPricing`) and are normalised to $/min, $/search;
  embeddings compare in $/1M tokens. Before 021 stt sat on `audio` (the TTS interface) and embeddings on `embeddings`
  (no offer): no callable candidate could rank.
- `requirements.on_change` = what adopting implies, printed in the proposal and the dossier: embeddings = re-vectorise
  every Hindsight bank (Hindsight keeps its own model config until that is done); rerank = Hindsight's reranker is the
  static drop-in 20-reranker-fallback.conf; stt = a dedicated STT model needs the gemini-stt plugin on OpenRouter's
  transcription API. Dossiers carry a `ranking` (every measured model, callable or not, pinned ones always listed).

## Commands
```
bin/walter-router migrate
bin/walter-router refresh [--no-notify] [--dry-run]
bin/walter-router pick <task> [--level L1|L2|L3]      # preferences first, then computed choice
bin/walter-router pick <task> --require unrestricted|open_weights   # hard constraint, best callable model
bin/walter-router decide <task> "<request in French>"  # role by objective, route, workflow, brief
bin/walter-router declare                               # apply config/knowledge.json
bin/walter-router sync-hermes [--apply]                 # Hermes auxiliary jobs / crons follow the postes
bin/walter-router dossier <task>                        # the JSON the router reads
bin/walter-router route "<request>" [--task T]            # Jev intent -> decision -> execution routes
bin/walter-router classify "<request>"                    # Jev intent only
bin/walter-router health | probe [--provider P] | tasks | notify-failure
bin/walter-router prefer <task> [--objective value|best_available] [--pin model_id[/variant]] [--provider p] [--note ...]
bin/walter-router alerts [--all]
bin/walter-router verdict <alert_id> adopted|dismissed [--note ...]   # adopted challenger becomes the favourite
bin/walter-router status
```
Tests: `venv/bin/python -m pytest -q tests` (DB tests run inside a rolled-back transaction).

## Specialised tasks (2026-10-21)
`medical` (AA HealthBench Professional 60 % + HealthBench 40 %), `legal` (AA Harvey LAB), `science` (AA CritPt 35 %,
GPQA 35 %, SciCode 15 %, HLE 15 %), `long_context` (AA-LCR), `writing` (Arena creative writing 60 % + French 40 %),
`music` (AA Music vocals + instrumental; Kie's Suno is called with model V6 = AA « Suno v6 »). 3D now also weighs AA-3D
(20 %), vision MMMU-Pro (40 %). New tasks start unpinned (best callable model); a later #1 is only proposed. Intent
eval after adding them: 37/38 (the original 30 all pass; « photo of a mole » goes to medical instead of vision).
`walter-router research [--source KIND]` collects by hand (docs/DATA.md § 9).
2026-10-22: AA domain indexes (artificialanalysis.ai/indexes, frontier models only, with cost and time per task) —
`engineering` (Engineering Index), `finance` (Finance & Accounting 70 % + Economics 30 %), `strategy` (Strategy & Ops),
`cybersecurity` (AA Cyber Index); `medical` now Healthcare Index 50 % + HealthBench Pro 30 % + HealthBench 20 %, `legal`
Legal Index 60 % + Harvey LAB 40 %. Intent eval (eval/intents_fr.json, 42 cases): 41/42 (photo of a mole -> medical).

## Hosts behind a gateway (2026-10-22)
One model is served through OpenRouter by several hosts at different prices (DeepSeek V4 Pro: 0.45 to 1.68 $/M input),
compression (fp4 / fp8 / bf16) and reliability. `research/prices/openrouter_endpoints.py` reads every host of the models
the active library uses (shortlist + pins) into `models.endpoints`; `models.best_endpoints` keeps the cheapest usable
one per model: >= 95 % successful requests over 24 h, never below the vendor's own precision (4-bit only when the
vendor itself serves 4-bit, e.g. Kimi K3 mxfp4), flex tier (half price, slower) only for background work. The library
page shows that host next to the OpenRouter price. Calls do not use it yet (OpenRouter still picks the host): pending
the owner's decision (2026-10-22).

## Research by category (2026-10-22)
`walter-router research [text|image|video|audio|memory|decision|prices|hosts|plans|all] [--analyse]` runs one or more
categories alone (`--list` shows what each reads). Sources shared by categories (Arena, AA media, Design Arena) are
read in parts and merged into their last complete snapshot, so the other categories keep their data (`research
image`: 1 min 40 s with `--analyse` = recompute + republish, no message). The 48 h cycle still runs everything.
