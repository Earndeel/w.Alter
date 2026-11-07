# Auditing an out-of-process shadow / sidecar observer (must-never-affect-hot-path)

Read-only review of a "shadow" / "sidecar" / "observer" / "probe" module that replays
or observes a production component (V1) without ever touching its live path. The core
claim to verify is **isolation**: a failure of the sidecar must be impossible to
propagate into production. Used for a macOS shadow-telemetry Lot 2.1 audit (Computer
Use V2). Concrete commands are grep/read-only; nothing below modifies the tree.

## 1. Prove out-of-process isolation by IMPORT CLOSURE, not by repo layout
The sidecar living in its own files means nothing — the backend/SSH runner may still be
imported by the poll entrypoint. Compute the closure of the entrypoint that the
daemon/timer actually execs (`ExecStart` module → its imports → theirs) and grep THAT
closure for banned roots:
```bash
# poll path = shadow_spool_cli -> shadow_spool -> shadow_sidecar
#           -> {device_context, observation, shadow_observation, shadow_policy, shadow_replay}
grep -nE 'subprocess|macos_shadow|ssh|exec\(|CuaDriver|call_tool' <each poll-path file>  # expect: none (or only event.action=="capture" classification, not a real capture)
grep -rln 'macos_shadow' adaptive_operator tests benchmarks | sort   # who actually reaches the SSH runner
```
Distinguish **reachable-in-closure** from **present-in-repo**: an SSH/subprocess runner is
fine if it lives in a module that only tests/benchmarks import (reachable via a *separate
one-shot benchmark*, never the poll loop). Name which module is excluded and why.

## 2. Backend/SSH counters must be provably zero in the poll
The sidecar's poll result should carry `additional_backend_calls`, `failures_affecting_v1`,
`duplicate_backend_observations`, and forbidden action counters (clicks/keystrokes/
screenshots/vision/focus/device_actions) — all must be `0`. Verify in BOTH the code
(defaults) and the committed benchmark-report.json `counters`/`gates`.

## 3. Read-only DB access is literal
Open the production DB read-only via SQLite URI, and check nothing else in the closure
writes: `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`. Confirm the artifact evidence
state.db size/mtime unchanged across the run.

## 4. Correlation / cursor / quarantine / idempotence
Read the replay reader's pairing logic:
- Pair result↔call by `session_id` + `tool_call_id` between an assistant message
  (`tool_calls` JSON) and the tool message (`role='tool'`, `tool_name='computer_use'`).
- **Cursor advances ONLY past a correlated result.** Malformed-but-complete pairs →
  quarantine (advance cursor, log error, continue). Unpaired result → **block** (no
  advance) so a persistence race isn't silently masked.
- Idempotence proof: events written with exclusive-create `open("x")` (never overwrite)
  and cursor written atomically (`.tmp` + `os.replace`). **The decisive evidence is a
  real second poll:** first poll N seen/N created, second poll 0/0, cursor unchanged.
- Pitfall to flag (suggestion, not must-fix): an *unpaired* result that is permanently
  orphaned (not just a transient race) stalls the whole queue forever because `break`
  holds the cursor; later events are never spooled. Suggest a stale-unpaired timeout →
  monitored quarantine.

## 5. Failures can't reach V1
- Separate systemd unit, `Type=oneshot`, **no `Restart=`**.
- Event-scoped isolation: per-event `try/except` in the sidecar poll sets `shadow_error`
  and continues; never raises out of the loop.
- `failures_affecting_v1` must be `0` everywhere and asserted in tests.

## 6. systemd confinement is real, and verify installed==deploy
```bash
diff <(cat /etc/systemd/system/computer-use-v2-shadow.service) deploy/computer-use-v2-shadow.service  # expect: identical
systemctl show computer-use-v2-shadow.service -p Type -p Result -p ExecMainStatus -p NRestarts
systemctl list-timers computer-use-v2-shadow.timer --no-pager
```
Look for: `RestrictAddressFamilies=AF_UNIX` (blocks network — so even if code tried to
open a socket/SSH the kernel refuses), `NoNewPrivileges=true`, `CapabilityBoundingSet=`
empty, `ProtectSystem=strict`, `PrivateDevices`, `UMask=0077`, `ReadOnlyPaths` on the
workspace+DB, `ReadWritePaths` narrowed to the spool, `Nice=10` + `IOSchedulingClass=idle`.
ActiveState may read `inactive/dead` for a oneshot that already ran — that's correct, the
timer drives it.

## 7. Secrets: absent from code AND docs, and the store carries only references
Scan `adaptive_operator` + `docs` + `deploy` for `ssh-rsa`, `BEGIN ... PRIVATE`,
`sk-<hex>`, hardcoded `identity_file`/`password=`. A device-context store is fine if it
holds a **runtime identity_ref** ("runtime:tailscale:<node-id>") and never a Tailscale or
SSH private key. Note when a benchmark artifact (device-context.json) exposes the peer's
Tailscale ID / DNS / route at world-readable `0644` — not a secret, but a
defense-in-depth suggestion (align to spool `0700/0600`).

## 8. must_fix vs suggestions discipline
Elevate to `must_fix` ONLY when a stated invariant is *actually violated*. Documented AND
tested design choices (fail-closed unpaired-blocking, non-root hardening, stale manifest,
world-readable benchmark artifact) are `suggestions`, not `must_fix`. A must_fix forces
`passed=false`. Always distinguish "tested intentional behavior" from "oversight".

## 9. Deliverable shape (machine-validated JSON)
Flat single JSON object, no prose around it:
`{ "passed": bool, "must_fix": [{file,issue,reason,suggested_fix}],
   "suggestions": [str], "verified": [str], "tests": {...}, "summary": str }`.
- `passed=false` iff at least one must_fix.
- `verified` = concrete evidence strings ("second poll 0/0", "import closure clean",
  "diff empty vs deploy unit", "counters all 0").
- `tests` = suite result (e.g. 92/92) + the read-only greps/diffs run as evidence.
- Write the summary in the user's language (French here), factual.
