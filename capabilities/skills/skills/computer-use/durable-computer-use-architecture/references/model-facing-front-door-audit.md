# Model-Facing Front Door Audit (computer_use) — current seam map + Lot 1 gaps

Read-only audit (Aug 2026) of the single model-facing `computer_use` front door:
`tools/computer_use/` package + `tools/computer_use_tool.py` shim + the
`walter-computer-use` plugin. Repo: `/root/.hermes/hermes-agent`. The goal of
this workstream is **one model-facing door, Mac first, runtime routing
native/AX before vision, compact AX, verification, no hardcoded Retina
scaling, no App Memory yet.**

## Audit method (do this first next time)

1. `git status --short` → inventory uncommitted/untracked work BEFORE anything
   else; never reset/stash blind (the updater autostash protects content only
   from loss, not from structural resets).
2. Set-diff the schema surface against actual dispatch: load
   `COMPUTER_USE_SCHEMA["parameters"]["properties"]["action"]["enum"]` and
   compare with the `_dispatch` branches in `tool.py`. Anything in the enum
   without a handler (or vice-versa) is a real surface bug.
3. Check the bundled `computer-use` skill Actions list (`skills/
   autonomous-ai-agents/computer-use/SKILL.md`, ~lines 80-104) against the
   schema — doc-drift is a runtime-exposure gap.
4. Check action classification: every enum action must land in
   `_SAFE_ACTIONS` or `_DESTRUCTIVE_ACTIONS`; destructive go through
   `_request_approval`, persistent focus goes through the separate
   `bring_to_front` approval scope.
5. For pixel geometry: grep the hot path for any literal scale constant
   (e.g. `* 2.0`) and for coordinate-range validation. Absence of a literal is
   good; absence of *any* bounds check is a fail-closed gap.

## Current seam (exact names, as audited)

- **Registry**: `tools/computer_use/backend.py` — `register_backend_factory`
  (rejects reserved `cua`/`cua-driver`/`noop`; collision-safe, fail-closed),
  `get_backend_factory`, `registered_backend_names`.
- **Plugin seam**: `hermes_cli/plugins.py` `PluginContext.
  register_computer_use_backend(name, factory)` → calls the registry. Plugin
  modules are imported and `register(ctx)` called (plugins.py ~1925+).
- **Selector**: `tools/computer_use/tool.py` `_configured_backend_name()` —
  config `computer_use.backend` first, `HERMES_COMPUTER_USE_BACKEND` env as
  test/integration escape hatch. `_get_backend(session_id)` is session-owned
  one-backend-per-session; YOLO permission-mode toggle replaces only that
  session's backend (`_cua_permission_mode` consults both the DB session id and
  gateway session key).
- **Config defaults**: `hermes_cli/config_defaults.py` `computer_use.backend`
  (`"cua"`), `computer_use.capture_strategy` (`"safe-window"`).
- **Capture integrity (new)**: `CaptureResult.capture_valid /
  capture_error / capture_coverage`. Parsed from driver responses by
  `_capture_integrity_from_tool_result` (cua_backend); used in
  `_capture_response` (tool.py) to omit the screenshot and add a
  "screenshot omitted... AX elements remain" note when `capture_valid is
  False`; target is disarmed when pixels are invalid AND no AX elements
  survived. Walter plugin `_mark_capture_integrity` fails closed on an
  explicitly empty image.
- **Window targeting (new)**: `_select_capture_target` returns `None` when no
  live pool (no stale off-screen recycling) → `_failed_capture` diagnostic;
  `_has_substantive_window_bounds` rejects tiny/zero bounds; `_ingest_windows`
  now preserves `bounds`.

## Lot 1 gap inventory (existing → missing)

1. **Native/app launch + URL navigation** — backend methods exist:
   `CuaDriverBackend.launch_app(bundle_id, name, urls, additional_arguments,
   creates_new_application_instance)`, `kill_app(pid)`, `bring_to_front(pid,
   window_id)`. MISSING from model surface: schema enum, `_dispatch` handler,
   skill Actions list → models cannot launch apps or open URLs natively (only
   `cua_browser_navigate` for driver-owned browser). Only backend test is the
   empty-arg guard.
