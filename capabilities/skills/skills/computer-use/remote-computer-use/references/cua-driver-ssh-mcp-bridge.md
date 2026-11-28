# CuaDriver stdio MCP bridge over SSH

Use this when Hermes runs on a VPS and the signed CuaDriver daemon runs in the
Mac user's GUI session. The goal is one long-lived stdio MCP process whose
stdin/stdout traverse SSH, not one new SSH process per tool call.

## Wrapper

Create an executable wrapper on the VPS; keep host, user, and driver path in
the deployment's protected configuration rather than in a skill or prompt:

```bash
#!/usr/bin/env bash
set -euo pipefail

# A remote manifest can contain a Mac-only absolute command path. Returning
# failure makes Hermes use its documented fallback: this wrapper plus `mcp`.
if [[ "${1:-}" == "manifest" ]]; then
  exit 1
fi

exec ssh -T \
  -o BatchMode=yes \
  -o ConnectTimeout=8 \
  -o ServerAliveInterval=10 \
  -o ServerAliveCountMax=3 \
  -o ClearAllForwardings=yes \
  <mac-user>@<mac-tailscale-ip> \
  <mac-cua-driver-absolute-path> "$@"
```

Point the existing Hermes override at the wrapper:

```bash
HERMES_CUA_DRIVER_CMD=/absolute/path/to/cua-driver-mac-remote
```

The override must resolve to an executable path. Do not put a shell pipeline
or a multi-word command in it; the Hermes resolver probes the path and then
spawns it with `manifest`, `mcp`, and driver flags.

## Verification order

1. Run the wrapper's `--help`; then confirm `manifest` exits non-zero so Hermes
   falls back to `wrapper mcp` rather than spawning a Mac-only path on the VPS.
2. Run the Mac-side read-only checks through the target's signed daemon:
   `permissions status --json`, `health_report`, `list-tools`, and one AX/window
   read. The VPS binary being installed is not proof of Mac capability.
3. Run Hermes' actual backend, not only a raw CLI smoke test:

   ```python
   from tools.computer_use.cua_backend import CuaDriverBackend

   backend = CuaDriverBackend()
   try:
       backend.start()              # measure this one-time cost separately
       print(backend.get_screen_size())
       print(backend.list_windows())
   finally:
       backend.stop()
   ```

4. Benchmark repeated AX/window-state calls and full screenshots separately.
   Report p50/p95, payload bytes, and whether a semantic postcondition was
   actually verified. Do not compare a valid Cua screenshot with a legacy
   black PNG as if they were equivalent outputs.
5. Run the same checks with the Mac GUI unlocked and locked. A standard Cua
   session returning `desktop_escalation_required`, `desktop_unlocked=false`,
   or `ax_window_unresolved` is a safety refusal/state blocker, not a reason to
   force foreground input or retry a pixel mutation.

## Observations that matter

- `permissions status --json` can report Accessibility/Screen Recording true
  while the current GUI session is locked or the requested window has no
  addressable AX surface. Always perform a real capture and a scoped AX read.
- CuaDriver's native AX path is normally the low-latency path. Full-screen
  capture still pays image encoding and SSH/MCP transport costs; optimize by
  using AX/window reads first and scoped pixels only when needed.
- A legacy screen server may appear faster because it returns a tiny black
  frame. Compute a non-black/content signal before sending any frame to a
  vision model or acting on coordinates.
- Keep the legacy pixel server on its own port during migration. Never
  automatically replay a mutation through the second driver after an unknown
  network completion.
- The raw Cua surface should remain a validation/migration surface; the
  permanent Hermes prompt should use the generic `computer_use` route with
  session-scoped tokens, stale-reference refusal, and post-action verification.

## Failure handling

- SSH connection failure: validate the direct Tailscale route and GUI launchd
  before changing CuaDriver or TCC.
- Manifest failure: expected for the wrapper; do not “fix” it by exposing a
  Mac absolute path to the VPS.
- MCP startup failure: inspect stderr and run the wrapper directly; distinguish
  MCP dependency/version issues from the remote daemon's health/TCC state.
- Black/empty capture: stop before vision or mutation; check signed daemon
  identity, capture dimensions, pixel signal, lock/sleep state, and restart the
  permission-owning daemon if its TCC state is stale.
- `unverifiable` or unknown completion: obtain fresh state first; never replay
  the same action automatically.
