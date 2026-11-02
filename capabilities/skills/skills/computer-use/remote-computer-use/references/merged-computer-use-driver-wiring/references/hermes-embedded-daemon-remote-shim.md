# Traced audit: embedded cua-driver daemon vs remote stdio shim

Session-specific evidence behind `remote-computer-use`. Findings from an
audit of the reported startup failure:

> `embedded cua-driver exited during startup: walter-cua-remote: remote driver
> subcommand is not allowed`

(Invocations are `walter-cua-remote` = the walter plugin's remote shim; the
pattern applies to ANY bounded-verb driver shim.)

## Exact invocation chain (file:line at audit time)

1. `tools/computer_use/tool.py:_cua_permission_mode(session_id)` returns
   `"unrestricted"` when `is_approval_bypass_active_for_session()` is true
   (YOLO / approval-bypass session).
2. `_get_backend()` resolves `_configured_backend_name()` → `"walter"` and
   calls the plugin factory: `factory(permission_mode="unrestricted")`
   (uncommitted seam: tool.py `_get_backend`, `backend.py
   register_backend_factory`, `hermes_cli/plugins.py
   register_computer_use_backend`).
3. Plugin `/root/.hermes/plugins/walter-computer-use/__init__.py:_factory`
   → `WalterCuaBackend(permission_mode=permission_mode)` — passes through
   unguarded.
4. `CuaDriverBackend.__init__` (cua_backend.py ~2012) builds
   `_EmbeddedCuaDaemon(resolve_cua_driver_cmd() or "", "unrestricted")`.
   `resolve_cua_driver_cmd()` returns `HERMES_CUA_DRIVER_CMD` =
   `/root/walter-computer-use/.venv/bin/walter-cua-remote` (set by plugin
   `register()`).
5. `_EmbeddedCuaDaemon.start()` (cua_backend.py ~466) calls
   `_resolve_mcp_invocation` (manifest round-trip over SSH — works), then
   IGNORES the resolved args and hardcodes:

   ```
   walter-cua-remote serve --embedded --socket /tmp/hc-<token>.sock \
     --no-permissions-gate --permission-mode unrestricted \
     --dangerously-bypass-approvals
   ```

6. Shim `main()` → `build_ssh_argv(config, ("serve", ...))` →
   `"serve" not in _ALLOWED_SUBCOMMANDS` → `ValueError("remote driver
   subcommand is not allowed")` (remote_driver.py ~183), printed to stderr,
   exit 2 — rejected at argv validation, BEFORE any SSH.
7. Daemon startup loop sees the exit, drains stderr tail, raises the reported
   RuntimeError.

## Verified reproduction (offline, safe)

```bash
/root/walter-computer-use/.venv/bin/walter-cua-remote serve --embedded \
  --socket /tmp/hc-test.sock --no-permissions-gate \
  --permission-mode unrestricted --dangerously-bypass-approvals
# -> walter-cua-remote: remote driver subcommand is not allowed; exit=2
```

The allowlist contract test pins this deliberately:
`tests/test_remote_driver.py::test_remote_driver_rejects_unknown_or_unbounded_invocation`
asserts `("serve", "--no-permissions-gate")` RAISES. `docs/operations.md` row
documenting the message: "Use only the shim's declared bounded verbs; Hermes
uses `manifest` and `mcp`".

## Verified contract-compatible fix

The initial audit recommendation to force Walter's factory back to
`permission_mode="standard"` was not applied. The remote shim was instead
extended with a bounded `serve` contract matching Hermes' real unrestricted
invocation, and this path was exercised successfully against the enrolled Mac.

The shim now validates and forwards only the required shape:

```text
serve --embedded --socket /tmp/hc-<token>.sock \
  --no-permissions-gate --permission-mode unrestricted \
  --dangerously-bypass-approvals
```

It also bounds `status`/`stop` socket use and rejects unsupported or duplicate
flags. The standard path remains manifest → `mcp`; the unrestricted path uses
`serve` → private socket → `mcp --embedded --socket`.

The remote manifest contract remains fail-closed: `mcp_invocation.command` is
rewritten to empty, Hermes retains the local shim, and the remote Mac absolute
binary path is never executed on the VPS.

Rejected:
- Coercing the factory to `standard`: this would silently remove the user's
  explicit YOLO/approval-bypass semantics rather than fixing the official
  transport contract.
- Allowing arbitrary `serve` arguments: this would forward unbounded
  permission-bypass flags over SSH.
- Special-casing `_EmbeddedCuaDaemon`/`_get_backend` in core: the shim's
  explicit contract is the correct edge seam.

## Tests present (at audit time)

- Hermes `tests/tools/test_computer_use_cua_0_10_permissions.py`:
  `test_unrestricted_embedded_daemon_uses_private_socket_and_two_part_ack`
  (pins `[cmd, "serve", ...]` with `"cua-driver"` — does NOT cover shim
  drivers), `test_standard_backend_does_not_spawn_an_embedded_daemon` (`standard
  _embedded_daemon is None`, `unrestricted` is not).
- Plugin `test_walter_computer_use.py` (11 tests): strategy, driver-command
  validation, register→env bridge, click retry loop. **No
  permission_mode/_factory guard test (gap).**
- Shim `tests/test_remote_driver.py` (12 tests) incl. allowlist rejection,
  manifest rewrite, config fail-closed.

## Git state note

`/root/.hermes/hermes-agent` carries uncommitted diffs adding the plugin
backend-factory seam (backend.py `_BACKEND_FACTORIES`, plugins.py
`register_computer_use_backend`, tool.py `_get_backend` factory dispatch) —
this is what newly routes `permission_mode` into plugin factories. The
`_EmbeddedCuaDaemon` class itself exists on `HEAD` (not part of the diff).
`/root/.hermes/plugins/walter-computer-use` and `/root/walter-computer-use`
are plain directories, not git repos.
