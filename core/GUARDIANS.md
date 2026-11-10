# Guardians — common convention (P5, 2026-10-28)

Owner decisions (2026-10-27): every Walter module has its own guardian; Curator ≠ Guardian ≠ Lab; a minimal
supervisor checks that modules and guardians answer, without becoming a central agent; critical watchdogs work
without Router or Memory. Reference implementation: `/walter/cognition/router/guardian` (detection without a model, incident
follow-up, repair on a copy behind deterministic gates, sparse Telegram).

## Declaration — `<module>/contracts/maintenance.json`

```json
{"version": 1, "module": "<id>", "check": ["<command>", "<args>…"], "format": "incident-v1",
 "timeout_seconds": 120, "max_level": "G1", "levels": {"G0": "…", "G1": "…"}, "note": "…"}
```

- `check` exits with code 0 and prints a JSON list of **Incident v1** (`contracts/schemas/incident-v1.json`); only code 0 plus `[]` means healthy. No model, no
  side effect, fast. It is the module's watchdog (G0); its guardian agent and maintenance executor, when they exist,
  stay inside the module (router: `walter-router-guardian run`).
- `max_level` = the most the module's own guardian may do without the owner: G0 observe · G1 routine reversible action
  (restart a unit, re-read a source, regenerate an index) · G2 repair on a copy behind gates, with
  `walter-ops backup checkpoint` (alias `walter-backup checkpoint`) before landing · G3 owner only.
- A module sharing a directory with others declares once with `"modules": [...]`.

## Supervisor — `walter-guardians` (walter-core)

`walter-guardians check [--no-notify]` runs every declared check (parallel, bounded), keeps open incidents by
`module:key` in `@instance/state/guardians/state.json`, appends openings/closings to `incidents.jsonl`, and sends
Telegram (Bot API directly, no Hermes) for new `high`/`critical` incidents and severity escalations. A nonzero exit,
timeout, invalid JSON, invalid Incident v1, duplicate key, or incident attributed to a module outside the declaration
fails the complete watchdog response and becomes `guardian:unreachable`. Failure to read the module inventory
becomes `core:guardian:unreachable`; an existing but invalid maintenance declaration becomes the same incident
for its module. Neither discovery failure can be reported as an empty healthy pass. Invalid items are never silently discarded.
The supervisor preserves previously open incidents for a watchdog that failed; failure cannot establish recovery.
A later valid response can close them. `walter-guardians status` reads
the state. Timer `walter-guardians.timer` (every 15 min). Standard library, system `python3`.


## Notification delivery (2026-10-29)

The open incident state is also the persistent delivery queue. A failed send stays pending across supervisor
invocations. Attempts are bounded to five per incident/severity, with delays of 15, 30, 60 and 120 minutes before
the remaining attempts (maximum configured delay 6 hours). A severity escalation resets delivery attempts;
a successful send suppresses repeats while the incident stays unchanged. Resolving the incident removes its
pending alert. `--no-notify` observes and updates incidents without sending or consuming an attempt; pending
alerts remain available for a later notified pass. Each batch contains at most ten bounded incident summaries,
so incidents omitted from a batch are not falsely acknowledged. `check` returns pending/exhausted counts.
An exhausted alert remains visible in state/status and requires operational review; it is not retried forever.

State is replaced atomically after each pass; incident openings, closings and escalations are appended to
`incidents.jsonl`. The supervisor stores return codes and invalid-response metadata, never raw watchdog stderr
(which could include secrets). The Telegram transport is unchanged; isolated tests replace it with a fake
function and never access the grant or send a real message.

Coverage is limited to modules with a maintenance declaration. A missing declaration does not claim a healthy module
and does not invent a watchdog; use `walter-guardians list` to inspect the actual coverage.

## Flap damping (2026-10-30)

An incident that reopens less than `FLAP_SECONDS` (6 h) after a notified closing, at the same or a lower severity, is
recorded (opened/closed in `incidents.jsonl`, `suppressed: "flap"` in state) but not re-sent; a higher severity is
always sent. Watchdogs should still not flap: an expectedly absent dependency (the owner's Mac asleep for
`walter-exit-mac`) is `info`, and a watchdog emits one incident per key.

## Module guardians: repair first, tell only when needed (2026-10-30)

Owner, 2026-10-30: « Les guardians sont censés être des agents intelligents qui doivent comprendre les situations et
les régler d'eux-mêmes ; pour le Mac qui se déconnecte, pas besoin de me notifier à chaque fois. »

- **Declaration.** `maintenance.json` gains `"guardian"`: a command (`["walter-guardian", "run", "--module", "<id>"]`)
  that reads `{"incidents": [...]}` on stdin and answers `{"verdicts": {"<module>:<key>": {outcome, diagnosis_fr,
  message_fr, actions}}}`, or `"self"` for a module whose guardian tells the owner itself (router).
- **Supervisor.** A new high/critical incident is handed to its module's guardian before anyone is told (one run per
  module per pass; again after `GUARDIAN_RETRY`, or `GUARDIAN_RECHECK[outcome]`). Telegram only for: `critical`
  (at once, with the guardian's words when it has them), `needs_owner`, `external` lasting 12 h, `failed` lasting 2 h,
  no verdict after a 30 min grace (never silence). `fixed`, `pending`, `expected` are never told. A module without a
  `guardian` keeps the old rule (the watchdog's word is final); `"self"` modules are told about only when their
  watchdog itself is unreachable. `--no-act` observes without handing anything over.
- **Engine** `walter-guardian` (walter-core, stdlib): evidence = read-only commands from the module's
  `guardian/playbook.json` (masked before any model) → decision by a Walter Router poste through walter-llm
  (`general/L2`, token `@instance/state/guardians/llm.env`) → only declared actions, level ≤ the module's
  `max_level`, parameters from the playbook's allow-list, ≤ 3 per run, 2 rounds per incident per 12 h → module check
  again after `settle_seconds` (`fixed`), or `pending` for asynchronous actions → rounds exhausted = `needs_owner`
  with what was tried. Without a model: the playbook's `fallback` action for that kind, else `unknown`.
  History `@instance/state/guardians/agent/<module>.json`, actions `actions.jsonl`.
- **Playbook** (`<module>/guardian/playbook.json`, version 1): `notes` (what is normal, what incidents mean, what only
  the owner can do), `evidence` by incident kind (`*` = always), `actions` (`level`, `command` with `{param}`,
  `params` allow-lists, `async`, `timeout_seconds`), `fallback` by kind, `settle_seconds`. Written for browse,
  memory, secrets, skills, context, ops. Adding knowledge to a guardian = editing its playbook, not the engine.
