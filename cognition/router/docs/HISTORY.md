# Walter Router — history of decisions

Dated notes kept as written when each change was made (newest at the bottom). Where they disagree with
README.md, the README describes the module as it is now.

## (past) Cycle every 48 h (timer `walter-router-refresh`, `bin/walter-router-cycle`; was daily until 2026-10-02)
1. research + analysis: every source is fetched by the router itself (since 2026-10-21 also AA Intelligence, AA media
and Design Arena, absorbed from the aa-pareto-model-optimizer skill — no browser, no Hermes script), understood,
ranked, active library written; 2. research agent on the ECONOMIC text tier (L1 read from the router — GPT-6 Luna max
via Codex today):
`research/agent/prompt.md` + `walter-router review` digest -> `~/.hermes/logs/walter-router/analysis-YYYYMMDD.md`
(read-only, proposals only; Telegram only when the report says `VERDICT: ACTION`).

## (past) Flow
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

## (past) the owner's knowledge (`config/knowledge.json`, applied by `declare` and at every refresh)
Leaderboards rank; the knowledge file says what a model is *for*. `models.profiles` (strengths, workflow,
effort direct|guided|workflow, access/cost notes, content policy override), favourite **roles** per objective in
`models.preferences` (label, description, French request `signals`, priority) and `models.affinities` (close calls:
inside the tie margin — 1 AA point, 10 Elo — the preferred model, then a subscription route, wins).
`decide <task> "<request>"` = signals → role → favourite → route + workflow + a `brief` listing every role so the
orchestrator can overrule the keyword match. Video today: default/équilibré H3 (Kie), premium Seedance 2.5
(workflow: references + adapted prompt), action H3, UGC Omni 1.1 (Flow, Gemini AI Pro credits), budget Grok 1.5.

## (past) Text tiers (the owner's method — docs/TIERS.md)
L1 économique / L2 intermédiaire / L3 haut de gamme on the AA Pareto frontier of callable model x reasoning level at
real provider cost (`tiers.py`): L1 = first knee above 35 AA, L2 = best pts per extra $ from L1, L3 = best pts per
extra $ from L2 within 5 points of the ceiling. Declared tiers live in knowledge.json `levels`; a different nightly
result raises one `tier` alert (adopt/ignore). Specialised tasks keep only their #1 (`best` rank 1).

## (past) Weighting and dossiers
`scoring.composite(task)`: each board of the task (`models.task_benchmarks.weight`) is put on 0-100 (linear from the
board's median model = 0 to its leader = 100), weighted by weight x reliability (votes v/(v+500); provisional 0.5)
and shrunk toward 50 when the evidence is thin (K = 0.25). The `best` level ranks callable models by this composite,
then close calls (margin 1.5 composite points) go to the owner's affinity, then a subscription route.
Every refresh writes one JSON per task to `models.dossiers` (view `models.latest_dossiers`): boards and weights,
the owner's roles with fiches/workflows, the top candidates with per-board evidence, routes, prices, open weights,
content policy, affinity, the level picks, and the decision rules. `walter-router dossier <task>` prints it.
BridgeBench (bridgebench.ai, behind Cloudflare) is fetched through the local FlareSolverr (127.0.0.1:8191).

## (past) Phase A + B (2026-10-02 evening)
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

## (past) In production (2026-10-02)
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

## (past) Subscriptions (2026-10-14) — information only, no routing effect
the owner's plans in `config/subscriptions.json` (ChatGPT Plus 20 $, Claude Pro 20 $), shown on the library page
(tab 💳 Abonnements / Subscriptions) with two sources only (2026-10-14):
- **Our measurement** (`plan/subscriptions.py`): the weekly meter — ChatGPT Plus real, from the Codex usage API
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

## (past) Cloudflare access (decision model Clef)
`intent.py` calls Clef on Cloudflare Workers AI with `CLOUDFLARE_AI_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` from
`~/.hermes/.env` (scoped token « W.Alter — Workers AI (walter-router intent) », permission Workers AI Read, created
2026-10-04 with the global key). Any other Cloudflare work goes through the instance's Cloudflare helper (host.json `cloudflare_cli`)
(`check` / `-- <command>`): global key from Bitwarden « W.Alter · cloudflare », account e-mail from `.env`
`CLOUDFLARE_EMAIL` (the vault item has no e-mail; an example e-mail from a skill gives 401/403).

## (past) Internal postes — every W.Alter module that uses AI (2026-10-16)
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

## (past) Commands
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

## (past) Specialised tasks (2026-10-21)
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

## (past) Hosts behind a gateway (2026-10-22)
One model is served through OpenRouter by several hosts at different prices (DeepSeek V4 Pro: 0.45 to 1.68 $/M input),
compression (fp4 / fp8 / bf16) and reliability. `research/prices/openrouter_endpoints.py` reads every host of the models
the active library uses (shortlist + pins) into `models.endpoints`; `models.best_endpoints` keeps the cheapest usable
one per model: >= 95 % successful requests over 24 h, never below the vendor's own precision (4-bit only when the
vendor itself serves 4-bit, e.g. Kimi K3 mxfp4), flex tier (half price, slower) only for background work. The library
page shows that host next to the OpenRouter price. Since 2026-10-22 (owner's go) the route carries
`or_provider` = usable hosts cheapest first (`allow_fallbacks`), and walter-llm passes it to OpenRouter
(`extra_body.provider`); its log records the host that answered. Hermes' own `walter_run` (hermes chat --provider
openrouter) cannot pass it and still lets OpenRouter choose.

