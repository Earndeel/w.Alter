---
name: walter-integration-verification
description: Use when auditing Walter's effective module integration or verifying that a routed sub-agent really executes tools and persists its complete run trace.
---

# Verify Walter integration with live evidence

## Establish the live inventory

Run:

```bash
walter modules
walter status
walter check
walter matrix
```

Record command exit codes and the matrix's `observation_snapshot_at`. Inspect `available`, `bound`, and `in_use` separately for each harness/capability binding. Treat an old observation as historical evidence. A healthy module or passing structural check does not establish that a runtime actually uses it.

Read the relevant module contracts and existing architecture decisions before proposing changes. Distinguish implemented, connected, observed in use, and quality-tested capabilities in the report.

## Exercise the real execution path

Run the existing scenario from a neutral working directory:

```bash
cd /tmp
walter-scenario run e2e-minimal --json
```

Allow sufficient execution time: this scenario calls real tools and a routed model. Inspect the JSON's `ok`, `steps`, `assertions`, and `run_id`; do not infer success from process completion alone.

The scenario must exercise the real hook adapter and walter-core MCP path. A direct unit call or mocked gateway does not verify propagation of the caller's run context.

## Verify durable traces

Inspect the returned run:

```bash
walter-memory runs show <run_id>
```

Locate the routed child's task/session identifiers in the result and inspect its log:

```bash
walter-memory logs timeline walter-router/<task_id>
```

Confirm that:

- The routed task belongs to the caller's run and reaches a terminal status.
- The child session has the expected parent session.
- The trace contains the prompt, model/tool activity, tool results, and final answer.
- Tool execution used the requested Walter capability and the answer satisfies the scenario's substantive assertions.

A returned answer is insufficient evidence of successful persistence. During the 2026-10-27 implementation, a routed agent produced an answer while its trace writer failed.

## Diagnose failures at the interface boundary

- If `logs.event_key` raises `AttributeError: 'str' object has no attribute 'astimezone'`, normalize serialized event timestamps to timezone-aware `datetime` objects before handing events to the logs Writer. The observed fix was in `walter_memory/runs.py`; do not bypass the canonical writer.
- If the scenario records an empty answer despite successful execution, inspect the actual tool response shape. The observed response used `output`; the scenario previously read only `answer`, `raw`, or `text`.
- If run correlation fails through the MCP server, inspect the hook's process-context recording. The server's parent-process lookup is part of the real path and must be exercised by the scenario.
- If Router documentation tests report `Undocumented environment variable`, document newly introduced variables in its documentation registry and regenerate the reference through the module's documented interface. This occurred for `WALTER_RUN_TOOLS` and `WALTER_SESSION_ID`.

Back up affected files before fixes, run the relevant module tests, rerun the live scenario, and finish with `walter check`. For memory-service changes, also run `systemctl start memory-autopilot` and inspect its reported score. Report remaining failures explicitly; structural success and execution quality are separate findings.

## Verify a pinned Router level end to end

When a caller such as the development board must always use L3, verify the Router level rather than hard-coding today's model.

1. Inspect the current mapping with `walter-router dossier general`. Treat the L3 provider, model and reasoning variant as mutable configuration, not permanent constants.
2. Trace the level through the caller, engine session and gateway. A session opened with `level: L3` must preserve that override on subsequent calls even when preflight chooses a lower level. Ensure the execution budget is at least the L3 budget; the verified deployment used 60 steps and 35 minutes. Do not infer that pinning a model also pins the level or its budget.
3. Run the affected regression suites:
   ```sh
   cd /walter/cognition/router && walter-python -m pytest -q tests -p no:cacheprovider
   cd /walter/core && node --test interfaces/api/tests/api.test.mjs
   cd /walter/core && node --test engine/tests/plugins.test.mjs
   cd /walter/core && walter-python -m pytest -q engine/tests -p no:cacheprovider
   cd /walter/ops/devboard && walter-python -m pytest -q tests -p no:cacheprovider
   walter check
   ```
   Inspect individual failures, not just aggregate counts. If the Router documentation test reports stale generated references, regenerate with `cd /walter/cognition/router && ./bin/walter-router docs --write`, review the diff and rerun the suite. A test assuming every live preference is locked is invalid when the owner has deliberately unlocked preferences; preserve those settings and test lock behavior with controlled fixtures instead.
4. Before restarting services, check for active engine turns and running development-board resumptions. Once safe and authorized, deploy with:
   ```sh
   systemctl restart walter-llm dsh-web walter-devboard-web
   systemctl is-active walter-llm dsh-web walter-devboard-web walter-telegram walter-devboard-bus
   curl -fsS http://127.0.0.1:8894/health
   ```
5. Open an isolated test conversation through the engine's declared API with `level: L3`. Send a deliberately trivial message so preflight can select L1. Correlate that turn with its persisted gateway request and selection trace. The demonstrated successful trace contained `req.level: L1`, `req.pinned_level: L3`, and a selection event with `task: general/L3`. Confirm that the selected provider/model matches the current L3 mapping. Also test rejection of an invalid level; the observed error was `invalid_level`.
6. Report separately: tests passing, services healthy, and live routing proven. A successful response or an L3-labelled session alone does not prove the override survived preflight. Avoid claiming that a single-turn smoke test proves multi-turn persistence; cover subsequent turns separately.

