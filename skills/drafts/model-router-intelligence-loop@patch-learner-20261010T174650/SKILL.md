---
name: model-router-intelligence-loop
description: "Build and operate an auto-updating model-router intelligence system for W.Alter: benchmark research, DesignArena/API ingestion, X/Reddit signal collection, free-offer scanning, test harnesses, decision scoring, and safe integration proposals. See references/designarena-and-research-ingestion.md for the no-paid-tests enrichment workflow and references/designarena-code-preference-vs-price.md for the Design Arena category/view segmentation pitfall."
triggers:
  - model router recommendations
  - keep router up to date
  - compare models by task
  - benchmark and pricing watch
  - free model credits or provider offers
  - X Reddit model intelligence
  - routing matrix by usage
---

# Model Router Intelligence Loop

> Reference: `references/composite-loop-aa-designarena-social-2026-06.md` captures the current composite-loop contract: manual-only execution; Artificial Analysis as primary cost/intelligence source; Design Arena as segmented specialized signal; X/Reddit as sourced community evidence only.

Use this skill when Monsieur asks to keep W.Alter's model routing current, choose models per task, monitor model offers/free credits, or build recurring research/test/integration loops for LLM providers.

## Core principle

Do **not** treat model choice as a static benchmark table. Maintain a living router decision system that combines:

- authoritative benchmarks,
- value-density metrics such as Artificial Analysis `Cost per Intelligence Index Task`,
- real provider pricing and availability,
- real task-level tests,
- latency/context/tool-use constraints,
- qualitative community/provider signals,
- safe config integration with dry-runs.

For AA-driven W.Alter/Hermes routing, `Cost per Intelligence Index Task` is mandatory: raw Intelligence Index and token price alone are insufficient for route economics. See `references/aa-cost-per-intelligence-task-2026-06.md`; reusable scraper: `scripts/scrape_aa_cost_per_task.py`.

Router changes should be proposed as a staged diff by default. Do not modify production router configuration automatically unless Monsieur explicitly approves or a prior policy marks the change as auto-safe.

### Architecture before automation

Do **not** create recurring cronjobs before the loop architecture is explicit. For this class of system, first produce:

1. project summary and goals;
2. loop definitions with inputs/outputs;
3. shared data schema/contracts between loops;
4. dry-run plan and budget guardrails;
5. dry-run execution with real sample output;
6. only then recurring jobs or router integration.

If Monsieur says the loops are unclear, stop automation work and formalize the system before adding more scheduled jobs. Oui, même si the cron button is sitting there looking innocent.

## Recommended loop architecture

Run the system as four integrated loops. Each loop should produce structured output that downstream loops can consume.

### 1. Signal Collector

Frequency: daily or every 2-3 days.

Collect:

1. **Benchmarks**
   - Artificial Analysis: Intelligence Index, Coding Index, Agentic/tool-use, long-context, speed, cost per task, input/output/blended price.
   - Design Arena: Elo/rank for frontend, visual design, coding UI output.
   - Aider, SWE-bench, Terminal-Bench, LiveCodeBench, GPQA, HLE, MMLU-Pro, long-context evaluations when available.
2. **Provider catalogs**
   - OpenRouter model catalog.
   - Direct provider docs and announcements.
   - Input/output/cache pricing, context window, rate limits, region limits, moderation constraints, API compatibility.
3. **Community signal**
   - X/Twitter: launch threads, engineer benchmarks, provider announcements, complaints, hidden pricing changes.
   - Reddit: especially r/LocalLLaMA, r/ClaudeAI, r/OpenAI, r/MachineLearning, r/LocalLLM, r/ArtificialInteligence, provider-specific communities.
   - Distinguish hype from verified hands-on results. Require links, screenshots, reproducible prompts, or multiple independent mentions before promoting a model.
4. **Offers and free capacity**
   - Free credits, trial tokens, temporary free routes, beta access, limited-time launch offers, free OpenRouter routes, provider hackathon credits.
   - Record expiry, quota, eligibility, account requirements, payment-card requirements, and whether usage risks surprise billing.

Output schema should include: `model_id`, `provider`, `source`, `signal_type`, `task_relevance`, `price`, `context`, `latency`, `quality_claim`, `confidence`, `expiry`, `risk_notes`, `url`.

### 2. Test Harness

Frequency: 2x/week or triggered when a promising model/offer appears.

Test candidates per task class:

- `chat_general`
- `reasoning_deep`
- `coding_backend`
- `frontend_design`
- `extraction_json`
- `long_context`
- `agent_tool_calling`
- `cheap_background`
- `multimodal_image_video` when relevant

Use a small stable benchmark set owned by W.Alter: 3-5 prompts per task class, expected-output rubrics, JSON validity checks, latency measurement, token accounting, and cost estimation.

Cost guardrails:

