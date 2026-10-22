---
name: walter-model-router
description: "Use when choosing which AI model or provider W.Alter should use for a task, checking live leaderboards, prices or the owner's AI subscriptions, explaining or tuning Walter Router (tasks, weights, preferences, alerts, library page), or analysing its 48 h cycle."
version: 4.1.0
author: W.Alter
metadata:
  hermes:
    tags: [router, model-selection, pricing, benchmarks, subscriptions, postgresql, openrouter, kie, codex]
    related_skills: [aa-pareto-model-optimizer, kie-ai-api-direct, model-router-intelligence-loop]
---

# Walter Router

Module `/walter/router` (also reachable as `/opt/walter-router`), command `walter-router` on the PATH. Data: schema
`models` in PostgreSQL 127.0.0.1:5433 db `hindsight` (password only in ~/.pgpass; every table and view is commented).
Read first: `/walter/router/README.md` (current state: layout, how a choice is made, consumers, access, rules), then
`docs/DATA.md` (every source and table), `docs/TIERS.md` (text tiers), `docs/HISTORY.md` (dated decisions).
The old store (schema `walter_router`, fixed weight vectors, router_matrix.json) is retired: never use it.

## Ask the router — never hardcode a model
- `walter-router pick <task> [--level L1|L2|L3] [--role R]` — model, provider order with prices, fallbacks.
  `walter-router tasks` lists the task keys (42, incl. medical, legal, engineering, finance, strategy, cybersecurity,
  science, long_context, writing, music, vision, video roles…).
- `walter-router route "<demande>"` — the decision model (d1-ultra, then Mercury Decide free, then Clef) classifies
  the request, then the decision with its execution routes. `classify` = intent only.
- `walter-router dossier <task>` — the evidence behind a choice; `walter-router library` — the whole table (also the
  library page, behind Cloudflare Access).
- Text calls from modules or agents: walter-llm (127.0.0.1:8894, OpenAI-compatible, `model` = a router task, per-agent
  token). Hermes: plugin tools walter_route, walter_run, walter_generate, walter_feedback, walter_verdict, walter_plans.
- Media: `walter-router generate "<demande>" --task …` — costs money, only on request.

## How a choice is made (read the README for details)
- research/ fetches 16 sources by category (`walter-router research image|video|text|audio|memory|decision|prices|
  hosts|plans [--analyse]`); analysis/ ranks each task on its weighted boards among the models Walter can run; the
  owner's pins and roles always win; a better model is only PROPOSED on Telegram with buttons.
- Route order: subscription at its cost price while its weekly quota < 90 %, Kie if reliable and not much dearer,
  OpenRouter on the cheapest usable host the router imposes (provider order passed by walter-llm and by Hermes'
  provider_routing.models). Media: the same model on its next provider; another model only if declared.
- plan/: the owner's subscriptions (`walter-router plans list|set|retire`, never invent a plan or a price; billing
  mails become proposals; plan news become notices).

## Checks
- `walter-router health`, `status`, `review`, `alerts --all`; tests `cd /walter/router && venv/bin/python -m pytest -q`.
- Before calling a provider "cheapest", compare every provider and host at equal settings (`models.offers`,
  `models.best_endpoints`, subscription cost price in `models.latest_subscription_costs`).

## Pitfalls
1. Next.js flight data prefixes change (`c:` → `d:`): strip any single-letter prefix; reject a suspiciously tiny parse.
2. OpenRouter chat ids use dots (`openai/gpt-6-luna`), router ids dashes (`gpt-6-luna`); `pick` returns `openrouter_id`.
3. OpenRouter prices are $/token (× 1e6 for $/M); media prices come from each model page `displayPricing`.
4. Kie has no global discount; Kie Claude and Kie GPT degrade under load — the router demotes a route failing ≥ 50 % of
   its last runs.
5. A board that disappears is kept 21 days from its last snapshot and raises `board_down`.
6. Never run `bw unlock` yourself to reach provider keys: use `walter-secret` (shared Bitwarden session).

