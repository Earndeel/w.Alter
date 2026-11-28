# Plugin-only fast-vision: targeted-crop visual sensor + snapshot-bound visual refs

Read-only architecture audit of the *current* vision pipeline (release
`hermes-agent-lot11-…`), producing a plugin-only design for an additive
targeted-crop visual sensor and short-lived visual refs — without changing the
model-facing `computer_use(goal)` shape or any core file. Multiple plugins can
share this seam.

## Line-anchored map of the current vision pipeline

- `tools/computer_use/vision_routing.py` (204 ln) — pure policy:
  `should_route_capture_to_aux_vision(provider, model, cfg)` at **L164**,
  **fails closed** toward aux routing. Helpers `_explicit_aux_vision_override`
  (**L56**), `_provider_accepts_multimodal_tool_result` (**L143**, reuses
  `tools.vision_tools._supports_media_in_tool_results`), `_lookup_supports_vision`
  (**L107**, reuses `agent.image_routing`).
- `tools/computer_use/tool.py`:
  - `_capture_response(cap, max_elements)` **L1058** is where the image is
    routed. Mode gate at **L1136**; aux-vision branch **L1143-1213**; multimodal
    envelope `{"_multimodal": True, "content":[text,image_url], "text_summary"}`
    **L1227-1239**. AX/text payload **L1248-1270**.
  - `_should_route_through_aux_vision()` **L1326** (cache `_AUX_VISION_ROUTE_CACHE`);
    `_aux_vision_is_explicit()` **L1381**; `_route_capture_through_aux_vision()`
    **L1408** writes the PNG to `$HERMES_HOME/cache/vision/`, downscales via
    `_shrink_capture_for_vision` **L1283** (`_MAX_VISION_DIM = 1456`), calls
    `vision_analyze_tool` (via `_run_async` from `model_tools` **L1437**), unlinks
    the temp file in `finally`. `_main_model_supports_vision()` **L1364**.
  - Coordinate-space guards: `_bounds_scale` **L1672**, `_bounds_space_note`
    **L1699** warn AX element bounds can be *native desktop* coords while the
    PNG is *window-local* (HiDPI/scaled displays). Any crop must handle or
    reject this.
  - `_dispatch` **L658**: action extensions are resolved first at
    **L661-666** (`get_action_extension(action)` → `extension.handler(backend,
    args)`), then built-in actions. This is the exact plugin-only seam for new
    sensor actions.
- `tools/computer_use/backend.py`:
  - `UIElement.bounds` = `(x, y, w, h)` tuple, logical px (**L142**);
    `UIElement.center()` **L155**.
  - `CaptureResult` **L160-192**: `width`, `height`, `png_b64`,
    `image_mime_type` (explicit MIME, else base64-prefix sniffing), `elements[]`,
    `app`, `window_title`, `capture_valid`/`capture_error`/`capture_coverage`.
  - Extension registry: `register_action_extension(name, handler, properties=…,
    destructive=…)` **L85**, `get_action_extension` **L123**.
- `tools/computer_use/cua_backend.py`:
  - `capture()` **L2337**: dims from `_image_dimensions_from_bytes` **L2695**;
    `_last_capture_geometry` **L2712** = `{pid, window_id, width, height,
    backing_scale_factor}` (None for AX-only); snapshot-token cache
    `_snapshot_tokens` **L2659** cleared on every capture (also **L2469** before
    capture).
  - **Geometry fail-closed precedent**: `_validate_pixel_coordinate` **L2737**
    refuses coordinates unless the newest capture has positive geometry for the
    same exact pid/window pair; unknown/mismatch/zero edges all refuse with
    `escalation.recommended="ax"`.
- `hermes_cli/plugins.py` host seams: `register_computer_use_backend` **L1486`,
    `register_computer_use_action` **L1511** (→ `register_action_extension`,
    handler `(backend, args)`), `register_system_prompt_section` **L2858**.

## Plugin-only design (no core change)

**Preserve the model-facing schema before choosing the plugin seam.** If
`computer_use(goal)` is contractually byte-stable, do **not** register
`visual_sensor`, `vision_target`, `targeted_verify`, or another action extension:
registration changes the effective action enum even though it avoids a core
edit. Keep the sensor behind the existing `goal` handler and return a compact,
explicit observation envelope to the same Hermes LLM. A later `goal` call may
consume one visual ref for one selected primitive; the runtime must not infer a
multi-step workflow.

Use `ctx.register_computer_use_action(...)` only when additive model-facing
actions are explicitly allowed and the schema change is tested and approved.
The handler receives `(backend, args)` and returns a dict through the existing
dispatch seam, but architectural convenience does not override schema
stability.

### 1. Targeted-crop visual sensor (e.g. `visual_sensor` / `crop`)
- Take the already-bound `CaptureResult` (the one shown to the model this turn,
  or re-capture `mode="ax"`/`"som"` to the exact `pid, window_id`), pick an
  element by index, read `bounds`.
- **Geometry fail-closed** (never guess): require `png_b64`, positive
  `width`/`height`, bounds fully inside the image, and a consistent
  coordinate basis (`_bounds_scale` ≤ ~1.05 or a known `backing_scale_factor`);
  otherwise return `{"status":"skipped","reason":"geometry_unavailable"}` with
  **no vision call**.
- Decode → PIL-crop to bounds → write a temp PNG/JPEG under
  `get_hermes_dir("cache/vision", "temp_vision_images")` → call
  `vision_analyze_tool(path, prompt)` (same pathway as `_route_capture_through
  _aux_vision`) → return text attached to the element. Unlink temp in `finally`.
- **No second planner**: this is a single observation augmentation appended to
  the same tool result the model already sees — not a separate LLM loop, not a
  new goal action.

### 2. Snapshot-bound visual refs
Mirror the plugin's existing `arm_native_refs` / `_guard_native_ref` pattern
(`walter…/__init__.py`, ~**L725-760**):
- Bind the crop + its `element_token`/`snapshot_id` to the exact capture
  snapshot in a short-lived dict on the backend.
- Invalidate on: a new capture (core already clears `_snapshot_tokens` on every
  capture), target change, and consumption (single-use, then `consumed`).
- Never persist; the observer already strips pixel payloads (`png_b64`,
  `screenshot_png_b64`, `images`) from published events — visual refs are
  task-local.

### Where it lives
New file e.g. `deploy/walter-computer-use-lot23/vision.py` imported and wired
in `register(ctx)`; reuse `compact_ax_state` / `_element_row` for element
selection. AX remains preferred throughout (capture `mode="ax"` first).

## Tests (add to plugin-local `test_walter_computer_use.py`)
- Crop: synthetic `CaptureResult` with known width/height/png_b64 + element
  bounds → assert sub-region analysis and correct bbox.
- Fail-closed cases: unknown dims, zero/out-of-bounds bounds, scale > threshold
  → assert `status="skipped"` and **no** vision call.
- Snapshot binding: matching token works after `arm`; after consumption or a
  fresh capture the visual ref refuses (`stale_ref`) — do not act on stale refs.
- AX-preferred: sensor selects captured AX elements over pixel coordinates.
- Reuse patterns from host `tests/tools/test_computer_use_vision_routing.py`
  and `test_computer_use_capture_routing.py`.