2. **AX-first compact state** — `mode=ax` returns elements-only text JSON and
   `max_elements` cap (default 100, hard 1000) is solid. MISSING: no runtime
   routing that drops the screenshot in favor of compact AX for non-vision
   main models (aux-vision routing only picks image→aux-vision, never
   image→none); `_element_to_dict` sends full untruncated `label` (summary
   truncates at 60 chars).
3. **Act/verify semantics** — PRESENT and well-tested (`_action_result_from`
   normalizes driver verdicts; `_classify_action_result` → verdict
   `done|verify_fresh_state|escalate`; `_apply_delivery` refuses
   `foreground_unsupported` without downgrade; `test_computer_use_delivery_
   ladder.py` covers normalization/escalation/approval). Only gap: the schema
   prose itself doesn't enumerate verdict values (the skill doc carries the
   ladder), and `_request_approval` defaults to *allow* when no callback is
   wired (CLI-only; gateway handles it one layer out) — pin that default with a
   test.
4. **Pixel geometry fail-closed** — MISSING: no coordinate-range validation on
   `click(x,y)`/`drag`/`scroll(x,y)` (int-cast straight to driver, only
   "active window exists" checked); `get_screen_size` returns
   `backing_scale_factor` but nothing consumes it; response width/height are
   PNG physical pixels while AX `bounds` are logical points (dual-space).
   GOOD: no hardcoded ×2 Retina literal anywhere — if mapping is ever needed,
   consume `backing_scale_factor` and fail closed when unknown.
5. **Skill/runtime exposure** — seam is excellent; surface is incomplete
   (superset of #1: launch/kill/open-url absent from schema AND bundled skill);
   `computer_use.capture_after_mode` default not in config_defaults; no
   end-to-end test of `computer_use.backend: walter` via config (only
   env-override + `_configured_backend_name` unit).

## Uncommitted work to preserve (as of audit)

Modified: `tools/computer_use/{backend,tool,cua_backend,__init__}.py`,
`hermes_cli/{config_defaults,plugins}.py`,
`tests/tools/test_computer_use_cua_backend_linux.py`.
Untracked tests: `test_computer_use_backend_registry.py`,
`test_computer_use_capture_integrity.py`.
Unrelated (leave alone): `hermes_cli/web_server.py`
(`HERMES_DASHBOARD_ACCEPTED_HOSTS` dashboard forwarder), THALEOS/report
markdown, `ui-tui/.../terminalDimensions.ts`.

## Next slice plan (Phases A-D, preserving the above)

- **A — app launch + URL front door**: add `launch_app`/`kill_app`/`open_url`
  to schema enum + `_DESTRUCTIVE_ACTIONS` + `_summarize_action`; `_dispatch`
  handlers; non-abstract optional ABC defaults returning a
  `typed_browser_unavailable`-style structured refusal (keeps 3rd-party backends
  instantiable); extend `test_schema_lists_all_expected_actions` with `>=`
  (behavior contract, not change-detector); update bundled skill Actions table.
- **B — AX-first compact**: in `_capture_response`, drop to AX text payload
  (not just on aux-vision *failure*) when main model is non-vision; truncate
  `label` in `_element_to_dict`.
- **C — pixel geometry fail-closed**: track last capture `width/height`
  (+`backing_scale_factor`), reject negative or `>capture+epsilon` coords with
  `code="coordinate_out_of_bounds"` + `escalation.recommended="ax"`; never a
  literal scale; test in/out-of-bounds + a behavioral "no hardcoded scale on
  hot path" assertion.
- **D — hardening/exposure**: invariant test every schema action ∈
  `_SAFE ∪ _DESTRUCTIVE`; config-plane test for `backend: walter` selection;
  add `capture_after_mode` to config_defaults; pin the no-callback→allow
  approval default.

## Verification baseline

`pytest tests/tools/test_computer_use*.py` plus the walter plugin test module
must stay green before and after each phase; the audit itself made no edits.