## (past) Subscriptions in the price (2026-10-22)
Owner: « en prenant en compte aussi les abonnements et le prix de revient du token avec ceux-ci ». `research plans`
(and every cycle) records in `models.subscription_costs` the cost price of a token through each plan = plan price / API
value it carries per month, at the current pace (7 days x 4.35) and at capacity (measured meter points, else
SemiAnalysis). ChatGPT Plus on 2026-10-22: 2.1 % of the API price at the current pace, 4 % at measured capacity.
A subscription route (`route_provider` in the instance's subscriptions.json) carries `cost_price_1m` and its weekly
meter; it stays first while the meter is under 90 % (`execution.QUOTA_SWITCH`), then goes after the paid routes. The
library shows « Codex ≈ 0,04/0,21 $/M (prix de revient, 2,1 % du prix API, quota 4 %) ». Claude Pro has no route
(Claude Code only).

## (past) Research by category (2026-10-22)
`walter-router research [text|image|video|audio|memory|decision|prices|hosts|plans|all] [--analyse]` runs one or more
categories alone (`--list` shows what each reads). Sources shared by categories (Arena, AA media, Design Arena) are
read in parts and merged into their last complete snapshot, so the other categories keep their data (`research
image`: 1 min 40 s with `--analyse` = recompute + republish, no message). The 48 h cycle still runs everything.

## (past) Plans research and editing (2026-10-22)
Owner: providers kept = OpenRouter, Kie, Codex, Arnict (uncensored); hosts behind OpenRouter are OpenRouter's (billed
through it), the router only orders them. `research plans` (and the 48 h cycle) = meters, then billing mails, then
web research, then the cost price:
- **mails** (`plan/mail.py`): the owner's Gmail, read-only grant `google-memory` via `walter-secret`, only
  subscription mails from AI vendors (Google Play / Payments for Google AI plans); deterministic parsing, no mail
  content sent to a model; the latest mail of each plan decides; a difference with the declared plans becomes a
  `plan_change` alert (Telegram buttons « ✅ Mettre à jour / ✖️ Ignorer »; adopting applies it). Credit top-ups
  (OpenRouter, API credits) are recorded, never proposed as plans.
