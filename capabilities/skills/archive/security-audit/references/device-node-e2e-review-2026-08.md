# Device Node E2E review — deployability checklist (2026-08-06)

Read-only adversarial E2E review of a Python "fail-closed device control plane"
(an unprivileged Node + privileged Broker over owner-only Unix sockets, macOS first).
What emerged is a reusable deployability check for any shipped daemon/CLI. Findings:

## 1. Declared entrypoints pointing at a missing module
- `pyproject.toml` declared console scripts (`walter-node`/`walterctl`/`walter-broker`)
  pointing at `walter_device_node.cli:...`.
- `src/walter_device_node/cli.py` did **not** exist, and there was no `__main__` block or
  launcher wrapper. Result: every launch raises `ModuleNotFoundError` at runtime.
- A test file imported symbols from the missing module → the suite errored at collection
  (one collection ERROR, the other 272 tests passed).
- Grep verdict: the orchestration constructors appeared **only inside tests** → a library
  exists, but no process wiring that binds store + service + socket server together.

## 2. Reproducibility / CI blocker from the wrong venv
- A secondary "hardened" venv had the test runner installed but **not** the project package,
  so every test module aborted on import before collection. The main venv ran the suite but
  still errored on the missing CLI test. Nothing produced a green full-suite run, so the
  documented dev command cannot serve as a CI gate. Report as a reproducibility problem,
  not "tests are broken."

## 3. Dead-on-arrival privileged slice (issuance missing)
- The elevated operation path consumed a one-shot grant (consumption method exposed), but
  **no issuance method was exposed** over any RPC surface ⇒ every elevated op denied
  (fail-safe, but non-functional end-to-end).
- Compounding: a terminal denied status keyed on an idempotency key is final, and idempotent
  replay returns the stale denial forever ⇒ a refused grant permanently locks that key for
  retries (fail-safe, but stuck).

## 4. Mid-build detection via mtimes
- `find -newermt '...'` showed every source file written within ~20 minutes during the audit,
  including the CLI test written just before the module it imports. Read this as a tree
  actively mid-build / pending work, and report the state as of review time.

## 5. What was positively checked (so the report reads as verified, not assumed)
- Peer auth over the owner-only local socket, socket permission and parent-directory checks.
- The command dispatcher's identity/replay hardening and platform portability.
- The idempotency/state-machine concurrency gate (single-dispatch mutex).
- The tamper-evident audit chain verifying on start.

## Reporting shape that worked
Lead with the single decisive blocker (not runnable / no wiring), then subsystem gaps
(elevated slice unreachable), then medium items (server echoes internal exception text to
the socket peer; reproducibility). Close with a short "verified sound" list. All findings
file:line-cited.
