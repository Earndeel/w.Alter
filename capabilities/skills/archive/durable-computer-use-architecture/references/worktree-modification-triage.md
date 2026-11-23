# Worktree Modification Triage (keep-core vs move-to-plugin)

Use when a mixed/local worktree carries uncommitted Computer Use changes and you
must decide, read-only, what stays in Hermes core and what belongs to the
walter-computer-use plugin — WITHOUT proposing any behavior change. This is the
classification the "Lot 1.x Upgrade Resilience" triage runs produce.

## Baseline-identity check (do this FIRST — it decides the shape of the whole map)

```
cd <checkout>
git rev-parse HEAD            # local HEAD
git status --short            # the real modifications
# Compare the target files between local HEAD and upstream main:
git -C /tmp/<upstream-mirror> diff HEAD <origin-main-sha> -- tools/computer_use/*.py
```

- If `git merge-base HEAD origin/main == HEAD` and the target files diff to 0
  between HEAD and origin/main, then **every worktree change is a local
  uncommitted modification** — none come from upstream. Report that up front;
  it means you are mapping local-only work, so the A/B/C/D split is the entire
  deliverable, not a reverse-diff against upstream.
- Do not assume the mirror is at the same sha; verify `git rev-parse HEAD` in
  the mirror and the local `origin/main` ref.

## Classification rubric (one label per hunk/function)

- **A — generic Hermes improvement, keep core.** Robustness/hermetic fixes that
  benefit any user: transport-shape normalization (`_tool_payload`,
  `_tree_text_from_tool_result`, `_capture_integrity_from_tool_result`),
  `CaptureResult.capture_valid/error/coverage` propagation, `_split_tree_text`
  new-shape guard, window-selection off-screen refusal,
  `include_screenshot=false` AX efficiency, fail-closed
  `_validate_pixel_coordinate` pixel validation, element-label length bounding,
  text-only-main-model vision skip, central approval-bypass consultation.
- **B — generic extension seam, keep core.** The stable plug surface the plugin
  consumes: backend **factory registry** (`register/get_backend_factory`,
  `registered_backend_names` in `backend.py`), `_configured_backend_name`
  (env `HERMES_COMPUTER_USE_BACKEND` or `config.yaml computer_use.backend`),
  `_get_backend` factory wiring, ABC **optional** hooks with fail-closed
  refusals (`launch_app/open_url/kill_app/verify_state/execute_goal`), and the
  `__init__.py` factory re-exports.
- **C — Walter-specific, candidate to live at plugin.** The model-facing
  high-level surface and its driver implementations that only make sense for
  Walter's workload: the `goal` action + `launch_app/open_url/kill_app/
  verify_state` actions and params, the goal-front-door docstring/description,
  the `needs_user_input → terminal/user_message/safe_to_return` direct-reply
  promotion, and the Lot-1-tagged native methods in `cua_backend.py`.
- **D — tests only.** All additions to test files. Note which behavior each
  test asserts (A-vs-C) even though the file is D.

## Judgment notes that prevent over-/under-claiming

- A backend method may be a **B seam** (generic dispatch) while a **specific
  block inside it is C** (e.g. the `goal` dispatch delegates to
  `backend.execute_goal` = B, but the direct-reply promotion block is C). Split
  the hunk, don't collapse it.
- Reuse tests: a helper function that already exists in core AND upstream
  (e.g. `_main_model_supports_vision`, `_explicit_aux_vision_override`,
  `is_approval_bypass_active_for_session`) means the new logic leveraging it is
  A, not a new seam you must add.
- A comment that names "Walter/Cua" ("before Walter/Cua was ever invoked")
  does NOT automatically make the behavior C — check what it actually does.
- The plugin (`walter-computer-use`, `kind=backend`) already implements
  `execute_goal` / `WalterComputerRouter` / `parse_computer_goal` and overrides
  `capture`/`click`. So "move C to plugin" is a statement of ownership, and
  removing C from core leaves the generic B dispatch delegating to the ABC
  hooks the plugin already overrides — plugin behavior is unchanged. Say that.

## Deliverable shape

Per file: per-hunk label + exact current-file line anchors (from `grep -n` on
the live file, e.g. `backend.py:285 launch_app`, `tool.py:642 goal`). Then a
C-total line table (`~ +added / −removed`) and a keep-core (A+B) vs move-to-
plugin (C) recommendation. State explicitly "no behavior change proposed."

## Current state (Lot 1.1, Aug 2026)

Local HEAD c0106e50 == merge-base; origin/main 08a3b20dff identical on all 5
core files (0 diff). Worktree: 948+/53− core, 100+/1− tests.
C (Walter) ≈ **+282 / −13** across:
- `tools/computer_use/schema.py` ~+60/−13 — goal docstring/description
  (12–16, 32–39), action enums goal/launch_app/open_url/kill_app/verify_state
  (34–39), params `goal/bundle_id/urls/expect/timeout_ms/stable_samples/…`
  (71–118), url desc (open_url).
- `tools/computer_use/tool.py` ~+119 — `_SAFE/_DESTRUCTIVE` members (82–92),
  `_summarize_action` goal (633), `_dispatch` goal (642, includes direct-reply
  promotion ~645–666) + launch_app (669)/open_url (699)/kill_app (709)/
  verify_state (718).
- `tools/computer_use/cua_backend.py` ~+103 — launch_app urls/isError
  (3202), open_url (3243, "stable Lot 1 action"), verify_state (3286).

B seams ≈ +85: `backend.py` registry (~14–90), ABC native hooks (285–356),
`tool.py` `_configured_backend_name` + factory wiring (~205–269), `__init__.py`
exports.
A = remainder (transport/capture-integrity/pixel/vision/approval/label-bounding).
Tests D: 4 files, +100/−1 (one Walter-flavored fixture
`/usr/local/bin/walter-cua-remote` in an otherwise generic security test).