- **web** (`plan/watch.py`): the economic tier with web tools looks for published facts on each plan
  (SemiAnalysis / Tokenomics, vendors' limit pages, other measurements) -> `models.plan_evidence` with source and date;
  published plan values feed the capacity of the cost price when we have no measure of our own.
- **editing**: `walter-router plans list | set ID [--vendor --plan --price --models --note] | retire ID`
  (`plan/declared.py`, the instance's subscriptions.json, previous version kept in config/router/history/),
  the Subscriptions tab form (page -> /api/plans -> control service POST /plans, HMAC over the body too), and adopted
  plan_change alerts.

## (past) Plan news (2026-10-22)
Owner: « s'il y a un nouvel avantage ou une modification via un des abonnements que l'on possède, on doit être
notifié ». `plan/news.py`, run by `research plans` (and the cycle): product / plan mails of the vendors of his plans
(exact senders: OpenAI / ChatGPT, Anthropic, Google One / Gemini…; sign-in codes, receipts, trials, developer / API
newsletters left out; body read without any model, tracking links removed) and facts the web research adds for one
of his plans that were not known before. One Telegram notice each (« 💳 <plan> — nouveauté », button « 👁️ Vu »), sent
at the end of `research plans` (`--no-notify` to only record). Window: mails of the last 21 days not seen before.

## (past) Hermes plugged in (2026-10-22)
- `sync-hermes` (end of every cycle, after each verdict) writes into Hermes' own config: auxiliary jobs compression,
  title generation, curator (-> summarization = tier L1) and vision (-> vision), with their fallback chains, and the
  router's host order for each OpenRouter model (`provider_routing.models.<id>.order`, marked `_managed_by:
  walter-router`; priority tiers never imposed). Verified: Hermes builds {'order': ['wafer/us', …]} for Kimi K3.
- Hermes plugin `walter-router`: tools walter_route / walter_run / walter_generate / walter_feedback / walter_verdict and
  new `walter_plans` (list, change, cancel a plan on the owner's word). The availability check looked for the
  command in the current directory since 2026-10-19 (tools hidden); it now uses the PATH.
- Decision models: d1-ultra for decision and decision_vision (owner, 2026-10-22), intent eval 42/42.
- Media fallback: the same model on its next provider; another model only when declared.

## Video understanding and what an agent gets from `route` (2026-10-22)
The owner's example (analyse a client's reference video, research, plan, images, video, post-production, review)
showed the router had no task to watch a video: `vision` picked Claude Fable 5, which reads no video at all. New task
`video_understanding` (migration 031): `modes = {video}`, so only offers declaring video input (OpenRouter's
`input_modalities`, now stored on chat offers) are callable, in the selection, the dossier, the Hermes routes and the
subscription fallback. No arena measures it (AA and Arena rank video generation only; Arena vision = images;
Video-MME saturated at ~90 %): boards = Video-MME-v2 (authors' measurement, newest rows Gemini 3 / Qwen 3.6) and the
LLM Stats video boards (current, all vendor self-reported, reliability 0.5). Two hand-checked aliases (Gemini 3 Pro /
gemini-3-pro-preview, Gemini 3 Flash / gemini-3-flash-preview). First choice: Gemini 3 Flash Preview.
Same day, what the agent sees: `route` no longer calls the decision model when the caller fixed the task (and the
level for general); it reads an optional `--context` line, so « fais la suite » is classified with what came before;
the Hermes plugin shows each route's price per million tokens (a subscription at its cost price) and no longer a
media route for text decisions; the tool descriptions name the decision model instead of Jev.

Withdrawn the same day by the owner (« on n'a pas de benchmark satisfaisant sur la vidéo, donc pas besoin d'en faire
une catégorie spécifique », migration 032): no video task and no video boards. What stays: chat offers record the
inputs a model reads, and `--require video_input` (pick / route / walter_route) gives the best image-analysis model
that reads a video, with only routes that accept it.

## Every agent knows the router (2026-10-22)
The owner: « il faut que le modèle appelé sache que ce module existe, à quoi il sert, et quels sont ses paramètres
d'utilisation (spécialisations, niveaux de réflexion, capacités de génération ou d'analyse, modèle de décision…), sans
qu'il ait besoin de connaître le nom du modèle, son provider ». Claude Code and Codex had called the router for a real
task zero times in 30 days (only maintenance sessions): their profile had one line on a lookup tool, nothing on what to
ask for, and no way to run a sub-task or a generation. Now one brief, generated from the database (`serve/brief.py`,
`walter-router brief`), reaches every runtime: Hermes as a system-prompt section, the walter MCP server as its
instructions (Claude Code), the Codex / DSH profiles through `@instance/state/router/brief.md` (written by the cycle,
profiles re-rendered by walter-soul when it changes). The same four tools everywhere: `walter_route`, `walter_run`,
`walter_generate`, `walter_plans` (MCP: `walter_run` is one walter-llm call with its own agent token `walter-mcp`).
The agent view of a decision (`--agent`, `serve/agent_view.py`) is the router's, shared by the plugin and the MCP.

## The orchestrator chooses, the router executes (2026-10-22)
The owner: the orchestrating agent decides which specialised model to spawn for each piece of work (the decision
model routes the intent, and will set the agentic level for walter-context; the orchestrator may also call it for its
own choices); a model and provider named in the request run exactly as named; generation is not a separate kind of
call. Now: `serve/named.py` resolves a named model (provider ids, router ids, aliases, display names, `model/variant`)
and gives only that provider's routes — or `mode: none` with where it is available, never a substitute (the
subscription last resort never applies to it); `serve/run.py` (`walter-router run`, moved out of the Hermes plugin)
does the job: a text sub-agent with tools as a one-shot Hermes run on the chosen model, or the media generation
(named provider honoured); `intent.ask` (`walter-router ask`, tool `walter_decide`) opens the decision model to any
choice. Tools everywhere: walter_route, walter_run, walter_decide, walter_plans (walter_generate merged into walter_run;
the walter MCP's walter-llm token, created the same day, revoked as unused). Constrained picks (`--require`) now rank
on the task composite like any pick.


## Native text execution; failover belongs to the router (2026-10-23)

Owner: if a model’s provider does not answer, use that model’s fallback provider and notify the user;
Hermes is not part of this execution path. The earlier one-shot wrapper could receive a successful
answer from an internal runtime fallback while reporting the initial provider/model as successful.

Text `run` now owns a native tool loop and an exact-route gateway transport. It tries only providers
of the selected model, carries the conversation/tool results across failures, records actual attempts
and response ids, and requires callers to forward `user_notice`. The automatic subscription/model
substitution and hardcoded last-resort model are removed. Named provider restrictions stay explicit.
No runtime source, global configuration or provider key is changed. Regression coverage includes
provider exhaustion, empty/wrong-model responses, no hidden retry, preserving tool side effects,
tool permissions, execution budgets and notification delivery in the result.


## Documentation vérifiable et note orchestrateur unique (2026-10-23)

Le propriétaire demande une documentation complète maintenue avec le module, et une note courte destinée à
walter-context pour expliquer au modèle orchestrateur à quoi sert le routeur et comment l’utiliser efficacement.
La référence est désormais générée depuis les schémas d’outils, le parseur CLI, le catalogue PG, les tâches/poids,
les constantes, l’environnement et la configuration livrée. Un contrôle hors ligne est intégré aux tests ; la
vérification live contrôle aussi PG. Une colonne SQL non décrite ou une référence périmée doit produire un échec.

`brief` reste l’unique producteur de la note ; `brief --json` lui ajoute versions, empreinte, taille, outils requis
et politique de chargement. La note ne contient pas de choix de modèle ou de prix volatils. Un consommateur
walter-context prépare cette source par l’interface CLI, vérifie les outils réels et la garde stable pendant un
tour. Cela prépare le composeur futur sans modifier les ports de compression actifs. Les limites d’exécution,
de confidentialité et de permissions du texte natif sont explicites ; elles ne sont pas remplacées par une
promesse de portabilité universelle. Les documents de conception anciens sont identifiés comme historiques.


## 2026-10-24 — Exécuteur HeyGen Video 1

Ajout de la configuration média `heygen-video-1` via OpenRouter pour exécuter ce modèle déjà présent au catalogue. Aucun favori modifié. Le catalogue vidéo public annonce 480p, 768p et 2K, sans 720p exact ; utiliser une résolution native prise en charge et distinguer toute conversion de livraison.


2026-10-24 : le décodage HTTP média accepte les espaces et sauts de ligne avant un objet/tableau JSON ; les réponses binaires restent des octets.

## 2026-10-26 — Route Claude Pro et contexte possédé par Walter

À la demande du propriétaire, ajout de `claude-pro` dans le Router et sa passerelle. Le client officiel ne fournit que le transport authentifié et l’attribution technique ; les messages, outils, paramètres et la boucle d’exécution appartiennent au consommateur Walter. La CLI reçoit un accusé synthétique sans outil plutôt que la vraie réponse du modèle. Le contenu natif n’est jamais repris par simple filtrage de chaînes : le pont reconstruit la requête à partir du payload du consommateur et d’un bloc d’attribution validé.

Autorisation dédiée dans Walter Secrets, renouvellement atomique avec verrou interprocessus, catalogue limité aux modèles qualifiés de l’instance, vrais compteurs d’abonnement et journal d’usage sans contenu. Les configurations directes Hermes ne reçoivent pas ce nouveau fournisseur. Les restrictions fournisseur explicites et l’absence de fallback de modèle restent inchangées. Guide : CLAUDE-SUBSCRIPTION.md.


## 2026-10-26 — Fournisseur effectif des décisions texte

Les décisions ordinaires et les modèles nommés exposent désormais comme `provider` la première route
exécutable ordonnée, au lieu du fournisseur historique du classement. Sans route, la valeur est nulle.
L’ordre peut évoluer avec les abonnements et quotas sans laisser un résumé contradictoire.
Les restrictions explicites et le fournisseur réellement observé après exécution restent inchangés.


## 2026-10-26 — Guardian : le module se maintient lui-même

Le propriétaire : « cela doit être fait automatiquement à partir de maintenant, fais un guardian dans le module qui
s'occupe de la maintenance de celui-ci, peut-être propulsé par L2 ». Déclencheur : la source AA Speech-to-Text était
muette depuis 118 h (page refaite le 24/10, plus de tableaux téléchargeables ; le lecteur lit désormais les objets
modèle × hébergeur de la page) et une panne de l'API Claude de Kie déclassait toutes les vidéos et images Kie.

`guardian/` : détection sans modèle (sources, cycle, fournisseurs, tests, référence générée), incidents dans
`models.guardian_incidents`, actions simples d'abord (nouveau test du fournisseur, relecture de la source), pannes
extérieures attendues, réparation par le niveau L2 sur une copie du module (module, configuration de l'instance et
services en lecture seule pour l'agent), mise en place seulement après des contrôles déterministes et sur des
fichiers que personne n'est en train de modifier, puis commit de ces seuls fichiers. Référence générée régénérée
sans modèle. Telegram seulement pour une réparation faite, une décision du propriétaire, une panne extérieure de
48 h. Toutes les 6 h et après chaque cycle. Premier essai réel : test média réparé en 2 min 30 (commit 4123ac9).

Kie est testé en trois services distincts : `kie` (API Claude), `kie-codex`, `kie-media` (compte et crédit, aucune
génération). Les médias suivent `kie-media` ; le détail d'un test garde la raison donnée par le fournisseur
(« no_available_account »). Le transport d'abonnement Claude refuse un modèle non qualifié avant de charger litellm.

## 2026-10-29 — Corrélation et mesure du gateway

Les requêtes HTTP sont corrélées individuellement aux runs Memory ouverts ; DSH utilise les options publiques
de son fournisseur pi-ai sans modifier son moteur. Une corrélation inconnue ou ambiguë échoue explicitement.
Les flux interrompus gardent leur trace d’échec. Migration 036 : usage jsonb et provenance du coût ; une mesure
absente ne devient plus un coût nul. Voir EXECUTION.md et llm/README.md pour les limites et le retour arrière.

### 2026-10-29 — Télémétrie du texte natif et session DSH réelle

Le format de session DSH `session-UUID` est conservé exactement pour le lookup local. Les essais réels
ont vérifié la corrélation et le routage observé. Le port CLI exact partage désormais la télémétrie du
port HTTP ; la boucle native transmet usage et provenance du coût à chaque tentative et au journal.
