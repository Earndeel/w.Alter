---
name: walter-model-router
description: "W.Alter model routing intelligence — PostgreSQL database of all models across providers (OpenRouter, Kie.ai, Google AI Studio), scraped benchmarks (AA, Design Arena), live pricing, cost-per-task, and pre-computed router scores per task type. Use when comparing models, optimizing routing, adding providers, or refreshing model data."
version: 2.2.0
author: W.Alter
metadata:
  hermes:
    tags: [router, model-selection, pricing, benchmarks, postgresql, openrouter, kie, scraping]
    related_skills: [model-benchmark-comparison, aa-intel-vs-cost-scraper, kie-gemini-mastery, hermes-model-picker]
---

# W.Alter Model Router

Production model selection intelligence for W.Alter's agent loop. PostgreSQL-backed, multi-provider, with automated scraping and change detection.

## Architecture

```
Scrapers (cron + triggers)
  ├── OpenRouter API → models, pricing, AA indices, Design Arena
  ├── AA API v2 → GPQA, HLE, TAU2, TerminalBench, etc.
  ├── AA DOM (Playwright) → cost_per_task (Recharts)
  └── Kie.ai API → model list + pricing (via /client/v1/model-pricing/page)

                       ↓
              PostgreSQL (walter_router)
                       ↓
              Router scores (pre-computed by task type)
                       ↓
              W.Alter agent loop ("best model for this task?")
```

## Database

Schema: `walter_router` in PostgreSQL (`hindsight` DB at `172.17.0.3:5432`).

9 tables: `models`, `providers`, `pricing`, `benchmarks`, `design_arena`, `task_types`, `router_scores`, `change_log`, `scrape_runs`.

## Scrapers

### 1. OpenRouter (daily — fast, no auth)
- `GET https://openrouter.ai/api/v1/models`
- Data: name, creator, pricing, `benchmarks.artificial_analysis` (intel/coding/agentic), `benchmarks.design_arena` (Elo by category)
- 343 models, ~10s. Connection: direct `psycopg2`.

### 2. AA API v2 (weekly)
- `GET https://artificialanalysis.ai/api/v2/data/llms/models` with `x-api-key` header
- Key in vault: `artificialanalysis/api_key` (prefix `aa_mgBk...` — NOT `artificial-analysis/api_key` which returns 401)
- Data: intelligence_index, coding_index, math_index, GPQA, HLE, MMLU-Pro, IFBench, TAU2, TerminalBench, LiveCodeBench, AIME, SciCode, LCR, tokens/sec
- Source label: `aa_api_v2`

### 3. AA DOM — Cost per Task (weekly, Playwright)
- Scrapes Recharts "Intelligence vs Cost per Task" scatter from any model page
- Playwright → `page.evaluate()` → React fiber payloads from `<circle>` elements
- 26-30 models have this metric. For models NOT on the chart, scrape THEIR OWN page.
- **RÈGLE ABSOLUE: always live. Never estimate cost_per_task.**

### 4. Kie.ai Pricing (weekly, public-page evidence first)
- For exact per-model chat rates, fetch the public family page `https://kie.ai/<family-slug>` and parse its serialized `pricingDesc`.
- Accept a `verified_rates` record only when exact input and output rates are exposed. Preserve `unverified`, `not_found`, and `fetch_error` states.
- Parse Kie’s published official-price basis and explicit top-up bonus separately from AA’s reference token prices; never store one global discount.
- The marketplace API remains useful for discovery (`POST https://api.kie.ai/client/v1/model-pricing/page`), but its catalog fields alone are not evidence for the AA/Kie discount calculation.
- If the marketplace API is blocked by Cloudflare, use Playwright `page.evaluate(fetch(...))` for discovery; the public model-page check is a separate path.

## Router Score Computation

> **Routing philosophy (Monsieur, Aug 2026):** the router must NOT be a
> multi-weight score mash. It is: (1) three intelligence levels read from the
> AA Pareto upgrade ladder (L1 = value_anchor, L2 = median marginal_upgrade —
> the sweet spot, NOT the last step before the ceiling, L3 = quality_ceiling);
> (2) default route = the required level's model (cheapest sufficient);
> (3) conditional escalation ONLY when the specific action needs a domain
> skill (frontend, 3D, gamedev, dataviz, SVG, full-stack build, ...) — then
> take the BEST model of that domain per Design Arena human preference
> (per-category Elo, never the Overall scale), showing the cost delta, plus a
> compromise: best design model still within the default level's budget.
> Never score all models on one global min-max scale: the expensive model wins
> every task because the cost dimension gets crushed by outliers. Derive
> levels from the Pareto ladder, or rank within budget tiers, instead.

> Live decision surface: the deterministic per-budget-tier matrix is computed
> daily from fresh AA + Design Arena by
> `aa-pareto-model-optimizer/scripts/router.py` ->
> `~/.hermes/cache/aa-pareto/router_matrix.json` (+ `.csv`). That matrix is the
> cron-fresh answer to "best model for this need"; the PG store below keeps the
> historical/priced/provider-specific layer. When the PG router scores diverge
> from the fresh matrix, trust the fresh matrix (check `generated_at`).

8 task types with weight vectors:

| Task | Intel | Coding | Agentic | Cost | Speed |
|------|-------|--------|---------|------|-------|
| agentic | 0.25 | 0.15 | 0.35 | 0.15 | 0.10 |
| coding | 0.15 | 0.45 | 0.10 | 0.15 | 0.15 |
| extraction | 0.10 | 0.05 | 0.25 | 0.40 | 0.20 |
| reasoning | 0.40 | 0.10 | 0.10 | 0.25 | 0.15 |
| compression | 0.20 | 0.05 | 0.05 | 0.40 | 0.30 |
| tool_calling | 0.10 | 0.10 | 0.30 | 0.30 | 0.20 |
| frontend | 0.15 | 0.20 | 0.10 | 0.25 | 0.10 |
| slides | 0.15 | 0.20 | 0.15 | 0.25 | 0.10 |

