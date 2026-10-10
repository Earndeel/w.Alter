# walter-skills

W.Alter's procedural memory: skills and workflows, owned by Walter, independent of any agent runtime. Hermes, Claude
Code, Codex and DSH are adapters. Plan: `/root/.hermes/docs/walter-memory/PLAN.md` (P10). Decisions and measurements:
`DECISIONS.md` (2026-10-09/10). Operations: `RUNBOOK.md` § walter-skills.

## Shape: one core, thin ports, one loop

```
                 ┌──────────────────────────── core: walter_skills ────────────────────────────┐
  content  ───▶  │ store       git: skills/ archive/ drafts/ — the only source of content        │
                 │ registry    Postgres skills.*: cards, labels, rankers, state, journals, ledger │
                 │ ranker      Corpus (what is searchable) | Ranker (what was learned)            │
                 │ retrieval   live engine + local snapshot (boots without Postgres)             │
                 │ policy      THE place deciding what an agent sees (tiers 0/1/2, errors)        │
                 │ learning    implicit labels → judge sample → drafts from sessions → train → promote │
                 │ evaluate    the single evaluator (nightly promotion, curation checks, bench)   │
                 │ curation    operators: drafts, archive, links, merge, split, workflow, organize │
                 │ postes      editor / indexer / judge: ordered routes with fallback             │
                 │ door        the single way content enters (judged before it goes live)         │
                 └───────────────────────────────────────────────────────────────────────────────┘
  ports (no rules): api.py (HTTP :8891) · client.py (stdlib, fallback to the store) · MCP walter · hooks · Hermes plugin
  jobs: jobs.nightly (04:10 UTC) — idempotent steps, one failure never blocks the others
```

## What an agent sees (the agent's own model always decides what to open)

| Tier | When | What |
|---|---|---|
| 0 | session start (Claude Code `SessionStart`, Hermes first turn) | the domain map, stable → provider-cached |
| 1 | each user message | cards new for this session: 15, or 8 when the ranker is calibrated-confident; a workflow first, replacing its sub-skills; nothing on follow-ups and machine prompts |
| 1e | after a failed command | at most 2 skills whose card *symptoms* match the specific words of the error |
| 2 | the agent's initiative | `skills_search` / `skill_read` (Hermes: `walter_skill_search` / `walter_skill_read`) |

## Resilience

- Service up → full policy. Registry down at start → engine boots from `.cache/snapshot`; the registry circuit breaker
  fails fast (no waits), exposures keep working without session state.
- Service down → `client.py` searches and reads the git store directly; exposure fails open (nothing injected).
- Everything derived can be rebuilt from git + walter_logs: delete `.cache/`, run `walter-skills nightly`.
- A new ranker is promoted only if not worse on the held-out slice; the service hot-swaps it (no restart).
- Curation never deletes: archive/ + git history; shadow mode on branch `curator/<date>` until `shadow_until`.

## Commands

```
walter-skills search "message"          walter-skills expose "message" --runtime hermes --first
walter-skills read <name> [--file f]    walter-skills nightly [--only step,…]
walter-skills train [--force]           walter-skills curate [--shadow|--apply] [--only op,…]
walter-skills health                    python bench/run.py --hermes
/opt/walter-memory/venv/bin/python -m pytest -q tests
```

Configuration: `config/walter-skills.toml` (the only tunables). Python path: `walter.pth` in the walter-memory venv
(this package + walter_memory), `walter-skills.pth` in the walter-core venv (client only).
