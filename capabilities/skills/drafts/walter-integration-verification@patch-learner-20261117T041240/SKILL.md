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
