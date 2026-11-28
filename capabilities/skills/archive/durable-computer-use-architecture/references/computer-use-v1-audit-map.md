# Computer Use V1 — Architecture Cartography & Gap Inventory

Read-only audit map of the active Computer Use V1 (core `tools/computer_use/*`
+ plugin `walter-computer-use`). Line anchors are from the reference tree at
HEAD `c00089cd` (core) and plugin v1.1.0. Use this as the fast entry point for
any audit, extension, or gap triage; re-anchor lines before citing in a
deliverable, since the tree moves.

## File → responsibility map (file:line)

- `tools/computer_use/backend.py`
  - `ComputerUseActionExtension` plugin action shape: `:16-24`
  - registries `_BACKEND_FACTORIES` / `_ACTION_EXTENSIONS` (profile-scoped): `:26-132`
  - `UIElement` (incl. `element_token` stale guard): `:136-158`
  - `CaptureResult` (mode/png/elements/capture_valid/error/coverage/mime): `:161-193`
  - `ActionResult` structured verdict (`verified/effect/escalation/path/degraded/code`): `:196-234`
  - `ComputerUseBackend` ABC primitives: `:236-374`; typed-browser hooks fail closed: `:341-367`
- `tools/computer_use/schema.py`
  - single `computer_use` tool, `action` discriminator enum: `:16-58`
  - `max_elements` cap 100/1000: `:109-130`
- `tools/computer_use/tool.py` (dispatcher + safety + result shaping)
  - `_SAFE_ACTIONS` (`capture/wait/list_*/cua_browser_state`): `:84-86`
  - `_DESTRUCTIVE_ACTIONS` (approval-gated, incl. all `cua_browser_*`): `:89-95`
  - blocked key combos & type patterns (fail-closed): `:99-149,159-166`
  - permission-mode resolution (YOLO→unrestricted, fail-closed): `:202-229`
  - per-session backend cache / lifecycle: `:232-302`; release: `:305-352`; atexit: `:355-402`
  - `handle_computer_use` (validate → approve → backend → dispatch): `:492-566`
  - approval scoping `(action, delivery_mode) × session`; **default-ALLOW if no callback**: `:569-629,602-606`
  - `_dispatch` per-action; plugin extension first; browser route: `:658-863`
  - verdict ladder `_classify_action_result` (done/verify_fresh_state/escalate): `:870-887`
  - typed-browser `page` escalation alternative: `:930-967`
  - `_capture_response` multimodal / aux-vision / AX branches: `:1058-1270`
  - aux-vision routing + downscale ≤1456px + one-shot describe: `:1280-1528`
  - `_maybe_follow_capture` (no screenshot on failure): `:1531-1573`
  - element label cap 120 + spill-to-disk + HiDPI bounds note: `:1596-1736`
- `tools/computer_use/cua_backend.py` (driver transport)
  - `_action_result_from` lift structured verdict: `:69-129`
  - embedded daemon / CLI-transport fallback: `:418-540,1568`
  - session capabilities + restart: `:1121-1568`; `call_tool`: `:1711`
  - `capture` modes (vision `/screenshot|get_window_state`, ax `include_screenshot=false`, SOM elements): `:2337-2676`
  - `_apply_delivery` / `_run_input_action` / `bring_to_front`: `:2815-2905`
  - `click` tool/button selection: `:2907-2961`; `_action`: `:3528-3567`
- `tools/computer_use/vision_routing.py`
  - `should_route_capture_to_aux_vision`, fail-closed toward aux: `:164-199`
- `tools/computer_use/browser_route.py`
  - exact-bind typed-browser adapter; ref/tab/mutation discipline, no chained mutations without fresh snapshot: `:179-573`
- plugin `walter-computer-use/__init__.py` (policy only — core owns approval/dispatch/lifecycle: `:1-8`)
  - goal parser (hardcoded apps + youtube only): `:44-83`
  - `compact_ax_state` (YouTube-domain regex): `:96-133`
  - `WalterComputerRouter.execute` (launch→ax observe→(click)→verify): `:197-319`
  - `WalterCuaBackend` (launch_app/open_url/verify_state/execute_goal/capture strategy/px retry): `:583-841`
  - `_handle_goal_action` + `safe_to_return` certification: `:856-883`
  - `register()` seams: `:894-930`
- core host seams: `hermes_cli/plugins.py:1486-1545`

## Key contracts

- **Core** owns: schema, approval + permission mode, session backend cache/lifecycle, multimodal result, safety lists. **Plugin** owns: naming/targeting policy, goal routing, local bounded recovery, prompt section. Do not duplicate the tool/approval in a plugin.
- **Verify→escalate ladder**: `confirmed`→done; `unverifiable`→fresh-state check before retry; `suspected_noop` or refusal→escalate `px|foreground|page`. `ok` is transport success, NOT semantic proof.
- **Local recovery bound**: plugin `click` retries once only on `suspected_noop`+`recommended=px`, background, from remembered centers; never auto-escalates to foreground/page.
- **Vision**: main-model-non-vision → screenshot dropped to compact AX text (not just rerouted), or one-shot aux `describe`; no perception→action loop, no coordinate grounding.

## Gaps toward an "Adaptive Universal Operator" (P0/P1/P2)

**P0 — correctness/safety:**
1. Approval `default-allow` when `_approval_callback is None` (`tool.py:602-606`) relies on outer gateway; fail-close at the tool.
2. Vision is one-shot describe, not a loop; no coordinate grounding (only heuristic scale note).
3. `verify_state` checks only `window.exists` — no content/OCR postcondition; liveness ≠ task success.

**P1 — universality/adaptivity:**
4. Goal parser hardcoded to 6 browsers + YouTube (`__init__.py:56,78-83`); everything else → `unsupported_goal`.
5. `compact_ax_state` regexes are YouTube/“video”-domain (`__init__.py:101-108`); no domain-agnostic semantic AX summarizer; `ComputerGoal` has no multi-step plan (`:48-51`).
6. Router is **stateless**; no preference/memory learning; single `SafeWindowStrategy` singleton (`:455-457`); no reward/feedback.
7. Capture is single-window only; no whole-virtual-desktop/multi-monitor (`cua_backend.py:153-162,2393-2426`).

**P2 — robustness/ergonomics:**
8. No vision-reported coordinates; model re-derives pixel targets.
9. Typed browser route is a parallel surface, not integrated into the goal engine.
10. Hard element/label/spill budgets are guardrails, not adaptive attention prioritization.

## Audit method (repeatable, read-only)

- `git status --porcelain` / `git diff --stat` must be empty; record `git rev-parse HEAD` + `HEAD^{tree}`.
- `sha256sum` every audited file for a tamper-proof read-only proof.
- Confirm no backend started: `pgrep -a cua-driver` → none (never instantiate driver in an audit).
- `grep -n "^class \|^def "` per module for an index before reading hot paths (e.g. `capture`, `_action`, `_action_result_from`, `_dispatch`).
- Cite `file:line` from the actual tree; re-anchor before quoting in a deliverable.
