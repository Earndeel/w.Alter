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
| Classify | `checks.provider_side` | Provider 5xx / 429 / a stream ending on a provider error / timeout = `external` (wait, no agent); 401/402/403 or credit exhausted = `needs_owner`; 400/404/422… = ours (agent). |
| Repair | `repair.py`, **L2 text tier** through `walter-router run` | Only what is still broken and repairable here. The agent works on a copy of the module (`@instance/state/router/guardian/<incident>-<time>/module`, own git baseline, the live venv); the live module, the instance configuration and `/etc/systemd` are mounted read-only for it. It ends with a JSON verdict (`prompt.md`). |
| Gates | `repair.gates`, no model | The patch only touches `research/`, `analysis/parse.py`, `analysis/identity.py`, `analysis/aliases.json`, `interface/`, `tests/`; no test deleted, no assertion removed, no skip/xfail added; the full suite on the copy has no new failure; the incident's own case passes (the test is green, or the source is read with rows). |
| Land | `repair.apply` | Each file is copied only if the live file is still exactly what the agent started from and nobody has uncommitted work on it; then a commit of just those files. Otherwise the verified patch waits (`deferred`) and lands on a later pass. A repaired source is read again at once. |
| Tell | `run.notify` → Telegram | Once per outcome: a repair that landed (« réparé tout seul »), a decision only the owner can take (« besoin de vous »), an outside outage lasting ≥ 48 h. Nothing else. |

Limits: 3 agent runs per incident (then `needs_owner`), 12 h between two runs on the same incident, 3 repairs per
pass, a failing test waits 6 h (often someone's work in progress). Never: changing an owner choice (favourites,
roles, preferences, plans, `config/`), execution policy (`serve/`, `llm/`), the schema, units or the cycle.

## When it runs

`walter-router-guardian.timer` (01:20, 07:20, 13:20, 19:20 UTC) and at the end of each 48 h cycle
(`bin/walter-router-cycle` starts `walter-router-guardian.service` without waiting). One pass at a time (lock file).

## Commands

```
walter-router-guardian check [--no-tests]          # what is wrong now; no action, no model
walter-router-guardian run [--no-agent] [--no-tests] [--no-notify] [--dry-run]
walter-router-guardian status                      # open incidents, closed in the last 7 days
```

Statuses: `open`, `repairing`, `fixed`, `deferred`, `external`, `needs_owner`, `resolved` (column comments of
`models.guardian_incidents`, migration 033). The verdict column keeps the agent's cause, evidence, changed files,
gate results, commit and the model/provider that did the work.
