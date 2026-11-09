# walter-skills

| | |
|---|---|
| **Rôle** | Mémoire procédurale de W.Alter : contenu, recherche, propositions et curation des procédures, indépendamment de tout runtime. |
| **Propriétaire** | walter-skills (`/walter/skills`). |
| **État** | **active** (constat du 09/11/2026) : services `walter-skills` (:8891) et `walter-skills-bus`, tâche nocturne 04:10 UTC. |
| **Ne fait pas** | Dépendre d'un runtime (Hermes, Claude Code, Codex, DSH sont des adaptateurs). Garder un secret dans le texte d'un skill. |
| **Contrats** | [contracts/skills.json](contracts/skills.json), [contracts/data-classes.json](contracts/data-classes.json), [contracts/maintenance.json](contracts/maintenance.json) ; MCP `skills_search`, `skill_read`, `skill_propose`, `skill_patch` ; schéma PostgreSQL `skills`. |

W.Alter's procedural memory: skills and workflows, owned by Walter, independent of any agent runtime. Hermes, Claude
Code, Codex and DSH are adapters. Plan: `/root/.hermes/docs/walter-memory/PLAN.md` (P10). Decisions and measurements:
`DECISIONS.md` (2026-10-09/10). Operations: `RUNBOOK.md` § walter-skills.

## Manifest and discovery index

`MANIFEST.md` explains purpose, components and progressive loading. `contracts/skills.json` is the machine-readable
technical contract. The Curator maintains descriptions/domains/workflows and publishes the active discovery index;
event reconciliation and the nightly graph refresh it too. The projection contains names, kinds, purposes and workflow
components, never procedure bodies. It is atomically published in `.cache/library-index.json` and registry state.

Default `policy.discovery = "on_demand"`: show the compact domain overview at session start, browse a selected domain
with `skills_index`, or search by intent; then read only the selected procedure and supporting files. `skills_manifest`
explains the module. Hermes uses `walter_skills_index` / `walter_skills_manifest`. CLI: `walter-skills manifest` and
`walter-skills index --domain <domain> [--offset N --limit N]`. HTTP: `/v1/manifest`, `/v1/index`.

`shortlist` keeps the former per-message ranking policy for comparisons/rollback. Search ranking and error assistance
remain available. Existing MCP sessions need their tool schemas refreshed to see the two new operations.

## Library layout and lifecycle (reorganised 2026-11-01)

- `skills/<domain>/<name>/` — the **active** library: 20 plain domains (walter, secrets, hermes, web, computer-use,
  research, shopping, models, images, video, cloudflare, gpu, code, design, devops, messaging, productivity, home,
  learning, scena, + reserve-only audio/business). One small procedure per intent; a short **entry** skill
  (`kind: entry` in the sidecar) routes a domain when it has shared rules (web, cloudflare, image-generation,
  video-generation, walter-model-router, hermes-memory-ops, bitwarden-logins, android-tv-stremio-dongle…). Workflows
  live in the domain of their first step.
- `archive/<name>/` with `reserve: true` — the **reserve**: dormant skills. Tier-2 search ranks them with the active
  library (flagged « réserve »), the domain index lists them after the active entries, and **reading one restores
  it** (`walter_skills/reserve.py`: move back to its domain, commit, ledger `reserve/restore`). `walter-skills read
  --peek` reads without restoring.
- `archive/<name>/` with `absorbed_into: <hub>` — **merged**: the original text is copied verbatim in
  `<hub>/references/merged-<name>/`; search answers the old name with the hub (`via`), reads point to the hub.
- `archive/<name>/` with `retired: true` — **retired**: describes a system that no longer exists (Hindsight, Jarvis,
  the voice stack, the Hermes dashboard, the hand-written identity). Never searched, never restored; readable by name
  as history.
- Curator: dormant 30 days (no read, not needed by a real message in 30 days — synthetic bench labels never protect)
  → reserve; entries are never archived or merged; a workflow whose steps already exist is never written again.