- Prefer free routes, free credits, and promotional offers.
- If account balance/credits are uncertain, suspend paid execution tests and continue metadata/benchmark/community ingestion only.
- **Do the research immediately after suspension.** When Monsieur says to suspend tests but continue filling the DB, do not stop at schema/plumbing or token benchmark ingestion; run the non-paid research pass in the same turn: web search, Design Arena/API scraping, provider catalogs, X/Reddit/community queries, then persist evidence rows with source URLs. Treat "tests suspended" as a branch, not a pause.
- Do not run paid tests above a small explicit budget without approval.
- If credentials/endpoints are missing, credits are exhausted, or the provider returns billing/credit errors, emit a proposed test matrix instead of fabricating results.

### 3. Decision Engine

Frequency: after test harness, usually 2x/week.

Score each model per task using weighted dimensions:

- quality/benchmark fit,
- real test performance,
- cost per task using expected input/output ratios,
- speed and throughput,
- context window,
- structured output reliability,
- tool-calling/agent reliability,
- provider reliability/rate limits,
- availability and offer/free-credit status,
- community risk signals.

Recommended output:

- `promote`: models worth moving up in the router.
- `demote`: models losing value or reliability.
- `test_more`: promising but insufficient evidence.
- `avoid`: risky, unavailable, misleading pricing, bad reports.
- `free_credit_actions`: offers Monsieur could exploit safely.
- `router_matrix`: best/default/fallback/cheap model per task.

Always explain tradeoffs in cost-benefit terms. Monsieur prefers pragmatic percentage impact over micro-optimizing crumbs.

### 4. Integration Proposal

Frequency: after decision engine.

Prepare a staged proposal, not an unapproved production edit:

1. Identify the active Hermes/W.Alter router config and current routes.
2. Produce a pseudo-diff or patch candidate.
3. Include rollback notes.
4. Mark each change with one of:
   - `APPROVAL_REQUIRED`
   - `AUTO_SAFE_CANDIDATE`
   - `DO_NOT_APPLY`
5. Only auto-apply if explicitly allowed, free/no billing risk, tested, reversible, and no secret/provider change is involved.

## Model Value, Benchmarks, and Provider Authenticity Branches

This umbrella absorbs the former `llm-model-value-analysis`, `public-model-benchmark-checks`, and `llm-provider-fingerprinting` skills. They are all branches of the same class-level activity: deciding whether a model/provider route is worth using in the router.

### Value analysis
- Combine benchmark quality, real usage cost, speed, context window, and workload-specific input/output ratios.
- Report cost per useful task, not only token price or leaderboard rank.

### Public benchmark checks
- Use quick public-source verification for single-model questions, then promote durable findings into the router evidence schema.
- Label source freshness and benchmark category; do not mix generic intelligence, coding, agentic, long-context, and design/UI signals.

### Provider fingerprinting
- Before routing a suspicious reseller, verify endpoint anatomy, response IDs, model listing, tool-use format, and behavioral fingerprints.
- Treat provider route authenticity as a router dimension: a good underlying model through a contaminated proxy may still be a bad route.
- Keep detailed fingerprints in `references/` and summarize only the decision-relevant evidence in router outputs.

## Source handling pitfalls

- Do not create cronjobs first. Define loops, schemas, contracts, dry-run tests, and integration gates before scheduling recurring automation.
- Use the existing PostgreSQL instance for persistent model-router intelligence; prefer a dedicated `model_router` schema over a new PG server.
- Treat community information qualitatively: record field reports, recurring claims, reported strengths/failures, reliability notes, pricing complaints, migration signals, hype/controversy, evidence quality, and source reputation. Do not collapse it into a naked `community_score`.
- For every candidate endpoint, test actual hosted behavior before routing: JSON/content shape, tool/format compliance, latency, usage/cost accounting, and null/empty content failure modes.
- Maintain endpoint-specific decisions. A model can benchmark well but fail through one provider route.
- Promotional free access is valuable but volatile. Always capture expiry and billing risk.
- Do not silently substitute model IDs. Load `model-id-lookup` before using exact model IDs.
- Do not recommend a paid provider change without price verification.
- Do not equate open-weight quality with hosted-route quality; providers can differ in quantization, context, throughput, and system prompt behavior.
- Do not update the router based only on launch hype. Require either benchmark evidence, community convergence, or W.Alter test results.

## Useful companion skills

- `model-benchmark-comparison` for benchmark normalization.
- `free-model-offer-watchdog` for offers/free-tier monitoring.
- `x-research-pipeline` for X/Twitter collection.
- `universal-web-extraction-router` for structured web research and known-URL extraction.
- `model-id-lookup` before exact model usage.
- `hermes-agent` for Hermes cron/config mechanics. Treat Hermes docs as source of truth when configuring jobs.

## Design Arena / protected benchmark ingestion

- **No-auth REST contract (Aug 2026):** Design Arena serves plain REST
  endpoints — `POST /api/leaderboard` (Elo per category, needs
  `variationName:"public"`), `GET /api/registry` (full model catalog, ~460
  models). Full endpoint list, valid arena/category keys, response shapes,
  the transient-400 rate-limit quirk, and the DA↔AA slug join recipe
  (dots→hyphens + tier-suffix stripping): `references/designarena-api.md`.
