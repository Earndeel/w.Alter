---
name: walter-model-router
description: "Use when choosing which AI model or provider W.Alter should use for a task, checking live leaderboards, prices or the owner's AI subscriptions, explaining or tuning Walter Router (tasks, weights, preferences, alerts, library page), or analysing its 48 h cycle."
version: 4.0.0
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

## Analyser un cycle de 48 h et corriger les noms

- Utilise `walter-router` sur le PATH. Commence par `walter-router review`, `walter-router health` et `walter-router alias-list`. Consulte `walter-router dossier <tâche>` pour approfondir une anomalie.
- Lorsqu'une mission limite les corrections aux alias, ne lance aucun refresh, recalcul, changement de routage ou édition de fichier/base. Utilise exclusivement la commande validée pour écrire les rapprochements.
- Vérifie chaque rapprochement dans une source officielle : même modèle, version, taille et variante. Une ressemblance de nom constitue seulement un candidat ; conserve les cas ambigus sans correction.
- Consulte `walter-router alias-add --help`, puis ajoute chaque correspondance avec `walter-router alias-add <id_non_noté> <id_noté> --reason '<preuve et URL>'`. Le validateur exige un identifiant source existant, une cible ayant des scores et l'absence de chaîne ou conflit.
- Confirme les écritures avec `walter-router alias-list`, puis relis `walter-router review` et `walter-router health`. Le résumé du cycle peut conserver ses candidats et compteurs après les ajouts : distingue les alias persistés du résultat d'un recalcul, et ne lance pas ce dernier sans autorisation.
- Si `walter-router alerts` renvoie `[]`, consulte aussi `walter-router alerts --all` et examine les champs `kind` et `status` avant de conclure à l'absence d'alertes ouvertes. Pour les modèles non classés, filtre `kind == "unranked"` et `status == "open"`.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d'outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
- Dans le compte rendu, sépare les corrections confirmées, les anomalies restantes et les limites du résumé enregistré. N'affirme jamais qu'un rapport a été écrit sans confirmation de sa création.
