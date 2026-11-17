---
name: walter-engine-release-validation
description: Use when applying Walter Engine runtime changes, restarting dsh-web, or validating persistent Python kernel behavior in production on Monsieur's VM.
---

# Validate a Walter Engine runtime release

## 1. Read the current implementation and rollback instructions

Read `/walter/core/engine/README.md` and `/walter/core/engine/docs/07-CONVERGENCE.md` before acting. The latter records the convergence implementation, known gaps, and rollback instructions. Do not assume all features of the upstream Unharnessed runtime are supported in Walter.

## 2. Check whether production is idle

Run:

```sh
systemctl show dsh-web -p ActiveEnterTimestamp -p ActiveState
cat /user/Lucas/state/core/engine/intake/open-runs.json
systemctl list-units 'walter-python-*' --no-legend
journalctl -u dsh-web --since '-15min' --no-pager
```

Inspect the open-runs file, active kernel units, and recent activity together. A running service is not evidence that it is idle. If a real user run or kernel workload is active, defer the restart or coordinate an interruption; do not kill it merely to complete validation.

## 3. Apply the restart and check service health

Once production is confirmed idle:

```sh
systemctl restart dsh-web
sleep 6
systemctl is-active dsh-web
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3080/
journalctl -u dsh-web --since '-1min' --no-pager
```

In the observed deployment, the web endpoint was on port 3080 and the production Engine API was on `http://127.0.0.1:8895`; confirm these against current documentation before reuse. Examine startup errors rather than treating HTTP responsiveness alone as success.

## 4. Prove kernel behavior through the actual engine

Use the documented Engine API client or the production conversation interface, not a host-shell substitute. For a kernel PATH change, send this explicit technical test:

> With the python tool, execute `bash('python --version && which python pip')` inside the kernel and return the output. This is a technical test; use no personal data.

Verify the tool execution trace and interpreter locations. `python` and `pip` must resolve to the intended kernel environment, not merely whichever binaries happen to be on the host shell's PATH. A service restart and a successful web request do not prove this.

For changes claiming persistence or restart recovery, test those claims separately across turns or a controlled restart; do not infer them from a one-turn PATH check.

## 5. Clean up durable side effects of tests

List open durable tasks before and after end-to-end tests using `tasks_list(status='open')`. Record which task IDs the tests create.

**Known pitfall:** Lab turns, channel `test`, and the `e2e` principal created durable tasks in Monsieur's task list during the convergence session. Those labels did not provide task isolation.

Close only positively identified technical-test tasks with `task_update`, marking them done and adding a note explaining the test scenario and result. Do not close unrelated tasks or treat real mission follow-up as disposable test data. Keep test IDs and cleanup results in the release record.

## 6. Record evidence and remaining limitations

Record the service restart, HTTP check, actual kernel output, test-task cleanup, and any remaining gaps. Keep 'service healthy', 'tool executed correctly', and 'feature validated end to end' as distinct claims. If a check fails, use the documented rollback procedure rather than improvising destructive cleanup.
