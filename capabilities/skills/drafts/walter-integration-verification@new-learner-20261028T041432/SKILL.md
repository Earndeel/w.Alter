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
