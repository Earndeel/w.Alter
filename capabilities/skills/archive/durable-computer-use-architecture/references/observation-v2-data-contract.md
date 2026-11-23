# Raw backend → observation V2: data contract audit

Line-anchored contract for consumers that read `CaptureResult` / `ActionResult`
off the raw computer-use backend (e.g. a durable observation/event layer, a
walter-computer-use-style plugin, or the future "observation V2"). Read from
release tree `~/.hermes/releases/hermes-agent-*/tools/computer_use/`. This is a
read-only contract snapshot; re-verify anchors if the tree moved.

## Result object shapes (backend.py)

- `UIElement` (backend.py:135-157): `index` (1-based SOM), `role`, `label`,
  `bounds` (native x,y,w,h logical px), `app`, `pid`, `window_id`,
  `attributes` (dict), `element_token` (Optional[str]; opaque
  `s{snapshot_hex}:{index}` handle).
- `CaptureResult` (backend.py:160-192): `mode`, `width`/`height`
  (pre-Anthropic-scale logical px), `png_b64`, `elements` (List[UIElement]),
  `app`, `window_title`, `png_bytes_len`, `image_mime_type`, and the
  **frame-integrity triple** `capture_valid` (Optional[bool]) /
  `capture_error` (dict) / `capture_coverage` (dict). Integrity is independent
  of the AX tree: a rejected frame may still carry usable elements.
- `ActionResult` (backend.py:195-233): `ok` (transport-only; NOT semantic
  success), `action`, `message`, `capture` (Optional[CaptureResult]), `meta`
  (dict), and the additive verdict fields `verified` (bool), `effect`
  (confirmed|unverifiable|suspected_noop), `escalation` (dict),
  `path`, `degraded` (bool), `delivery_mode`, `code`.

## Where native refs live — and where they are DROPPED

- `element_token` is parsed from `structuredContent.elements` into
  `UIElement.element_token` (cua_backend.py:974-985) and cached in the backend
  instance map `self._snapshot_tokens` (`{index -> token}`) on each capture
  (cua_backend.py:2659-2663).
- **`_element_to_dict` omits `element_token`, `pid`, `window_id`, and
  `attributes`** from the model-facing `elements` JSON (tool.py:1744-1753).
  So the model NEVER sees the native token today; only the backend's
  `_maybe_attach_element_token` uses it (cua_backend.py:3502-3526, attaches it
  to an outgoing action when the tool advertises
  `accessibility.element_tokens` capability).
- Native `bounds` reach the model but are scaled-vs-native divergent on HiDPI;
  `tool.py` warns via `_bounds_space_note` (1699-1721) and `_bounds_scale`
  heuristic (1672-1696). `backing_scale_factor` is hardcoded None
  (cua_backend.py:2717) — never a real metric.
- The walter plugin's `compact_ax_state` `_element_row` also drops
  `element_token`/`pid`/`window_id` (plugin `__init__.py:86-133`) — an
  observation layer must lift them explicitly.

## Mutation lifetime (the critical rule for an observation cache)

- The raw backend result objects are **not mutated by later backend calls**:
  `capture()` builds a fresh `CaptureResult` each call (cua_backend.py:2722-2735);
  `tool.py` copies fields into fresh response dicts (`_action_payload` 890-916,
  `_element_to_dict` 1739). So, read straight off the raw `ComputerUseBackend`,
  they are effectively immutable after the backend method returns.
- **BUT a wrapper layer mutates the SAME objects in place AFTER the raw backend
  returns** — an observation/event layer must snapshot at the exact boundary it
  actually reads (after any plugin wrapper), or deep-copy at emission:
  - walter plugin `_mark_capture_integrity` (plugin `__init__.py:554-580`) sets
    `capture.capture_valid`, `capture.capture_error`, and
    `capture.capture_coverage` on the `CaptureResult` returned by
    `super().capture()`; it runs from `_finish_capture` (724-729) which wraps
    every plugin `capture` (731-772) — so raw-backend `capture_valid` may still
    be `None` that the plugin later flips to `False`.
  - plugin `click` (774-839) replaces and grows `recovered.meta` with
    `recovered.meta['walter_loop'] = {...}` on the second `super().click()`
    return (829-839).
  - intra-backend mutations happen BEFORE the raw return and are safe to
    snapshot after: `_run_input_action` sets `result.meta['foreground_focus']`
    (cua_backend.py:2900-2904); `focus_app(raise_window=True)` rewrites
    `focused.action` + `meta['target_selected']` (cua_backend.py:3192-3193).
