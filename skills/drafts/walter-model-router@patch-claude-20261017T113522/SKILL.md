---
name: walter-model-router
description: "Use when choosing which AI model / provider W.Alter should use for a task, checking live leaderboards or prices, explaining or tuning Walter Router (tasks, weights, preferences, alerts, library page), or analysing its 48 h cycle."
version: 3.0.0
author: W.Alter
metadata:
  hermes:
    tags: [router, model-selection, pricing, benchmarks, postgresql, openrouter, kie, codex]
    related_skills: [aa-pareto-model-optimizer, kie-ai-api-direct, model-router-intelligence-loop]
---

# Walter Router

Code `/opt/walter-router` (git). Data = Postgres `hindsight-pg` 127.0.0.1:5433, db `hindsight`, **schema `models`**
(password only in `/root/.pgpass`; every table/view has a COMMENT). Docs: `README.md`, `docs/DESIGN.md` (design),
`docs/DATA.md` (every source, table, view + example SQL), `docs/TIERS.md` (text tiers method).
The old store (schema `walter_router`, 172.17.0.3, fixed weight vectors) is retired: never use it.

## Ask the router (never hardcode a model)
- `bin/walter-router pick <task> [--level L1|L2|L3] [--role R] [--require unrestricted|open_weights]` — the model,
  provider, price, fallbacks for a task. `bin/walter-router tasks` lists the 33 task keys.
- `bin/walter-router route "<demande en français>"` — Jev (decision model, OpenRouter Decisions API, ~0.5 s,
  ~0.00007 $) classifies task + video role + level, then the decision with execution routes.
- `bin/walter-router dossier <task>` — the full evidence the choice is made from.
- `bin/walter-router library` (CLI table) = https://library.walter-ai.cloud (English, /fr/ French; Cloudflare Access).
- Modules and agents call text models through **walter-llm** (127.0.0.1:8894, OpenAI-compatible, `model` = task or
  `general/L2`, per-agent token, keys stay in the gateway). Hermes: plugin `walter-router` (`walter_route`,
  `walter_run`, `walter_generate`, `walter_feedback`, `walter_verdict`).
- Media: `bin/walter-router generate "<demande>" --task text_to_video|text_to_image|tts|music…` (costs money: only on request).

## How a choice is made
1. 48 h cycle (`walter-router-refresh.timer`, `bin/walter-router-cycle`; manual button on the library page) collects
   sources into `models.snapshots`: AA (intelligence, multimodal, Decision Index, STT), Arena.ai, Design Arena,
   BridgeBench (FlareSolverr), Agentset, MTEB, prices from OpenRouter, Kie, Codex, Hermes providers, declared offers.
2. Names are unified (`models.canonical` / `aliases`), scores always "higher = better".
3. `scoring.composite`: each board of the task (`models.task_benchmarks.weight`) on 0–100, weighted by reliability;
   `select` ranks **callable** models only; text tiers L1/L2/L3 from the AA Pareto frontier at real provider cost.
4. Monsieur's choices win: `models.preferences` (pins, video roles, objective) from `config/knowledge.json`
   (`bin/walter-router declare`). Routes: subscription (Codex) → Kie (≤ 1.25 × OpenRouter) → OpenRouter; a provider
   × model failing ≥ 50 % of ≥ 3 runs in 14 days (`models.exec_log`) goes last.
5. Changes are only **proposed**: one Telegram message per news with buttons (« ✅ Changer » / « ✖️ Garder l'actuel »);
   a challenger must beat the current model on the task's global score. Never switch a model without his button.

## Checks
- `bin/walter-router health` (exit 1 = not fed / not usable; `sources_age_h`, provider probes, OpenRouter credit).
- `bin/walter-router status`, `alerts`, `review` (deterministic digest of the last cycle).
- Tests: `cd /opt/walter-router && venv/bin/python -m pytest -q`.
- Before claiming "cheapest", compare every provider's real price at equal settings (`models.offers`, latest snapshots).

## Pitfalls (still true)
1. Next.js RSC flight prefixes change (`c:` → `d:`): strip any single-letter prefix; reject a suspiciously tiny parse.
2. OpenRouter chat ids use dots (`openai/gpt-6-luna`), router model_ids use dashes (`gpt-6-luna`); `pick` returns
   `openrouter_id` where needed.
3. OpenRouter prices are $/token: × 1e6 for $/M. Media prices come from each model page `displayPricing`
   (÷ `displayMultiplier`).
4. Kie has no global discount: compare the exact offer; Kie Claude routes are often degraded (preflight in walter_run),
   Kie GPT rate-limits under batch load (« Too many pending requests »).
5. AA API v2 intelligence = base variant; the router uses the chart data per reasoning level.
6. A board that disappears from a source is kept 21 days from its last snapshot and raises `board_down`.

## Analyser un cycle déterministe et vérifier les alias

- Respecte le périmètre autorisé : si seules les corrections de noms sont permises, utilise uniquement `alias-add` pour les mutations. Ne modifie ni la base, ni la configuration, ni les fichiers ; ne crée pas de rapport sur disque sans autorisation.
- Lis `/opt/walter-router/bin/walter-router review` et `/opt/walter-router/bin/walter-router health`, puis `/opt/walter-router/docs/TIERS.md`, `/opt/walter-router/config/knowledge.json` et `/opt/walter-router/walter_router/aliases.json`. Consulte `/opt/walter-router/bin/walter-router dossier <tâche>` pour approfondir une anomalie.
- Pour chaque candidat de rapprochement, vérifie dans une source officielle que les deux noms désignent exactement la même version du modèle. Un suffixe descriptif supposé ou une proximité de noms ne suffit pas. En cas de doute, conserve le candidat sans ajouter d'alias.
- Vérifie la syntaxe avec `/opt/walter-router/bin/walter-router alias-add --help`, puis applique `/opt/walter-router/bin/walter-router alias-add <nom_source> <model_id_canonique> --reason '<preuve et URL officielle>'` uniquement lorsque l'identité est établie.
- Confirme la persistance avec `/opt/walter-router/bin/walter-router alias-list`, puis relis `/opt/walter-router/bin/walter-router review`. Distingue la présence de l'alias de son effet sur les données du cycle : si le résumé conserve le candidat, rapporte cette observation. Ne soustrais jamais manuellement le nombre d'alias ajoutés au nombre de candidats et ne lance pas de recalcul hors périmètre.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d'outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
