# Remote macOS cua-driver capability surface (read-only audit)

How to inventory the EXACT cua-driver capabilities exposed to a Walter Operator
remote Mac, and which primitives exist vs. are derived-only vs. are missing.
Use this to answer "can Walter do X on the remote Mac?" without SSHing to the
Mac — all evidence is on the VPS/Linux side.

## What is the remote transport

- Shim: `/root/walter-computer-use/.venv/bin/walter-cua-remote` →
  `walter_device_node.remote_driver:main`.
- Fixed-subcommand allowlist (fail-closed): `manifest mcp serve status stop
  check-update call list-tools describe permissions doctor diagnose version
  --version` (`remote_driver.py:_ALLOWED_SUBCOMMANDS`). `call <tool> <json>` is
  the primitive that reaches driver tools.
- `build_ssh_argv()` → OpenSSH (`BatchMode=yes`, pinned known_hosts, Tailscale)
  → `remote_driver_path` (e.g. `/Users/<user>/.local/bin/cua-driver`) + args.
- Endpoint config: `/root/.config/walter-device-node/remote-cua.json`
  (fields: host, username, identity_file, known_hosts_file, remote_driver_path,
  ssh_path, connect_timeout_seconds). VPS-side driver config:
  `/root/.cua-driver/config.json`.

## Where the authoritative tool schema + dispatch live (on disk)

1. **Schema fixture**: `hermes-agent-*/tests/fixtures/cua_driver_0_9_tools_list.json`
   — `contract_epoch=cua-driver-0.9`, normalized subset; `tools[]` has
   `name`, `inputSchema.properties`, `inputSchema.required`.
2. **Backend dispatch**: `tools/computer_use/cua_backend.py` — actual
   `_action/_run_input_action/_call_capture_tool(...)` tool-string literals and
   their argument dicts. This is the source of truth for which tools Hermes
   actually invokes and with what params.
3. **Health/permission probes**: `tools/computer_use/doctor.py` (calls
   `health_report`, `check_permissions`, `list_apps`), `tools/computer_use/permissions.py`.
4. **Verifier postconditions**: `walter-computer-use/src/walter_device_node/macos_verifier.py`
   (field expectations like `desktop_unlocked`, `screenshot_frame_valid`,
   `is_on_screen`).
5. **Presence/foreground tracking**: the Walter plugin `observer.py` —
   distinguishes REAL driver-sourced fields vs. derived/aspirational counters.

## Capability matrix (as-of audit; re-verify against current schema)

Present (dispatched + in schema):
- Pointer: `move_cursor`, `get_cursor_position`, `get_screen_size`; agent-cursor
  overlay: `set_agent_cursor_enabled/motion/style`, `get_agent_cursor_state`.
- Input: `click`, `double_click`, `type_text`, `hotkey`/`press_key`,
  `set_value`; `drag` (from/to_element or from/to_coordinate, `from_zoom`);
  `scroll` (direction/amount, element_index or x/y — coordinate-scroll gated by
  `input.scroll.coordinates` capability).
- Capture/crop: `get_window_state` (window PNG + AX `elements` +
  `screenshot_frame_valid`/`screenshot_error`/coverage); legacy `screenshot`
  kept as fallback; region via `zoom(window_id,x,y,w,h)` — window-scoped only,
  no free-region crop tool.
- App/window: `launch_app`, `focus_app`, `list_apps`, `list_windows`,
  `kill_app`, `bring_to_front`, `start_session`/`end_session`.
- Health/permission: `health_report`, `check_permissions` (→ `accessibility`,
  `screen_recording`, `screen_recording_capturable`), `list_apps` probe, and
  CLI `doctor`/`diagnose`/`permissions`/`status`/`check-update`.
- Presence gate: `desktop_unlocked` on `list_windows`/`get_window_state`.

Missing / derived-only:
- Clipboard: NO read/write tool (`read_clipboard`/`set_clipboard`/`paste`
  absent from schema and dispatch).
- Direct frontmost/foreground state: no `get_frontmost`/`get_active_window`
  tool — only derived via `list_windows` z-order, `focus_app`,
  `bring_to_front`.
- User-presence sensors beyond lock state: observer declares
  `idle_duration`/`recent_keyboard_activity`/`recent_pointer_activity`/
  `user_active`/`foreground_app` but these are aggregation counters with NO
  driver tool feeding them (only `desktop_unlocked` is real).

## Audit method (repeatable, read-only)

1. Read the shim allowlist + `build_ssh_argv` to know the reachable surface.
2. Grep `cua_backend.py` for tool-string literals + their arg dicts
   (`grep -rhoE '"..."'` then map to action methods).
3. Read the schema fixture for required/optional props per tool.
4. Check `doctor.py` + `macos_verifier.py` + plugin `observer.py` for what is
   truly source-fed vs. declared-but-unfed.
5. Distinguish "real primitive" (a driver tool returns it) from "derived"
   (computed from another tool's output) from "missing" (no tool, no derivation).
