# Walter Computer

Atomic desktop operations shared by agent harnesses. The calling harness owns the
user goal, planning loop and permission decisions. This module owns target
selection, presence/interruption policy, snapshot and visual-reference guards,
bounded recovery, observations, and the CuaDriver protocol port.

## Boundaries

- `walter_computer.policy`, `runtime`, `observer`, `types`: independent core;
  no Hermes, DSH, Codex or Claude imports.
- `operator`, `driver`, `transport`: independent session API and CuaDriver port.
- `ports/hermes`: configuration translation, host approval/lease/dispatch/result
  bridge. Public `register_tool(override=True)` is used on Hermes versions without
  backend extension registration. The original tool name/schema is retained and
  atomic Walter actions are appended. `allow_tool_override` is an explicit
  operator-owned setting. No Hermes checkout files are modified.
- `/root/walter-computer-use`: declared device-node transport dependency, not a
  harness dependency. Its SSH shim validates the enrolled device route and keys.
  `/root/.config/walter-device-node/remote-cua.json` and the key files it references
  must be included in encrypted backup coverage.

The `capture`, `input`, `parse`, and basic type code originates in the installed
NousResearch Hermes CuaDriver adapter and is now pinned module-owned source, with
`LICENSE.hermes` and exact revision/source hashes in `UPSTREAM.json`. There is no
runtime import from that checkout. Future upstream updates require deliberate
port review and tests; they do not overwrite this module.

## Stable Python interface

```python
from walter_computer.config import make_operator
from walter_computer.operator import OperatorSessions

sessions = OperatorSessions(make_operator)
result = sessions.call(
    "client-owned-session-id", "list_apps", {}, grants={"read"}
)
sessions.close()  # call on client shutdown
```

`call` is synchronous. An async MCP server should run it in a worker thread.
Session IDs must be namespaced by the authenticated caller/profile. State is
isolated per session. Calls in one pool are serialized. Pools are bounded to 16
sessions and discard entries idle longer than 15 minutes before processing a
new call. `close` is an action and also a pool method.

`grants` is trusted **per-call host policy**, not arbitrary unverified model
output. Missing scopes return `authorization_required` before backend startup.
All calls require `read`; input actions additionally require `input`; visible
foreground/focus requires `foreground`. Capture, targeted verification and
launch/open URL (which observe the resulting window) require `pixels`, because
the current driver may produce pixels with AX. `vision_target` also requires
`vision`, and an injected vision sensor. `mode=ax` suppresses the image in the
returned result. No global allow-all or persistent grant is created.

Actions: `list_apps`, `list_windows`, `capture`, `click`, `drag`, `scroll`, `type`,
`key`, `set_value`, `focus_app`, `wait`, `launch_app`, `open_url`, `device_context`,
`vision_target`, `click_visual_ref`, `targeted_verify`, `close`.
`capture` defaults to AX. Use `x/y` for clicks, `from_xy/to_xy` for drags;
`type` takes `text`. Native Hermes keeps its own `coordinate` schema and dispatch.
No generic raw driver-call escape hatch is exposed by the facade.

Transport failures never replay actions. Failed capture clears the prior target.
Only a snapshot returned to the caller arms native references. Screenshot and
vision contents are user data; the MCP adapter owns privacy filtering/redaction
and must not ship them to another model without authorization.

## Configuration and deployment

`config.json` owns the standalone route. The Hermes port translates its current
profile config at construction, preserving the configured route, observer and
permission mode. Module code supports Python >=3.11 and uses only stdlib; the
separately declared device-node source is loaded only when a real independent
transport is constructed. `bin/walter-computer check` performs no desktop or
network call.

Hermes compatibility is tested at registration and call-contract signatures. If
its private dispatch/approval helper contract changes, this port fails explicitly
rather than selecting a different backend. All private host calls are isolated
inside `ports/hermes.py`.

## Evidence and limits

Tests use fake CuaDriver frames and synthetic windows. They prove independent
imports, captured target/token routing, stale-ref refusal, failed-capture disarm,
no transport creation on missing grants, separate foreground/pixel scopes,
session isolation/cleanup, no replay on completion-unknown, and the actual
installed Hermes type/schema/approval/lease boundary.

No real Mac screenshot, input or end-to-end desktop task was executed during
this extraction. A later explicitly requested desktop operation is still needed
to prove current Mac permissions and live driver behavior. The independent port
supports one fixed enrolled CuaDriver route; it does not claim universal device
registration. Cross-process clients rely on driver snapshot tokens; pool locking
is process-local. The independent port's auxiliary vision sensor is injectable
and unavailable until a client supplies one. Hermes retains its existing sensor.