For board tests that invoke the resume brief, isolate the real memory CLI. In `tests/test_actions.py`, an autouse fixture can use `monkeypatch.setattr(actions, "_cli", lambda *a, **k: None)`; individual tests should supply controlled responses when testing memory enrichment. Otherwise apparently local tests can query live logs and tasks.

## Trace degraded context preflight through Router decision failover

1. Read `/walter/cognition/context/README.md` and the relevant runbook. Run `systemctl status walter-context-preflight --no-pager` and `journalctl -u walter-context-preflight --since '-60min' --no-pager`. An active unit is not proof of healthy context injection: inspect recent `plan.decision.degraded` records in `$(walter instance path)/state/context/shadow/preflight-*.jsonl`. Use `walter-context-preflight --report` to check degradation counts. Record the UTC time of a representative failure without copying prompts or context payloads.
2. If the shadow error is `HTTP 502: no decision model answered`, correlate that UTC window with `$(walter instance path)/logs/walter-llm.jsonl`. Read a bounded tail (for example, `tail -n 10000 "$(walter instance path)/logs/walter-llm.jsonl"`) and filter on `at` and `task == "decision"`. The preflight error can truncate provider details; inspect the gateway attempts before attributing the failure to a provider, rate limit, or routing policy.
3. Scope source searches to `/walter/cognition/router/llm`, not `/`. In `llm/structured.py`, distinguish whole-request failover from split assignment, per-group fallback, and final required-question checks. The split path can return 502 even when another group answered if a required question failed. Compare `config/decision-needs.json` with the current registry from `walter decisions`. Use `llm/decision.py`'s planner to check both individual questions and the exact compiled group, with the same media constraints as the failing call. A fallback that can carry one question need not carry the group.
4. Reproduce offline with the mocked routes in `tests/test_native_whole.py` and `tests/test_gateway_structured.py`. Preserve the live question mix and required/optional flags, simulate the observed route failure, and assert the HTTP status, required answers, and recorded attempts. From `/walter/cognition/router`, first run `/walter/ops/runtime/venv/bin/python -c 'import fastapi, pytest, httpx'`, then run `/walter/ops/runtime/venv/bin/python -m pytest -q tests/test_native_whole.py tests/test_gateway_structured.py`. On this VM, system Python and Router's `venv/bin/python` lacked FastAPI, while `llm/venv/bin/python` lacked pytest; do not mistake those import failures for regressions.
5. If a Router fix is warranted, inspect `git status` and back up only the files you will edit under `$(walter instance path)/backups/changes/`. After the regression tests pass and the change is deployed, verify a fresh, comparable preflight record and its matching gateway decision trace. Report live recovery only when those traces show the required decisions answered without degradation; neither an active unit nor a passing offline test is sufficient.

## Triage Router reference drift without dispatching a duplicate Guardian repair

1. In `/walter/cognition/router`, run `git status --short` and `venv/bin/python -m pytest -q -p no:cacheprovider tests/test_documentation.py`. Inspect `git diff -- docs/reference` before writing anything. The reference freshness test runs offline; a failure is not evidence of a database or provider fault.
2. Compare the checked-in outputs with a fresh render in memory: `venv/bin/python -c "import sys,difflib; sys.path.insert(0,'tests'); import conftest; from walter_router import documentation,paths; g=documentation.render(documentation.collect(True)); [print('\n'.join(difflib.unified_diff((paths.ROOT/'docs/reference'/n).read_text().splitlines(),g[n].splitlines(),fromfile=n,tofile=n+' (rendered)',n=1))) for n in ('CODE.md','catalog.json')]"`. Compare the changed symbols and source hashes with `git log -p -- llm/gateway.py` when the diff points there. A dirty generated file can still be stale relative to a newer source commit. If generated outputs contain uncommitted work, leave them intact: do not run `walter-router docs --write` or manually edit the outputs to turn the test green.
3. Inspect `guardian/checks.py`, `guardian/repair.py`, and `guardian/run.py`. Give the `docs` incident sole ownership while the docs check reports drift: in `checks.detect`, suppress only the failure with the exact node ID `tests/test_documentation.py::test_generated_reference_is_current_without_private_data_or_a_db_call` while `docs()` reports staleness. In `run.still_broken`, apply the same handoff to already-open `test_failure` incidents for that node ID, so they cannot retry independently. Keep the dirty-output deferral in `repair.regenerate_docs`. Do not skip the pytest test itself or suppress unrelated failures; the node must be eligible for reporting again when the docs check is clear.
4. Run `venv/bin/python -m pytest -q -p no:cacheprovider tests/test_guardian.py`. Cover detection and rechecks, including that unrelated test failures remain visible and that the reference node is not suppressed when docs are current. Run `timeout 900 walter-router-guardian check` to verify detection and `walter-router-guardian status` to inspect recorded incidents; a check does not prove an older persisted incident has been reconciled. To verify the legacy path directly while drift remains, run `venv/bin/python -c "import sys; sys.path.insert(0,'tests'); import conftest; from walter_router.guardian import run,checks; print(checks.docs()); print(run.still_broken(None, {'kind':'test_failure','subject':checks.REFERENCE_TEST}))"`. Expect a docs finding and `False` for the duplicate recheck. Report the raw freshness test as still failing if regeneration is deferred, and keep unrelated suite failures separate.
