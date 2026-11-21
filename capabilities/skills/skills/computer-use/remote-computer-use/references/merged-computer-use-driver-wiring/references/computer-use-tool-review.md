# Reviewing computer_use tool diffs (Hermes)

Use when auditing/reviewing changes to `tools/computer_use/*`, the plugin backend
seam (`PluginContext.register_computer_use_backend`), config
`computer_use.backend`, or their tests — e.g. phased "Lot" audits. Repo path:
`/root/.hermes/hermes-agent` (do NOT assume `/workspace/...`). Always inspect the
real diff (`git diff -- <files>`) — never trust a hand-written diff summary.

## Architecture map (single model-facing front door)

- `tools/computer_use_tool.py` → `tools.registry.register(name="computer_use", ...)`
  with `COMPUTER_USE_SCHEMA` + `handle_computer_use`. There is exactly ONE
  model-facing tool; new capability = a new `action` enum entry, never a new tool.
- `schema.py` — `COMPUTER_USE_SCHEMA`, `get_computer_use_schema()`. All actions
  share one flat property set (a property used by one action is visible to all).
- `tool.py` — `handle_computer_use` dispatch; `_SAFE_ACTIONS` vs
  `_DESTRUCTIVE_ACTIONS`; `_request_approval`; `_get_backend` (per-session cache +
  permission-mode). `_summarize_action` must cover every new action.
- `backend.py` — `ComputerUseBackend` ABC + the extension registry
  (`register_backend_factory` / `get_backend_factory` / `registered_backend_names`)
  and optional native hooks (`launch_app`, `open_url`, `kill_app`,
  `verify_state`, `execute_goal`) whose DEFAULT is a fail-closed refusal.
- `cua_backend.py` — default backend; speaks MCP over stdio to `cua-driver`.
  `permission_mode` flows `_cua_permission_mode(session)` → factory → `__init__`
  (see the parent skill for the embedded-daemon / unrestricted contract).
- `hermes_cli/plugins.py` — `PluginContext.register_computer_use_backend` seam.
- `hermes_cli/config_defaults.py` — `computer_use.backend` (default `"cua"`),
  `capture_strategy`.

## Review checklist

1. **Single front door.** Confirm new capability is an enum action under the same
   tool, not a second registration. Assert `schema action enum ⊆ _SAFE_ACTIONS ∪
   _DESTRUCTIVE_ACTIONS` (no orphan action lacking a safety classification).
2. **Approval gating / bypass.** Every mutating action must be in
   `_DESTRUCTIVE_ACTIONS`; read-only in `_SAFE_ACTIONS`. The tool-level local
   approval callback MUST consult `tools.approval.is_approval_bypass_active_for_session`
   BEFORE firing the callback — otherwise `--yolo` / `approvals.mode=off` still hit
   the local callback and block (false negative). Conversely, a failure of that
   central lookup must NOT become an implicit bypass (catch → fall through to the
   normal callback path). Session key `""` returns False (no bypass) — a safe
   default under any key derivation change.
3. **Fail-closed geometry.** Raw pixel coordinates must be validated against fresh
   geometry of the exact pid/window pair before the driver is called: reject
   bool/non-int values, negative, out-of-bounds (the exclusive right/bottom edge:
   `x >= width`), stale/missing target, absent geometry. The geometry record must
   be cleared on AX-only capture, on target change, and on any failed capture.
   Crucially: verify the tests SEED that geometry evidence explicitly instead of
   deleting the guard to make a past fixture pass — wiping the guard is a coverage
   regression in disguise.
4. **Driver payload shapes.** Newer cua-driver returns payload at the TOP level,
   not only inside `structuredContent`; helpers (`_tool_payload`,
   `_tree_text_from_tool_result`) must prefer a real structuredContent dict but
   fall back to the response itself, else AX elements/diagnostics are lost.
   `_split_tree_text` must not discard the first AX node when text leads with
   `- [` / `AXWindow` / `AXApplication`. Invalid frames
   (`screenshot_frame_valid=False` or `screenshot_error`) must never surface as a
   valid screenshot; keep AX elements when they survived the bad pixels.
5. **Backend registry fail-closed.** Reserved names (`cua`, `cua-driver`, `noop`)
   rejected at registration; duplicate registration rejected (unless identical
   callable); callable type-checked; RLock-protected; `_get_backend` resolves the
   factory BEFORE the built-in name branch and type-checks the instance.
6. **Schema↔dispatch consistency (the sneaky one).** Every arg `_dispatch` reads
   must exist in the schema — schema-strict providers strip undeclared properties,
   so a model call silently loses the arg and the tool errors. Found in the wild:
   `launch_app` accepts `name` but the schema only declares `bundle_id`; and
   urls-only `launch_app` is allowed in `cua_backend` but blocked in `_dispatch`.
7. **Degraded-but-safe.** A capability advertised to the model but permanently
   unavailable on the configured backend (e.g. `action='goal'` with the built-in
   `cua` backend, which returns `route_unavailable`) is fail-closed but a
   dead-end the model will retry — flag as a UX/availability note, not a vuln.

## Testing discipline

- Run the targeted suites before verdict (`pytest tests/computer_use/
  tests/tools/test_computer_use*.py tests/hermes_cli/test_plugins.py` plus any
  plugin test dir). Prefer tests asserting refusal WITHOUT the driver being called.
- Full-suite failures caused by unrelated dirty-tree deps (missing async plugin,
  lazy dependency) are out of scope — state that explicitly, don't block on them.
- New plugin-seam methods (`PluginContext.register_computer_use_backend`) often
  lack a direct unit test (only covered via a fake context in the plugin test) —
  call it out as a coverage gap.

## Worked example (Lot 1, reviewed 2026-08)

Verdict APPROVE_WITH_MINOR_NOTES on ~+895/-39 over 11 tracked files in
`/root/.hermes/hermes-agent` (dirty tree: unrelated web_server.py edits + many
untracked files). No security regressions. Approval-bypass fix was the correct
direction (unblocks explicit operator bypass; no new bypass introduced). Minor
findings: schema `name` gap for `launch_app`; urls-only launch blocked at
dispatch; `open_url` regex looser than intent (`about:` arbitrary content, `//`
not required for http); built-in backend can never satisfy `goal`; untested
plugin-seam registration + new config defaults. All targeted suites passed
(28 + 178 + 14 plugin tests).