## Research reference — sources and pitfalls (still valid)

Kept from the August collectors: how each source must be read and checked. The live readers are in
`/walter/router/research/` (AA through the Next.js data of its pages, no API key needed for the router's own sources).

### AA API v2
- `GET https://artificialanalysis.ai/api/v2/data/llms/models` with `x-api-key` header
- Key in vault: `artificialanalysis/api_key` (NOT `artificial-analysis/api_key`, which returns 401)
- Data: intelligence_index, coding_index, math_index, GPQA, HLE, MMLU-Pro, IFBench, TAU2, TerminalBench, LiveCodeBench, AIME, SciCode, LCR, tokens/sec
- Source label: `aa_api_v2`

### AA cost per task
- Former method: Playwright on the Recharts "Intelligence vs Cost per Task" scatter of a model page (React fiber
  payloads of the `<circle>` elements); the router now reads the same values from the page's Next.js data
  (`intelligenceIndexCostPerTask.cost.total`).
- Only 26-30 models are on one chart: for a model not on it, read ITS OWN page.
- **RÈGLE ABSOLUE: always live. Never estimate cost_per_task.**

### Kie.ai Pricing (public-page evidence first)
- For exact per-model chat rates, fetch the public family page `https://kie.ai/<family-slug>` and parse its serialized `pricingDesc`.
- Accept a `verified_rates` record only when exact input and output rates are exposed. Preserve `unverified`, `not_found`, and `fetch_error` states.
- Parse Kie’s published official-price basis and explicit top-up bonus separately from AA’s reference token prices; never store one global discount.
- The marketplace API remains useful for discovery (`POST https://api.kie.ai/client/v1/model-pricing/page`), but its catalog fields alone are not evidence for the AA/Kie discount calculation.
- If the marketplace API is blocked by Cloudflare, use Playwright `page.evaluate(fetch(...))` for discovery; the public model-page check is a separate path.

### Provider arbitration (Kie)

Kie.ai does **not** have one reliable global discount versus AA, OpenRouter, or
an official vendor price. Route to Kie only after checking the exact model page
and recording the pricing basis:

- `verified_rates`: exact Kie input/output rates are published;
- `unverified`: the page exists but does not expose exact rates;
- `not_found` / `fetch_error`: no usable evidence.

Store two separate values:

1. **Kie nominal discount vs Kie-published official pricing**, using the
   published official input/output rates and a 3:1 input/output blend.
2. **Signed Kie-vs-AA reference delta**, using AA’s own input/output prices. A
   positive delta means Kie is more expensive than AA’s reference even when Kie
   advertises a discount against a different official basis.

AA reasoning variants may use a family Kie rate only when their slug starts with
the exact published base slug (`gpt-5-6-luna-high` → `gpt-5-6-luna`). Never copy
a discount from Luna to Sol, Claude, or another provider. Keep streaming,
latency, tool-use transport, and provider availability as separate routing
criteria.

The deterministic live contract and parser evidence are maintained in
`model-value-analysis/references/live-aa-kie-refresh.md`; dated percentages are
examples, not catalog truth.

### Research pitfalls (from the August collectors, still valid)

1. **Huge prices** — some models price >$10k/M: keep prices as double precision (models.offers), never a narrow NUMERIC.
2. **Model name matching between sources** — normalize: lowercase, strip all non-alnum, collapse spaces.
3. **Cost per task comes only from AA** — the router reads it from the Next.js data of an AA model page (`intelligenceIndexCostPerTask.cost.total`); never estimate it.
4. **OpenRouter pricing is $/token, not $/1M** — multiply by 1,000,000.
5. **Design Arena has two arenas** — `models` (code quality) and `agents` (agentic tasks), different categories. Full reverse-engineered API contract (endpoints, valid categories per arena, the 400 rate-limit trap, slug mapping to AA): `references/design-arena-api-contract.md`.
6. **Kie.ai pricing API blocked by Cloudflare** — use Playwright `page.evaluate(fetch(...))`, not curl.
7. **Database access** — `walter_router.store.db.connect()` (127.0.0.1:5433, ~/.pgpass); the 172.17.0.3 container address is retired.
8. **AA API v2 has TWO vault keys** — only `artificialanalysis/api_key` works. `artificial-analysis/api_key` returns 401.
9. **Codex catalogue changes** — what a ChatGPT-login Codex session serves changes (GPT-5.6 refused in August; GPT-6 / GPT-6.1 served and GPT-5.5 withdrawn on 2026-10-14): read the live catalogue (source `codex`), never a remembered list.
10. **AA API v2 intel ≠ Recharts intel** — the API v2 returns non-reasoning (base) variant scores (e.g. Luna = 26.6), while the Recharts graph shows reasoning variant scores (Luna max = 51.2). Gap is 15-25 points. Always use Recharts data for Pareto analysis. See `references/aa-api-vs-recharts-intel-discrepancy.md`.
11. **Kie.ai GPT tool-use requires Responses API format** — use `function_call`/`function_call_output` items, not Chat Completions `tool_calls` messages. Call-ID prefixes, accepted tool fields, latency, and cost are route/model-specific: verify them against the exact target before routing it, and do not generalize a successful Luna probe to Astra. See `references/kie-gpt-tool-use-responses-api.md`.
12. **Next.js RSC flight prefixes change between versions** — AA's inline flight payload prefix moved from `c:` to `d:` in Aug 2026, silently emptying the old parser. Never hardcode one letter: strip any single-letter prefix (`c:`, `d:`, ...) before `json.loads`. Models arrays may also move shape; match on a stable field (`headlineValue` + `costPerTask.total`), and reject a run whose universe is suspiciously tiny instead of trusting an empty parse.
13. **A named model missing from the primary Pareto table may be below the eligibility threshold** — look up the exact live slug in the snapshot before calling it dominated, then distinguish `below_threshold` from epsilon replacement, minimum-gain pruning, or marginal-return removal. If needed, recompute a lower-threshold diagnostic into `/tmp`; never alter the primary snapshot or infer absence from a partial chart.
14. **Verified Kie token rates are not automatically a Kie cost-per-task** — report Kie input/output/cache rates and their pricing basis separately, and only publish a Kie benchmark-task estimate when the AA token mix and computed task-cost field are present; otherwise a discount percentage is not comparable to AA Cost per Task.

## Analyser un cycle de 48 h et corriger les noms

- Utilise `walter-router` sur le PATH. Commence par `walter-router review`, `walter-router health` et `walter-router alias-list`. Consulte `walter-router dossier <tâche>` pour approfondir une anomalie.
- Lorsqu'une mission limite les corrections aux alias, ne lance aucun refresh, recalcul, changement de routage ou édition de fichier/base. Utilise exclusivement la commande validée pour écrire les rapprochements.
- Vérifie chaque rapprochement dans une source officielle : même modèle, version, taille et variante. Une ressemblance de nom constitue seulement un candidat ; conserve les cas ambigus sans correction.
- Consulte `walter-router alias-add --help`, puis ajoute chaque correspondance avec `walter-router alias-add <id_non_noté> <id_noté> --reason '<preuve et URL>'`. Le validateur exige un identifiant source existant, une cible ayant des scores et l'absence de chaîne ou conflit.
- Confirme les écritures avec `walter-router alias-list`, puis relis `walter-router review` et `walter-router health`. Le résumé du cycle peut conserver ses candidats et compteurs après les ajouts : distingue les alias persistés du résultat d'un recalcul, et ne lance pas ce dernier sans autorisation.
- Si `walter-router alerts` renvoie `[]`, consulte aussi `walter-router alerts --all` et examine les champs `kind` et `status` avant de conclure à l'absence d'alertes ouvertes. Pour les modèles non classés, filtre `kind == "unranked"` et `status == "open"`.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d'outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
- Dans le compte rendu, sépare les corrections confirmées, les anomalies restantes et les limites du résumé enregistré. N'affirme jamais qu'un rapport a été écrit sans confirmation de sa création.
