---
name: walter-guardians-alert-repair
description: Use when W.Alter sends repeated Telegram guardian alerts, module watchdogs flap, or guardian repair and notification behavior needs diagnosis on Monsieur's VM.
---

## Locate the supervisor and incident history

Read `/walter/core/GUARDIANS.md` before changing behavior. The supervisor implementation is `/walter/core/bin/walter-guardians`; the shared module guardian engine is `/walter/core/bin/walter-guardian`.

```bash
systemctl cat walter-guardians.service
systemctl list-timers --all
walter-guardians status
journalctl -u walter-guardians --since '-2h' --no-pager
```

Resolve the active instance instead of assuming its state directory:

```bash
instance_path=$(walter instance path)
ls -la "$instance_path/state/guardians"
tail -n 30 "$instance_path/state/guardians/incidents.jsonl"
```

Inspect actual JSON field names before writing an incident-history parser. Repeated messages can represent repeated opening and closing of one incident, rather than repeated delivery of an unchanged incident. In the observed failure, the Mac tunnel incident reopened 15 times and the memory watchdog incident reopened eight times.

## Diagnose each module independently

Read `/walter/<module>/contracts/maintenance.json`, its declared check command, and `/walter/<module>/guardian/playbook.json`. Common check implementations live at `/walter/<module>/guardian/check`.

```bash
cat /walter/memory/contracts/maintenance.json
cat /walter/memory/guardian/check
walter-memory health
cat /walter/capabilities/browse/contracts/maintenance.json
cat /walter/capabilities/browse/guardian/check
systemctl cat walter-exit-mac
journalctl -u walter-exit-mac --since '-8h' --no-pager
```

For memory health message formats, inspect `/opt/walter-memory/walter_memory/health.py`. Inspect the supervisor's incident validation before attributing an unreachable-watchdog incident to a service failure: malformed or duplicate incidents can fail validation. Preserve unique, stable incident keys and validate the emitted incident list against the current implementation.

## Treat Mac sleep as expected behavior

`walter-exit-mac` is an SSH SOCKS tunnel to Monsieur's Mac. The Mac can sleep or leave the network. Inspect `tailscale status`, the tunnel unit, and its journal to distinguish expected disconnection from a VM failure.

Monsieur's established preference is that Mac disconnections never generate Telegram messages. Keep expected disconnection informational and retain automatic reconnection and the existing fallback path. The session changed aggressive restarts, observed at roughly 280 per hour, to retries starting at 15 seconds and backing off to five minutes. Read the current implementation before modifying retry settings; do not assume systemd supports a particular backoff directive.

## Repair through module guardians before escalating

Maintain the flow: module detector → module guardian → evidence gathering and diagnosis → declared repair → verification → notification only when Monsieur is needed.

Use each module's declared guardian and playbook. Keep repairs constrained by declared actions, allowed parameter values, and the permitted guardian level. A model diagnosis must not become unrestricted shell execution. Preserve the Router guardian's existing responsibility for its own notifications.

Validate playbooks through the engine:

```bash
for module in browse memory secrets skills context ops; do
    walter-guardian playbook --module "$module"
done
```

Inspect command results for validation errors. JSON syntax validation alone does not validate engine requirements. A fallback referencing an undeclared action caused a validation failure during this session.

## Verify repair and notification behavior

Run the existing targeted suites after changing the engine or supervisor:

```bash
cd /walter/core
walter-python -m pytest -q tests/test_guardian_agent.py tests/test_guardians.py tests/test_guardians_regressions.py tests/test_renamed_module.py
```

Use a declared incident with `walter-guardian run --module <module> --dry-run` to inspect evidence and proposed actions before exercising a repair. The command consumes JSON containing an `incidents` list on standard input; obtain incident fields from the current detector and schema.

Run a supervisor check without Telegram delivery:

```bash
timeout 900 walter-guardians check --no-notify
walter-guardians status
```

`--no-notify` suppresses notification delivery; it does not make the check read-only. Guardians may still repair services. Inspect the returned `guardians`, `opened`, `closed`, and `pending_notifications` fields. Repeat the check after repair to confirm incident closure.

When an interruption is appropriate and authorized, use a recoverable service to verify actual repair. The session stopped `walter-skills-bus`, ran the supervisor with `--no-notify`, and confirmed that the guardian restarted it without messaging Monsieur. Do not stop a service merely to inspect configuration. Check both `systemctl is-active walter-skills-bus` and incident state after the exercise.

## Commit only the intended module files

Guardian changes can span `/walter/core`, `/walter/memory`, `/walter/capabilities/browse`, `/walter/secrets`, `/walter/skills`, `/walter/context`, `/walter/ops`, and `/walter/router`, each a separate Git repository. Inspect staged and unstaged changes before staging explicit paths; preserve unrelated session work.

If Git reports a missing identity, inspect recent authors first:

```bash
git -C /walter/core log -5 --format='%an <%ae> | %s'
```

The established local identity observed in this session was `W.Alter <walter@localhost>`. When appropriate, pass it per command instead of modifying global Git configuration:

```bash
git -C /walter/core -c user.name=W.Alter -c user.email=walter@localhost commit -m 'Describe the guardian change' -- <explicit-paths>
```

After each commit, inspect `git show --stat HEAD`, remaining staged paths, and status for the intended files. Report commits per module and whether anything was pushed.