- The dangerous part is **backend INSTANCE state**, which the next call
  overwrites — never hold live refs to it, deep-freeze/copy on emission:
  `_snapshot_tokens` (2659, cleared 2469/3171/2184), `_active_pid` /
  `_active_window_id` / `_last_target` (2456-2478), `_last_capture_geometry`
  (2458-2466, 2705-2720).
- `_action` builds `meta` from the driver's `data`+`structuredContent` merged
  (structured wins) and returns it verbatim (cua_backend.py:3559-3566, 117-129);
  copy it if you cache across turns.

## Stale-generation guard (already present)

- `element_token` carries snapshot identity; cua-driver returns an explicit
  **'stale' error** if the snapshot was superseded — documented
  cua_backend.py:3504-3510, and `element_token` takes precedence over
  `element_index` when both are sent.
- Wrapper refreshes the whole `_snapshot_tokens` map ONLY on a fresh capture
  (cua_backend.py:2659-2663); disarms it on start/reset (2184), before any
  capture that retargets a new window (2469), and on `focus_app` retarget
  (3171). It is NOT disarmed after a click/type (2907-3100), so the token stays
  valid until the next capture and driver-side staleness decides.
- Frame integrity is guarded separately: on invalid pixels with no AX elements
  the active target is disarmed (2676-2683); `_last_capture_geometry` is
  cleared whenever `pid`/`window_id` changes (2458-2466) or geometry is not
  freshly pixel-verified (2705-2720); pixel coordinates are validated against it
  → `coordinate_target_stale` refusal (2786-2788).
- There is **no explicit generation counter** — "generation" is implicit via
  snapshot replacement. Any event-schema `generation` field is a proposed
  addition, not present in source.

## Honest-unknowns / additive contract

Always preserve an absent native value as `None`/absent — never synthesize:
- `effect`/`verified`/`escalation`/`path`/`degraded`/`code` are additive
  (`None` = old driver omitted `structuredContent`; cua_backend.py:80-129).
- `element_token` is `None` on pre-#1961 drivers (backend.py:148-153).
- `capture_valid` is `None` when the driver lacks frame-integrity fields
  (backend.py:190).
- `width`/`height` = 0 or `_image_dimensions` None when there is no usable
  image / sniff fails (tool.py:1062, cua_backend.py:2690-2700).
- `_bounds_scale` None when coordinate spaces don't diverge or no elements
  (tool.py:1683-1696).
- Escalation's typed-page `alternative` hint is additive, never a fabricated
  driver verdict (tool.py:936-967).

## Proposed immutable observation event schema

```json
{
  "kind": "capture|action",
  "ts": "ISO-8601 emission time",
  "generation": "monotonic per-backend snapshot epoch (PROPOSED — absent today)",
  "snapshot": "opaque snapshot id from element_token prefix, or null (no tokens)",
  "target": {"pid": "int|None", "window_id": "int|None", "app": "str", "window_title": "str"},
  "geometry": {"width": "int", "height": "int", "capture_valid": "bool|None",
               "capture_error": "obj|None", "capture_coverage": "obj|None",
               "bounds_note": "str|None", "bounds_scale": "float|None"},
  "elements": [{"index": "int", "role": "str", "label": "str",
                "label_truncated": "bool(omit)", "bounds": "[native x,y,w,h]",
                "app": "str", "pid": "int|None", "window_id": "int|None",
                "element_token": "str|None"}],
  "action": {"action": "str", "ok": "bool", "message": "str",
             "verified": "bool|None", "effect": "str|None",
             "escalation": "obj|None", "path": "str|None",
             "degraded": "bool|None", "delivery_mode": "str|None",
             "code": "str|None",
             "verdict": "done|verify_fresh_state|escalate"},
  "unknown": ["field names whose native value was absent at emission time"],
  "immutable": true
}
```

Deep-freeze on emission (tuples for bounds, immutable/copied dicts for
meta/escalation/attributes). Never hold live refs to backend instance state.

## Audit deliverable discipline (machine-validated JSON)

When a parent hands this class of read-only audit an OUTPUT CONTRACT that
says "final response must be a single JSON object validating against this
schema — no prose before or after", the deliverable is EXACTLY one
JSON-parseable object and nothing else. A trailing paragraph, a code fence
plus commentary, or any bytes after the closing brace fail the validator
(`json.loads` → "Extra data: line N column 1"), and the whole answer is
rejected and has to be re-emitted. Emit the object, verify it parses, and
stop — no summary, no "what I did". Keep JSON itself tidy: no trailing
commas, no comments, every required top-level key present. Honest-unknowns
still apply inside the JSON: list fields the source genuinely does not expose
(e.g. `generation`, an exposed `snapshot_id`) under an explicit unknown list
rather than fabricating a value — the parent validates shape, and the audit
value is precisely the truthful boundary between what exists and what does
not.