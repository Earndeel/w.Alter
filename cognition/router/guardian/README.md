# guardian — the Router's own maintenance

Owner, 2026-10-26: « cela doit être fait automatiquement à partir de maintenant, fais un guardian dans le module qui
s'occupe de la maintenance de celui-ci, peut-être propulsé par L2 ». The guardian keeps the module working without
the owner: it finds what broke, repairs what is ours, waits out what is not, and only speaks when it matters.

## A pass

| Step | Who | What |
|---|---|---|
| Detect | `checks.py`, no model | Sources older than their limit (`analysis/alerts.STALE_HOURS`) or in error at the last cycle; failed or missing cycle; providers whose probe fails; failing tests (except a test file someone has uncommitted work on). |
| Follow | `run.py` | One incident per problem in `models.guardian_incidents` (stable `key`); an incident no longer seen closes (`fixed` or `resolved`). |
| Cheap actions | `run.py` | A provider seen down is probed again first (its status heals when it is back). A stale source is read again once (`walter-router research --source`). |
| Reference | `repair.regenerate_docs`, no model | Generated reference out of date (`walter-router docs --check`): regenerated with `docs --write`, checked again, the regenerated files committed alone. Quiet; waits while someone has uncommitted work on those files. |
| Classify | `checks.provider_side` | Provider 5xx / 429 / a stream ending on a provider error / timeout = `external` (wait, no agent); 401/402/403 or credit exhausted = `needs_owner`; 400/404/422… = ours (agent). |
| Repair | `repair.agent` → `walter-guardian repair --module router --wait` (walter-core) | Since 2026-11-20 (Monsieur: « les guardians doivent pouvoir agir comme moi je le ferais » from a Claude Code session): the guardians' **common repair agent** — one Walter Engine delegation as `guardian-router`, poste **coding/L3** (Opus 5.5 high on 20/11), with the rights of a development session (policy interface `maintenance`: shell and files; outgoing messages never). It works on the live module like a Claude Code session: cause first, backup, fix, tests, restart what it changed, commit only its own files. The module's knowledge it gets: `guardian/playbook.json` `notes`. Ends with a JSON verdict. |
| Verify | `run.still_broken`, no model | The agent's « fixed » is believed only when the incident's own check passes again: the source re-read with rows, the failing test green, the provider probe healthy, the cycle check clear. Otherwise the run counts as failed. |
| Library | `interface/library.follow`, no model | The library page (library.walter-ai.cloud) is rendered again; when what it says changed since its last publication (quotas, routes, choices move between two 48 h cycles), it is republished. |
| Tell | `run.notify` → Telegram | Once per outcome: a repair that landed (« réparé tout seul »), a decision only the owner can take (« besoin de vous »), an outside outage lasting ≥ 48 h. Nothing else. |

Limits: 2 repair-agent runs per incident, 5 h apart (then `needs_owner`, and the owner is told with the agent's words;
before 2026-11-20 the last failure left it `open` and silent), 3 repairs per pass, a failing test waits 6 h (often
someone's work in progress). Never: changing an owner choice (favourites, roles, locks, preferences, plans, `config/`),
sending a message, reading a secret, deleting data (common brief + `playbook.json` notes; the policy blocks outgoing
messages and secret files whatever the agent decides).

## When it runs

`walter-router-guardian.timer` (01:20, 07:20, 13:20, 19:20 UTC) and at the end of each 48 h cycle
(`bin/walter-router-cycle` starts `walter-router-guardian.service` without waiting). One pass at a time (lock file).

Tests run with the module's venv plus the gateway's packages (`llm/venv`, appended by `tests/conftest.py`): the
gateway tests import FastAPI and litellm. Without them (13–20/11) six test files failed to collect and were chased as
failures.

## Commands

```
walter-router-guardian check [--no-tests]          # what is wrong now; no action, no model
walter-router-guardian run [--no-agent] [--no-tests] [--no-notify] [--dry-run]
walter-router-guardian status                      # open incidents, closed in the last 7 days
```

Statuses: `open`, `repairing`, `fixed`, `deferred`, `external`, `needs_owner`, `resolved` (column comments of
`models.guardian_incidents`, migration 033). The verdict column keeps the agent's cause, evidence, changed files,
gate results, commit and the model/provider that did the work.
