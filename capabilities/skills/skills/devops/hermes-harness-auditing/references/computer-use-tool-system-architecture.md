# Hermes Computer Use tool-system — architecture map & audit anchor points

Condensed, code-verified map of the Hermes `computer_use` tool system and the
Walter plugin backend, produced from a read-only audit of the worktree
(`tools/computer_use/`, plugin `~/.hermes/plugins/walter-computer-use/`,
shim repo `~/walter-computer-use/`). Line anchors are from the audited
worktree and drift; re-grep before citing in a fresh report.

## Component map (read order for an audit)

- `tools/computer_use/schema.py:16-348` — the single OpenAI function-calling
  schema, one `computer_use` tool with an `action` discriminator (26 actions,
  incl. 10 namespaced `cua_browser_*`). Model-agnostic.
- `tools/computer_use/tool.py:469` `handle_computer_use` — entry/dispatch:
  safety gates (blocked key combos `tool.py:97-110`, blocked type patterns
  `:129-143`), approval gate `:508-521`, backend fetch `:224-294`, dispatch
  `:619-817`, verdict classification `:824-869`, response shaping/capture
  envelope + aux-vision routing `:964-1109`.
- `tools/computer_use/backend.py` — `ComputerUseBackend` ABC `:184-322` and
  the plugin extension registry `register_backend_factory` `:32-57`
  (reserved names `cua`/`cua-driver`/`noop` `:44`). `ActionResult` carries
  the driver's structured verdict (effect/escalation/path/code) `:143-181`.
- `tools/computer_use/cua_backend.py` — `CuaDriverBackend` `:2005-3427`:
  driver resolution `resolve_cua_driver_cmd` `:763-779`, MCP over stdio via
  `_CuaDriverSession` `:1112-1746` (lazy, capability discovery from
  tools/list `:1259-1303`), embedded daemon for unrestricted mode
  `_EmbeddedCuaDaemon` `:418-570`, capture `:2318-2685`, delivery ladder
  `_apply_delivery`/`_run_input_action` `:2688-2778`, typed-browser adapter
  `:3122-3138`.
- `tools/computer_use/browser_route.py` — `CuaTypedBrowserRoute` `:179-573`:
  exact-bind gate, session-scoped refs, mutation invalidation.
- `tools/computer_use/vision_routing.py` + tool.py:1165-1200 — capture →
  main-model multimodal vs `auxiliary.vision` pre-analysis decision
  (fails closed toward aux).
- `tools/computer_use/doctor.py` (health_report client + composite fallback),
  `permissions.py` (status + mac-only grant).
- Core seam: `hermes_cli/plugins.py:524` `register_computer_use_backend`.

## Backend selection & session lifecycle (the plumbing to trace)

1. Name resolved: env `HERMES_COMPUTER_USE_BACKEND` → `config.yaml`
   `computer_use.backend` → default `"cua"` (`tool.py:202-221`).
2. Registry lookup `get_backend_factory` (`backend.py:59-67`); built-in
   branches `cua`/`noop` (`tool.py:263-268`); unknown name → RuntimeError.
3. One backend per session_id, cached under `_backends`, per-session
   api-permission mode `_cua_permission_mode` (`tool.py:172-199,224-294`);
   `/yolo` toggle swaps only that session's backend; `release_computer_use_session`
   + atexit teardown stop daemons.
4. `start()` lazy-installs the `mcp` dep, spawns the driver, `start_session`,
   applies max_image_dimension + cursor-overlay off.

## Walter plugin — delivered vs gap (verified)

- Backend lives at plugin `__init__.py`; `WalterCuaBackend` extends
  `CuaDriverBackend` (`__init__.py:301-434`): safe-window target strategy
  (`:115-170`), capture-integrity marking (`:272-298`), one bounded
  element→pixel retry gate (`:368-434`).
- `register()` validates `driver_command` (absolute, single-link, owner,
  mode) and bridges it via `HERMES_CUA_DRIVER_CMD` (`__init__.py:207-231,
  450-462`) → consumed by core at `cua_backend.py:727-744`.
- Shim `remote_driver.py` (walter_device_node package): strict OpenSSH argv
  `:180-226`, manifest rewrite `:229-263`, allowlisted subcommands
  `_ALLOWED_SUBCOMMANDS` `:26-28`.
- Test evidence: core computer-use suite **22 passed/1 skipped**; delivery
  ladder + typed browser **54 passed**; Walter plugin **13 passed**.
  All unit/contract; live remote-Mac path not executable on the VPS.

## Concrete gap: Walter backend × unrestricted (YOLO) mode

- `CuaDriverBackend.__init__` builds `_EmbeddedCuaDaemon` whenever
  `permission_mode == "unrestricted"` (`cua_backend.py:2012-2016`), and the
  daemon spawns the `serve` subcommand (`cua_backend.py:477-487`).
- The Walter shim's `_ALLOWED_SUBCOMMANDS` does **not** include `serve`
  (`remote_driver.py:26-28`).
- ⇒ `computer_use.backend: walter` + Hermes `/yolo` fails `backend.start()`
  (shim exits 2) instead of degrading; only `standard` mode works over SSH.
  Code-verified; not covered by any plugin test. Recommend a target fix/test.
