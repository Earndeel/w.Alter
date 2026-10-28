# Guardians — common convention (P5, 2026-10-28)

Owner decisions (2026-10-27): every Walter module has its own guardian; Curator ≠ Guardian ≠ Lab; a minimal
supervisor checks that modules and guardians answer, without becoming a central agent; critical watchdogs work
without Router or Memory. Reference implementation: `/walter/router/guardian` (detection without a model, incident
follow-up, repair on a copy behind deterministic gates, sparse Telegram).

## Declaration — `<module>/contracts/maintenance.json`

```json
{"version": 1, "module": "<id>", "check": ["<command>", "<args>…"], "format": "incident-v1",
 "timeout_seconds": 120, "max_level": "G1", "levels": {"G0": "…", "G1": "…"}, "note": "…"}
```

- `check` prints a JSON list of **Incident v1** (`contracts/schemas/incident-v1.json`); `[]` = healthy. No model, no
  side effect, fast. It is the module's watchdog (G0); its guardian agent and maintenance executor, when they exist,
  stay inside the module (router: `walter-router-guardian run`).
- `max_level` = the most the module's own guardian may do without the owner: G0 observe · G1 routine reversible action
  (restart a unit, re-read a source, regenerate an index) · G2 repair on a copy behind gates, with
  `walter-backup checkpoint` before landing · G3 owner only.
- A module sharing a directory with others declares once with `"modules": [...]`.

## Supervisor — `walter-guardians` (walter-core)

`walter-guardians check [--no-notify]` runs every declared check (parallel, bounded), keeps open incidents by
`module:key` in `@instance/state/guardians/state.json`, appends openings/closings to `incidents.jsonl`, and sends
Telegram (Bot API directly, no Hermes) only for **new** `high`/`critical` incidents. A check that fails, times out or
prints something else becomes the incident `guardian:unreachable` of that module. `walter-guardians status` reads
the state. Timer `walter-guardians.timer` (every 15 min). Standard library, system `python3`.
