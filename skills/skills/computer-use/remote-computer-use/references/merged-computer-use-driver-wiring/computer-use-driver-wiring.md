---
name: computer-use-driver-wiring
description: "Use when auditing computer_use spawn, schema, or fresh-session routing."
version: 1.1.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [computer-use, cua-driver, backend, embedded-daemon, driver-command, permission-mode, wrapper-shim]
    category: desktop
    related_skills: [computer-use, cua-driver-resilience, walter-computer-use]
---

# Computer use driver wiring (spawn / embedding contracts)

## When to Use

Load this when investigating why Hermes' `computer_use` tool fails to start its
driver, when configuring a custom/remote driver command (including stdio
forwarder shims), or when tracing how `permission_mode` selects between the
local embedded daemon and the normal MCP path. Trigger phrases include
`embedded cua-driver exited during startup`, `remote driver subcommand is not
allowed`, a driver that works in `standard` but fails in `unrestricted` mode,
or any change around the plugin computer-use backend seam. Also load it when
REVIEWING a diff that touches the computer_use toolset (front door, approvals,
schema, backend registry, capture integrity) — see
`references/computer-use-tool-review.md` for the architecture map and the
security/logic review checklist with a worked Lot-1 example.

Also load it when a backend plugin changes the model-facing schema, plugin
precedence, prompt/skill injection, or the ordinary first device call in a
fresh gateway session. A process launch is not task completion: URL, native
window readiness, later interactions, and final verification require their own
evidence. See `references/fresh-session-model-routing.md` for the release gates,
completion invariant, loop protections, and post-task evidence accounting.

## Scope

Governs how Hermes' `computer_use` backend locates and spawns the driver
executable (`tools/computer_use/cua_backend.py`), what the "embedded daemon"
is, and how custom/remote driver commands (e.g. a stdio-forwarder shim) must
behave to stay compatible. GUI action semantics stay in `computer-use`;
capture/AX integrity lives in `cua-driver-resilience`; the Walter remote route
itself lives in `walter-computer-use`.

## The spawn contract

- Driver resolution: `resolve_cua_driver_cmd()` reads, in order,
  `HERMES_CUA_DRIVER_CMD` env (the bridge plugins use to pass a configured
  driver in) > PATH > canonical install paths (`~/.local/bin`, `~/.cargo/bin`,
  `/opt/homebrew/bin`, `/usr/local/bin`).
- `_resolve_mcp_invocation(driver_cmd)` discovers the MCP incantation by asking
  the driver itself: `<driver> manifest` → JSON with `mcp_invocation
  {command, args}` (trycua contract). Falls back to `[driver, "mcp"]` on any
  indeterminate failure — discovery must never block startup.
- Wrapper drivers can return a rewritten manifest with `command: ""`; Hermes
  then keeps the already-resolved local command and uses the manifest `args`
  verbatim. That is exactly how a local shim keeps control of a remote MCP
  process while still benefiting from manifest-driven subcommand evolution.
- `--no-overlay` is appended when `computer_use.no_overlay` is on and `<driver>
  --help` advertises it (probed once, cached).

## The embedded daemon contract (permission_mode == "unrestricted")

- When a session has approval-bypass / YOLO active, `_cua_permission_mode()`
  returns `"unrestricted"`, and `CuaDriverBackend.__init__` constructs
  `_EmbeddedCuaDaemon(driver_cmd, "unrestricted")` to isolate the choice in a
  private daemon process + socket rather than reusing a machine-wide daemon.
- `_EmbeddedCuaDaemon.start()` launches the exact bounded contract:

  `[driver, serve, --embedded, --socket, /tmp/hc-<token>.sock,
    --no-permissions-gate, --permission-mode, unrestricted,
    --dangerously-bypass-approvals]`

- The MCP proxy then connects with `[driver, <manifest args>, --embedded,
  --socket, <path>]`; the CLI fallback calls `[driver, call, <name>, <json>,
  --socket, <path>]`.
- A remote Walter shim may support this contract when it forwards the exact
  bounded `serve` invocation to the enrolled Mac, where the socket is created
  and checked. Do not classify `serve` as inherently local; classify the
  configured command by its declared transport and target-daemon contract.