- For Design Arena and other benchmark sources with Cloudflare/anti-bot behavior, do not stop at direct HTTP `403`; escalate through the browsing hierarchy: cheap HTTP → Scrapling if available → Camoufox Max.
- For Design Arena's `https://www.designarena.ai/api/leaderboard/judge-scores`, Camoufox may return the JSON successfully even when Python/urllib is blocked. After navigation, extract content through `/tab/evaluate` with `document.body.innerText`; `/tab/navigate` can succeed without returning text.
- During analysis, report corpus coverage/freshness and source-specific rankings first. If `model_router.router_scores` is empty, explicitly say the router has not produced final decisions yet; analyze upstream benchmarks/pricing/evidence only.
- **Never generalize “Design Arena” across category/view combinations.** Always segment by `category` and `view` before ranking: e.g. `design_quality` + `judge_score_*` is not the same signal as `Code → Preference vs Price`. If Monsieur references a specific Design Arena UI view, verify that the local DB contains that exact category/view; if not, say the DB is incomplete for that view and fetch/ingest that view before analyzing.
- For Code routing, `Preference vs Price` is a separate value signal and can contradict raw judge-score/design-quality rankings. Report both only if clearly labeled; otherwise analyze the requested view alone.

## Router scoring: per-tier normalization (do not global-score)

Ranking every model on one global score is wrong: a $2.3 model crushes a
$0.03 model on raw quality dimensions, so the expensive model wins every
task type. The correct router shape (implemented in
`aa-pareto-model-optimizer/scripts/router.py`, daily cron artifact
`~/.hermes/cache/aa-pareto/router_matrix.json` + `.csv`):

- Resolve need → task type by keyword triggers (13 types: agentic, coding,
  frontend, 3d, dataviz, gamedev, extraction, reasoning, compression,
  tool_calling, slides, logo_graphic, agent_build).
- Rank models **inside cost tiers** (budget ≤$0.05/task, standard
  $0.05–0.20, premium >$0.20) with min-max normalization computed per tier.
- Normalize cost in **log space** so outliers do not flatten the cost
  dimension; the design dimension comes from Design Arena Elo mapped to the
  task's design categories (not from AA indexes).
- Tiered AA slugs (`gpt-5-6-luna-high`) inherit the base model's DA profile.

This matrix is the cron-fresh decision surface; the PG `walter_router`
`router_scores` table may lag it (it sat empty since Jul 2026) — trust
`generated_at`, not the table. The legacy PG task_types had
`weight_design_arena = 0.0` everywhere; the fresh router.py carries real
design weights.

## References

- `references/absorbed-source-routing.md` — mandatory routing to exact source procedures when consolidated guidance lacks operational detail.

- `references/session-2026-06-router-loop.md` — conversation-derived architecture and initial loop design.
- `references/designarena-camoufox-router-ingestion-2026-06.md` — session-tested Design Arena ingestion fallback via Camoufox and analysis caveats.

## Analyser un cycle déterministe avec corrections limitées aux alias

Quand la collecte et le calcul sont déjà terminés et que seules les corrections de noms sont autorisées :

1. Lire l’état avec les chemins absolus :
   ```bash
   /opt/walter-router/bin/walter-router review
   /opt/walter-router/bin/walter-router health
   /opt/walter-router/bin/walter-router alias-list
   ```
   Le binaire peut être absent du PATH. Juger le succès d’après le code de sortie et le contenu : une enveloppe d’outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
2. Lire `/opt/walter-router/docs/TIERS.md`, `/opt/walter-router/config/knowledge.json` et `/opt/walter-router/walter_router/aliases.json`. Examiner au besoin une tâche avec `/opt/walter-router/bin/walter-router dossier <tâche>`.
3. Vérifier chaque rapprochement sur une source officielle accessible. Exiger la même génération, variante et modalité ; une ressemblance de nom ne suffit pas. Une recherche vide ou un échec d’extraction ne prouve aucune équivalence. Si le backend indique qu’il ne prend pas en charge l’extraction, ne pas répéter cette opération ; utiliser une méthode de lecture autorisée ou laisser le candidat non résolu.
4. Consulter la syntaxe avant toute correction :
   ```bash
   /opt/walter-router/bin/walter-router alias-add --help
   ```
   Ajouter seulement les équivalences étayées :
   ```bash
   /opt/walter-router/bin/walter-router alias-add <clé-source> <model_id-canonique> --reason '<preuve de même identité et URL officielle>'
   ```
5. Relire `alias-list` pour confirmer la paire enregistrée. Cette vérification confirme l’écriture, pas l’identité des modèles.
6. Respecter strictement le périmètre de mutation : ne pas modifier directement la base, la configuration ou les fichiers du projet, ni lancer une collecte ou un recalcul. Sans autorisation distincte de produire un fichier de rapport, rendre l’analyse dans la réponse. Distinguer les constats du cycle, les alias effectivement corrigés et les candidats encore incertains.