Tiers: premium (>$0.20/task), standard ($0.05-0.20), budget (<$0.05).

## Provider Arbitration

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

**Codex ChatGPT availability:** GPT-5.6 Luna, Sol, and Terra return "not supported when using Codex with a ChatGPT account." Only GPT-5.5 and below are available on Codex/ChatGPT. Route GPT-5.6 through a provider whose live availability and pricing have been verified.

**OpenRouter model ID format:** Uses dots, not dashes — `openai/gpt-5.6-luna` (NOT `openai/gpt-5-6-luna`). The `/models` list returns dashes but the chat completions endpoint rejects them.

## Pitfalls

1. **NUMERIC(10,6) overflows** — some models price >$10k/M. Schema uses NUMERIC(14,6).
2. **Model name matching between sources** — normalize: lowercase, strip all non-alnum, collapse spaces.
3. **Cost per task is ONLY in AA DOM Recharts** — never estimate it. Scrape the model's own page.
4. **OpenRouter pricing is $/token, not $/1M** — multiply by 1,000,000.
5. **Design Arena has two arenas** — `models` (code quality) and `agents` (agentic tasks), different categories. Full reverse-engineered API contract (endpoints, valid categories per arena, the 400 rate-limit trap, slug mapping to AA): `references/design-arena-api-contract.md`.
6. **Kie.ai pricing API blocked by Cloudflare** — use Playwright `page.evaluate(fetch(...))`, not curl.
7. **`docker exec psql` is too slow** — use `psycopg2` with direct connection to 172.17.0.3.
8. **AA API v2 has TWO vault keys** — only `artificialanalysis/api_key` works. `artificial-analysis/api_key` returns 401.
9. **GPT-5.6 NOT on Codex ChatGPT** — the Codex Responses API on chatgpt.com blocks GPT-5.6 Luna, Sol, and Terra ("not supported when using Codex with a ChatGPT account"). Only GPT-5.5 and below work. For GPT-5.6, route to a provider whose live availability and per-model pricing have been verified; do not assume Kie’s discount.
10. **AA API v2 intel ≠ Recharts intel** — the API v2 returns non-reasoning (base) variant scores (e.g. Luna = 26.6), while the Recharts graph shows reasoning variant scores (Luna max = 51.2). Gap is 15-25 points. Always use Recharts data for Pareto analysis. See `references/aa-api-vs-recharts-intel-discrepancy.md`.
11. **Kie.ai GPT tool-use requires Responses API format** — use `function_call`/`function_call_output` items, not Chat Completions `tool_calls` messages. Call-ID prefixes, accepted tool fields, latency, and cost are route/model-specific: verify them against the exact target before routing it, and do not generalize a successful Luna probe to Astra. See `references/kie-gpt-tool-use-responses-api.md`.
12. **Next.js RSC flight prefixes change between versions** — AA's inline flight payload prefix moved from `c:` to `d:` in Aug 2026, silently emptying the old parser. Never hardcode one letter: strip any single-letter prefix (`c:`, `d:`, ...) before `json.loads`. Models arrays may also move shape; match on a stable field (`headlineValue` + `costPerTask.total`), and reject a run whose universe is suspiciously tiny instead of trusting an empty parse.
13. **A named model missing from the primary Pareto table may be below the eligibility threshold** — look up the exact live slug in the snapshot before calling it dominated, then distinguish `below_threshold` from epsilon replacement, minimum-gain pruning, or marginal-return removal. If needed, recompute a lower-threshold diagnostic into `/tmp`; never alter the primary snapshot or infer absence from a partial chart.
14. **Verified Kie token rates are not automatically a Kie cost-per-task** — report Kie input/output/cache rates and their pricing basis separately, and only publish a Kie benchmark-task estimate when the AA token mix and computed task-cost field are present; otherwise a discount percentage is not comparable to AA Cost per Task.

## Analyser un cycle déterministe et vérifier les alias

- Respecte le périmètre autorisé : si seules les corrections de noms sont permises, utilise uniquement `alias-add` pour les mutations. Ne modifie ni la base, ni la configuration, ni les fichiers ; ne crée pas de rapport sur disque sans autorisation.
- Lis `/opt/walter-router/bin/walter-router review` et `/opt/walter-router/bin/walter-router health`, puis `/opt/walter-router/docs/TIERS.md`, `/opt/walter-router/config/knowledge.json` et `/opt/walter-router/walter_router/aliases.json`. Consulte `/opt/walter-router/bin/walter-router dossier <tâche>` pour approfondir une anomalie.
- Pour chaque candidat de rapprochement, vérifie dans une source officielle que les deux noms désignent exactement la même version du modèle. Un suffixe descriptif supposé ou une proximité de noms ne suffit pas. En cas de doute, conserve le candidat sans ajouter d’alias.
- Vérifie la syntaxe avec `/opt/walter-router/bin/walter-router alias-add --help`, puis applique `/opt/walter-router/bin/walter-router alias-add <nom_source> <model_id_canonique> --reason '<preuve et URL officielle>'` uniquement lorsque l’identité est établie.
- Confirme la persistance avec `/opt/walter-router/bin/walter-router alias-list`, puis relis `/opt/walter-router/bin/walter-router review`. Distingue la présence de l’alias de son effet sur les données du cycle : si le résumé conserve le candidat, rapporte cette observation. Ne soustrais jamais manuellement le nombre d’alias ajoutés au nombre de candidats et ne lance pas de recalcul hors périmètre.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d’outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
