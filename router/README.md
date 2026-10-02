# Walter Router

Model catalogue + per-task model choice for W.Alter. Schema `models` in hindsight-pg (127.0.0.1:5433, creds in ~/.pgpass).
Plan and decisions: `/root/projects/walter-model-router/docs/PLAN-v2.md`.

## Cycle every 48 h (timer `walter-router-refresh`, `bin/walter-router-cycle`; was daily until 2026-10-02)
1. benchmark collection (aa-pareto skill script; its daily Hermes cron 096741a21a32 is paused), 2. router refresh +
notifications, 3. analysis by the ECONOMIC text tier (L1 read from the router — GPT-6 Luna max via Codex today):
`config/analysis_prompt.md` + `walter-router review` digest -> `~/.hermes/logs/walter-router/analysis-YYYYMMDD.md`
(read-only, proposals only; Telegram only when the report says `VERDICT: ACTION`).

## Flow
1. **Collect** → `models.snapshots` (deduplicated by sha256, 30-day retention, latest per kind always kept):
   AA intelligence, AA multimodal, Design Arena (files from the aa-pareto skill cache), Arena.ai (15 boards read
   from the pages' embedded data: text, French, coding, webdev, vision, document, search, agent, text-to-image,
   image edit, text-to-video, image-to-video, video edit), OpenRouter (`?output_modalities=all` + media prices
   from each model page's `displayPricing`, base unit = price ÷ `displayMultiplier`), Kie pricing, Codex account
   catalogue (read through Hermes), and the live `/models` (with prices) of OpenAI-compatible providers configured
   in Hermes (`config/providers.json`, today Arnict AI; key read at run time from `~/.hermes/.env`, sent as a
   header only). A failing source keeps its last good snapshot.
2. **Parse** → `models.benchmarks` (measured quality) and `models.offers` (callable, priced), linked through
   `models.canonical`/`models.aliases` (deterministic normalisation + justified manual aliases in `aliases.json`).
   Every media offer is classified (`walter_router/media.py`): `offer_kind` generation | fee | tool, `modes`
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
   `hermes send` only for challengers, stale sources, and unranked models in an interface Monsieur has a
   preference on. Pinning records already-better models as `baseline` (no message).

## Monsieur's knowledge (`config/knowledge.json`, applied by `declare` and at every refresh)
Leaderboards rank; the knowledge file says what a model is *for*. `models.profiles` (strengths, workflow,
effort direct|guided|workflow, access/cost notes, content policy override), favourite **roles** per objective in
`models.preferences` (label, description, French request `signals`, priority) and `models.affinities` (close calls:
inside the tie margin — 1 AA point, 10 Elo — the preferred model, then a subscription route, wins).
`decide <task> "<request>"` = signals → role → favourite → route + workflow + a `brief` listing every role so the
orchestrator can overrule the keyword match. Video today: default/équilibré H3 (Kie), premium Seedance 2.5
(workflow: references + adapted prompt), action H3, UGC Omni 1.1 (Flow, Gemini AI Pro credits), budget Grok 1.5.

## Text tiers (Monsieur's method — docs/TIERS.md)
L1 économique / L2 intermédiaire / L3 haut de gamme on the AA Pareto frontier of callable model x reasoning level at
real provider cost (`tiers.py`): L1 = first knee above 35 AA, L2 = best pts per extra $ from L1, L3 = best pts per
extra $ from L2 within 5 points of the ceiling. Declared tiers live in knowledge.json `levels`; a different nightly
result raises one `tier` alert (adopt/ignore). Specialised tasks keep only their #1 (`best` rank 1).

## Weighting and dossiers
`scoring.composite(task)`: each board of the task (`models.task_benchmarks.weight`) is put on 0-100 (linear from the
board's median model = 0 to its leader = 100), weighted by weight x reliability (votes v/(v+500); provisional 0.5)
and shrunk toward 50 when the evidence is thin (K = 0.25). The `best` level ranks callable models by this composite,
then close calls (margin 1.5 composite points) go to Monsieur's affinity, then a subscription route.
Every refresh writes one JSON per task to `models.dossiers` (view `models.latest_dossiers`): boards and weights,
Monsieur's roles with fiches/workflows, the top candidates with per-board evidence, routes, prices, open weights,
content policy, affinity, the level picks, and the decision rules. `walter-router dossier <task>` prints it.
BridgeBench (bridgebench.ai, behind Cloudflare) is fetched through the local FlareSolverr (127.0.0.1:8191).

## Phase A + B (2026-10-02 evening)
- **Telegram = model news only**: `challenger` (a favourite overtaken from a top-3 place), `tier` (Monsieur's method
  designates another text tier, or the orchestrator fiche de poste finds a clearly better orchestrator), `new_best`
  (a specialised task's auto-picked #1 changed and scores higher; « ignorer N » pins the previous one). No credit,
  staleness, podium or analysis messages; a cycle failure is reported only after two failed cycles in a row.
- **Replies**: plugin tool `walter_verdict` (« adopter N » / « ignorer N »); adopting an orchestrator sets Hermes
  `model.default/provider` (config backup + graceful gateway restart).
- **Learning**: `models.exec_log` (every routed attempt; a provider x model failing >= 50 % of its last >= 3 runs in
  14 days is demoted), `models.feedback` + tool `walter_feedback` (Monsieur's verdicts move a model by +/-3 composite
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

## Commands
```
bin/walter-router migrate
bin/walter-router refresh [--no-notify] [--dry-run]
bin/walter-router pick <task> [--level L1|L2|L3]      # preferences first, then computed choice
bin/walter-router pick <task> --require unrestricted|open_weights   # hard constraint, best callable model
bin/walter-router decide <task> "<request in French>"  # role by objective, route, workflow, brief
bin/walter-router declare                               # apply config/knowledge.json
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
