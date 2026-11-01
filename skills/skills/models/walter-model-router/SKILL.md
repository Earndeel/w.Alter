---
name: walter-model-router
description: "Use when choosing which AI model or provider W.Alter should use for a task, checking live leaderboards, prices or the owner's AI subscriptions, explaining or tuning Walter Router (tasks, weights, preferences, alerts, library page), or analysing its 48 h cycle."
version: 4.3.0
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
`docs/README.md` (documentation index), `docs/reference/DATABASE.md` (all SQL fields), `docs/DATA.md` (provenance), `docs/TIERS.md` (text tiers), `docs/HISTORY.md` (dated decisions).
The old store (schema `walter_router`, fixed weight vectors, router_matrix.json) is retired: never use it.

## Ask the router — never hardcode a model
- `walter-router pick <task> [--level L1|L2|L3] [--role R] [--require unrestricted|open_weights|video_input]` — model,
  provider order with prices, fallbacks (`video_input`: e.g. `pick vision --require video_input` to analyse a video;
  there is no video-analysis task, no satisfying benchmark).
  `walter-router tasks` lists the task keys (42, incl. medical, legal, engineering, finance, strategy, cybersecurity,
  science, long_context, writing, music, vision, video roles…).
- `walter-router route "<demande>" [--context "<what the conversation was about>"]` — the decision model (d1-ultra,
  then Mercury Decide free, then Clef) classifies the request (with `--context` when it depends on earlier turns,
  e.g. « fais la suite »), then the decision with its execution routes and each route's price per million tokens.
  Not called when `--task` (and `--level` for general) are given. `classify` = intent only.
- `walter-router dossier <task>` — the evidence behind a choice; `walter-router library` — the whole table (also the
  library page, behind Cloudflare Access).
- Text calls from modules or agents: walter-llm (127.0.0.1:8894, OpenAI-compatible, `model` = a router task, per-agent
  token). Agents: the same tools in every runtime — walter_route, walter_run (text sub-agent or media generation),
  walter_decide (the decision model for any quick choice), walter_plans (Hermes
  plugin; walter MCP for Claude Code / Codex / DSH), plus walter_verdict / walter_feedback in Hermes. walter_route and
  walter_run take `conversation`, the same line as `--context`. What agents can ask for (levels, specialities,
  generation, constraints) is `walter-router brief`, generated from the database and given to every agent (Hermes
  prompt section, MCP instructions, Codex / DSH profiles): edit tasks/roles, never the prompt.
- Doing the job: `walter-router run` (JSON spec on stdin: goal, context, task, level, or model + provider when the
  owner names them — run exactly as named or refused, never substituted; media: role, image_urls…). Media costs
  money, only on request; `walter-router generate "<demande>" --task …` remains the direct media command.
- `walter-router ask "<question>" --option a="…" --option b="…"` — the decision model for any choice.

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

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/research-sources-and-pitfalls.md` — Research reference: every leaderboard / price source and its pitfalls (still valid).
- `references/operations-48h-cycle.md` — Analysing, verifying and reviewing a 48-hour refresh cycle, fixing names with alias-only authority, handling an AA redesign or Intelligence Index version change.
- `references/providers-and-transport.md` — Native text execution and provider failover, the Claude subscription transport, diagnosing a Kie outage without downgrading its media, adding a Bitwarden-backed provider.
- `references/documentation-and-orchestrator.md` — Which documentation is maintained, and the orchestrator note (2026-10-23).