- No secret in a skill: the curator operator `secrets` (always active, every quick run) and the write door turn
  every Bitwarden value into its Walter Secrets placeholder `{{bw:<item>:<field>}}` (`walter_skills/secret_refs.py`;
  resolved at execution by Hermes' hook or `walter-secret get <item> <field>`, never shown to a model). It covers the
  store (active, reserve, drafts) and Hermes' copies (security only). Short visible fields (e.g. an AWS region) are
  configuration and stay readable; a value indexed but gone from the vault gets the generic mask `«secret:vault»`.

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
                 │ door        the single way content enters (checked at the door, then live)     │
                 └───────────────────────────────────────────────────────────────────────────────┘
  ports (no rules): api.py (HTTP :8891) · client.py (stdlib, fallback to the store) · MCP walter · hooks · Hermes plugin
  events: consumer.py on the Walter bus (walter_memory.bus) — instant reactions, no timers
  jobs: jobs.nightly (04:10 UTC) — idempotent steps, one failure never blocks the others
```

## Events (the Walter bus, not timers)

Runtimes and modules speak to walter-skills through typed events in Postgres (`bus.events` + `pg_notify`), whatever
the runtime. The hook adapter (`/opt/walter-core/hooks/walter_hook.py`) translates each runtime's own hooks; the
write door emits too. `walter-skills-bus` runs two consumers, each with its own cursor (a stopped consumer catches up):

| Event | Emitted by | walter-skills reacts |
|---|---|---|
| `skill.proposed` | the write door (MCP `skill_propose`/`skill_patch`, the learner) | consumer `walter-skills`: draft → live + card (< 1 min; no model judge since 2026-10-26, only the target is checked) |
| `skill.changed` | Hermes `on_skill_lifecycle` (created/patched/edited/…) | same, after syncing that skill from `~/.hermes/skills` |
| `turn.ended` | Claude Code / DSH `Stop`, Hermes `on_session_end` (every turn), Codex `notify` | consumer `walter-skills-learning`: implicit labels for that session |
| `session.ended` | Claude Code `SessionEnd`, Hermes `on_session_finalize` | same + the learner reads the session (may propose a skill) |

Bursts are absorbed (a 10 s calm before applying). What bypasses the bus (a hand edit, a Hermes update) is caught
by the hourly reconciliation (`jobs.quick`, run by the consumer when idle). Failed events stay in `bus.dead`;
`walter-skills health` reports a consumer more than 15 min behind.

## What an agent sees (the agent's own model always decides what to open)

| Tier | When | What |
|---|---|---|
| 0 | session start (Claude Code / DSH `SessionStart`, Hermes first turn) | compact purpose + domain index + navigation tools |
| 1 | on demand | selected domain: workflow/skill purposes and dependencies, up to 20 entries per page; no per-message shortlist in `on_demand` mode |
| 1e | after a FAILED command (Claude Code `PostToolUseFailure` or stderr, DSH `[exit code: N]`) | at most 2 skills whose card *symptoms* match the specific words of the error |
| 2 | the agent's initiative | `skills_search` / `skill_read` (Hermes: `walter_skill_search` / `walter_skill_read`) |

## Resilience

- Service up → full policy. Registry down at start → engine boots from `.cache/snapshot`; the registry circuit breaker
  fails fast (no waits), exposures keep working without session state.
- Service down → `client.py` searches and reads the git store directly; exposure fails open (nothing injected).
- Everything derived can be rebuilt from git + walter_logs: delete `.cache/`, run `walter-skills nightly`.
- A new ranker is promoted only if not worse on the held-out slice; the service hot-swaps it (no restart).
- Curation never deletes: archive/ (reserve, merged, retired) + git history; shadow mode on branch `curator/<date>` until `shadow_until`.

## Commands

```
walter-skills search "message"          walter-skills expose "message" --runtime hermes --first
walter-skills read <name> [--file f] [--peek]    walter-skills nightly [--only step,…]
walter-skills train [--force]           walter-skills curate [--shadow|--apply] [--only op,…]
walter-skills health                    python bench/run.py --hermes
/opt/walter-memory/venv/bin/python -m pytest -q tests
```

Configuration: `config/walter-skills.toml` (the only tunables). Python path: `walter.pth` in the walter-memory venv
(this package + walter_memory), `walter-skills.pth` in the walter-core venv (client only).
