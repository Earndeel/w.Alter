# Task-bound foreground approval

Use this reference for a legacy Mac pixel driver that is reachable through a
loopback HTTP tunnel. The goal is to prevent W.Alter from interrupting a user
who is working on the Mac while still allowing fully invisible/background
operations to run without a prompt.

## State model

```text
closed
  -> request-control(task_id, reason)
  -> user approves
approved(task_id, approval_token)
  -> visible actions / heartbeat touch last_activity
  -> release-control, idle timeout, hard maximum, restart, or user refusal
closed
```

There must be at most one foreground lease at a time. A request for a different
active task is `control_busy` and must not take over or replay an action. A
wrong token is not a reason to retry the mutation; stop and reacquire approval.

## HTTP contract

All query values must be URL-encoded.

| Endpoint | Required fields | Expected behavior |
|---|---|---|
| `/request-control` | `task_id`, `reason` | Displays a native approval dialog. On approval returns `approval_token`; on refusal/timeout returns `403`. |
| `/control-heartbeat` | `task_id`, `approval_token` | Refreshes inactivity timer. It never performs GUI input. |
| `/release-control` | `task_id`, `approval_token` | Explicitly closes the lease. Call it in `finally`/cleanup. |
| `/control-status` | — | Read-only status; must never display a dialog. |
| `/health` | — | Read-only health/version check; must never display a dialog. |
| `/screenshot` | — | Read-only capture; must never display a dialog. |

Visible action endpoints (`click`, `doubleclick`, `rightclick`, `type`, `key`,
`combo`, `scroll`, `drag`) must carry the same `task_id` and, when available,
`approval_token`. A server may bind a compatibility caller without an explicit
ID to an `implicit` task, but new clients should always provide a stable ID.

Only a genuinely invisible operation may carry `background=1`. This is an
explicit trust boundary, not a UI convenience flag: never add it just because
the user did not answer quickly. Background mode must not move the cursor,
change focus, type, press keys, or mutate the visible desktop.

## Timeouts

Use two different safety timers:

- **idle timeout**: closes the lease when no action or heartbeat occurs; it
  protects against an abandoned/crashed task;
- **hard maximum**: absolute upper bound even if heartbeats continue; it limits
  damage from a stuck or compromised client.

The verified W.Alter implementation defaults to 60 seconds idle and 600 seconds
hard maximum. These are safety defaults, not the task duration. Explicit release
is the normal end condition. If a task can be quiet for longer than the idle
window, heartbeat from the orchestrator while it is still active rather than
stretching the normal lease indefinitely.

## Verification without side effects

After deployment or restart:

1. `GET /health` and assert the expected version and approval model.
2. `GET /control-status` and assert `approved=false`.
3. `GET /screenshot`; validate HTTP `200`, `image/png`, PNG signature, and a
   plausible non-black frame. Do not use file size alone as proof of capture.
4. Request a dedicated test task with a reason stating that no action follows.
5. Have the user approve or refuse the native dialog; never automate the
   permission click.
6. If approved, call only `/control-heartbeat`, then `/release-control`.
7. Assert the final status is closed. Do not call `/click` with a harmless-looking
   coordinate: a coordinate is still a real side effect.

A health response, a valid PNG, and a successful approval are separate checks;
none substitutes for the others. Keep the remote backup and validate the
remote interpreter before replacing the LaunchAgent target.

## Failure semantics

- `403 control_denied` / `control_not_active`: do not replay a side effect;
  obtain fresh approval or stop.
- `409 control_busy`: another task owns the foreground lease; release/coordinate
  explicitly rather than taking over.
- network timeout after a mutation: completion is unknown; never retry the
  click/type automatically.
- server restart: treat the lease as closed and request approval again.

The prompt should identify the task and human-readable reason, state that the
authorization applies to that task, and explain idle/hard expiry. It should not
promise that a later action is invisible when it changes the user's screen.
