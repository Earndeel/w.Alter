# CuaDriver capture-integrity reference

## Sanitized observed response

A live macOS `get_window_state` response can contain these fields directly at
the top level (or under `structuredContent`):

```json
{
  "elements": [],
  "element_count": 0,
  "tree_markdown": "- [0] AXWindow \"Hermes\" ...",
  "screenshot_frame_valid": false,
  "screenshot_error": {
    "code": "px_frame_mismatch",
    "suggestion": "re-list and re-snapshot the exact window; do not reuse coordinates from a different surface",
    "capture_size": {"width": 2880, "height": 1800},
    "window_bounds": {"width": 1440.0, "height": 44.0},
    "scale_x": 2.0,
    "scale_y": 40.90909090909091
  }
}
```

The important facts are the boolean, error code, and bounds. The image may be
absent or unusable. Do not treat the markdown `AXWindow` line as an actionable
AX element when the structured list is explicitly empty.

## Window-selection reproduction

The same application can expose a helper row above its main window:

```json
[
  {
    "app_name": "Hermes",
    "pid": 33400,
    "window_id": 41707,
    "title": "",
    "z_index": 2,
    "is_on_screen": true,
    "bounds": {"x": 0, "y": -44, "width": 1440, "height": 44}
  },
  {
    "app_name": "Hermes",
    "pid": 33400,
    "window_id": 41657,
    "title": "Hermes",
    "z_index": 1,
    "is_on_screen": true,
    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900}
  }
]
```

A z-index-only selector chooses `41707` and produces `px_frame_mismatch`.
Preserving `bounds` and preferring the substantive surface selects `41657`.
Keep this fixture in the behavioral test suite; do not hardcode the live PIDs
or window IDs in production code.

## Safe validation checklist

- `check_permissions(prompt=false, probe_direct_capture=false)` is passive.
- `include_screenshot=false` is useful for AX inspection but does not establish
  `screenshot_frame_valid=true`.
- Use a new session ID with `start_session`; ended IDs are rejected.
- Do not inspect or click the CuaDriver authorization window itself; the driver
  rejects operations targeting its own authorization process.
- For a real interaction, use a reversible non-sensitive application control,
  capture before/after/final, and call `end_session`.
- If the pre-action state reports `px_frame_mismatch`, do not click.

## Verification boundary

The capture-integrity and target-disarm regressions passed in the session's
Computer Use test batch before the final bounds-selector edit: 156 tests across
8 files. Any later selector edit must be followed by a fresh CI-parity test run
before being reported as fully verified.
