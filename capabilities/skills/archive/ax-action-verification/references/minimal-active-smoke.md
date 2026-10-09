# Minimal active AX smoke

## Purpose

Prove one real native AX action without coordinates, screenshots, vision, hidden retries, or application-specific runtime logic.

## Sequence

1. Select one exact substantive window already suitable for AX.
2. Capture AX and retain this `CaptureResult` as the before-state.
3. Compact it for the LLM without modifying or fabricating native refs.
4. Let the LLM choose one reversible target.
5. Dispatch the exact current native token.
6. If the driver directly confirms the effect, finish.
7. If it returns `unverifiable`, capture AX exactly once on the same PID/window.
8. Compare semantic fingerprints and emit the criteria object.

## Fingerprint pseudocode

```python
from collections import Counter

def scalar(value):
    return value if isinstance(value, (str, int, float, bool, type(None))) else None

def element_fact(element):
    attrs = element.attributes or {}
    bounds = tuple(element.bounds) if element.bounds else None
    return (
        element.role or "",
        element.label or "",
        scalar(getattr(element, "value", None)),
        scalar(attrs.get("selected")),
        scalar(attrs.get("expanded")),
        scalar(attrs.get("checked")),
        scalar(attrs.get("enabled")),
        bounds,
    )

def fingerprint(capture):
    return Counter(element_fact(e) for e in capture.elements)

def verify(before, after):
    return fingerprint(before) != fingerprint(after)
```

Do not include snapshot ID, element token, compact index, or generation in `element_fact`.

## Proof schema

```json
{
  "chosen": {
    "ref": "<native token from before snapshot>",
    "role": "AXButton",
    "label": "<live choice>"
  },
  "action": {
    "route": "accessibility",
    "effect": "unverifiable"
  },
  "verification": {
    "source": "targeted_ax_observation",
    "changed": true,
    "verified": true
  },
  "criteria": {
    "real_native_ref": true,
    "action_reached_driver": true,
    "blind_coordinate_click": false,
    "screenshot": 0,
    "vision": 0,
    "result_verified": true
  },
  "passed": true
}
```

Compute `passed` with explicit predicates, especially `blind_coordinate_click is false`; a blanket `all(values)` is incorrect.

## Harness boundary

The harness may ask the LLM/operator to select an index from the live compact projection. It may choose a convenient app/control for that run, but those names must not enter plugin runtime routing. Store sanitized proof only; do not preserve personal labels or screenshots in long-lived references.

## Cleanup

If the control changed persistent UI layout, perform restoration separately using fresh refs and verify it. Preserve the successful smoke artifact even if cleanup needs another attempt; smoke validity and UI restoration are distinct postconditions.