- The shim must not accept arbitrary remote flags. Its `serve` route needs
  per-verb validation for `--embedded`, `--socket`,
  `--no-permissions-gate`, `--permission-mode unrestricted`, and
  `--dangerously-bypass-approvals`, plus bounded validation for `status` and
  `stop`.
- A remote manifest may legitimately return `mcp_invocation.command=""` and
  `args=["mcp"]`. Hermes keeps the already-resolved shim and uses those args;
  it must never execute the Mac's absolute `binary_path` on the VPS.

## Failure signature

- Backend raises: `RuntimeError("embedded cua-driver exited during startup:
  <stderr tail>")`.
- A bounded-verb shim rejects the `serve` subcommand at argv-allowlist
  validation and BEFORE any transport: `"<name>: remote driver subcommand is
  not allowed"` on stderr, exit 2 — reproducible locally/offline, no network
  needed.
- Only the unrestricted path fails; `permission_mode="standard"` (no embedded
  daemon) goes through manifest + `mcp` verbs and works. A failure specific to
  the unrestricted path is the diagnostic: the driver can't host the embedded
  daemon.

## Rules for custom/remote driver commands

1. Treat embedded-daemon verbs as a contract question, not as inherently
   local-only. A remote shim may forward `serve` when the daemon is actually
   created on the enrolled GUI host and the socket/lifecycle contract is
   coherent end-to-end. Do not prohibit the verb merely because the caller
   runs on a VPS.
2. Bound the remote `serve` contract before any SSH dispatch. For Hermes'
   unrestricted path, accept only the exact bounded shape:
   `serve --embedded --socket <safe-absolute-path> --no-permissions-gate
   --permission-mode unrestricted --dangerously-bypass-approvals`. Reject
   unknown or duplicate flags, missing required flags, unsafe socket paths, and
   every permission mode except `unrestricted`; similarly bound `status` and
   `stop` to an optional validated socket.
3. Preserve the official permission semantics. The flow is
   `_cua_permission_mode(session)` → `factory(permission_mode=...)` →
   `CuaDriverBackend.__init__`. Do not silently coerce an explicit
   `permission_mode="unrestricted"` to `standard`: that removes the user's
   accepted YOLO semantics and hides a transport incompatibility. If the shim
   cannot implement the exact bounded serve contract, return an explicit
   compatibility error or require an explicit policy decision instead.
4. Keep manifest and executable boundaries separate. A remote manifest may
   return `mcp_invocation.command=""` and `args=["mcp"]`; Hermes must retain
   the already-resolved local shim, use the remote args, and never execute the
   Mac's absolute binary path on the VPS.
5. Debug in two stages: reproduce the exact argv offline against the shim's
   validator, then run both standard (`manifest → mcp`) and unrestricted
   (`serve → private socket → mcp`) smoke paths. Verify `status`/`stop`, the
   remote target daemon, and the real GUI/TCC gate separately.

See `references/remote-shim-bounded-serve.md` for the bounded contract,
reproduction recipe, and evidence checklist.

## Pitfalls

- The embedded daemon long predates the plugin-factory seam
  (`register_backend_factory` / `register_computer_use_backend`); a change that
  newly routes `permission_mode` into plugin factories can surface this for
  any custom driver with zero core diff.
- Do not read "remote driver subcommand is not allowed" as a shim bug — it is
  a deliberate fail-closed allowlist (the shim author usually pins it with a
  contract test). The incompatibility is on the caller side.
- Testing only `standard` leaves the unrestricted path broken for YOLO
  sessions. Add a regression test asserting
  `_factory(permission_mode="unrestricted")` yields a backend whose
  `_embedded_daemon is None`.

## Reference

See `references/hermes-embedded-daemon-remote-shim.md` for a complete traced
audit: exact file/line positions, the full invocation chain, reproduced argv,
tests present, and rejected alternatives.

For a read-only inventory of the REMOTE macOS cua-driver capability surface
(which MCP tool primitives exist, which are derived-only vs. missing —
clipboard, direct frontmost state, user-presence sensors — and where the
authoritative schema/dispatch evidence lives on disk), see
`references/remote-cua-capability-surface.md`.
