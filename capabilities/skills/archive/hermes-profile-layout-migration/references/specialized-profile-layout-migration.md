# Verified Migration Notes — Creative Factory v1.3

This reference records a completed structural migration pattern. It is deliberately narrower than the umbrella skill and contains the concrete checks that worked.

## Layout result

- Canonical functional skills: exactly nine directories under `skills/<name>/SKILL.md`.
- Executable modules moved to profile-level `runtime/`.
- Business workflow and model registry moved to `workflow/`.
- Canonical JSON schemas moved to `schemas/`.
- `workspace/` retained only `jobs/` data and persisted artifacts.
- Old package tree and duplicate schemas were deleted after a whole-profile path search.

Use move operations, not copy-and-leave-both operations. After the move, search for the old package path in visible text files and separately classify any historical match inside session databases as non-runtime history.

## Artifact contract pattern

The central validator used this sequence:

```text
GENERATE
→ JSON_SCHEMA_VALIDATE
→ NORMALIZE documented legacy aliases only
→ JSON_SCHEMA_VALIDATE_AGAIN
→ SHA-256
→ atomic PERSIST
→ mark stage validated
```

Canonical contracts carried `schema_version: "1.3"`. Legacy artifacts were rejected by default. An explicit migration handled only safe aliases such as:

- `units` → `generation_units`
- `reason` → `rationale`
- Unicode route arrows → `IMAGE_TO_VIDEO`, `IMAGE_TO_POST`, `VIDEO_TO_POST`, `IMAGE_TO_VIDEO_TO_POST`

A deliberately invalid `generation_plan` was tested and blocked with a localizable schema error. Real artifacts from the self-test were persisted as fixtures and validated against the canonical schemas.

## Deterministic forensics parameters

- Base sampling: `5 fps`, chronological, no artificial frame duplication.
- Contact-sheet page size: maximum `25` frames.
- Layout: compact grid, at most `5 × 5`, no forced empty cells.
- Thumbnail: short side exactly `300 px`, aspect ratio preserved.
- Label: separate band below the image, containing source frame index and timestamp; no pixels of the source frame are overlaid.
- Each board has a machine-readable manifest linking `cell`, `shot_id`, sample index, source frame and exact timestamp.
- Board manifests carry `asset_role: ANALYSIS_CONTACT_SHEET`.
- Generation consumers accept only explicit roles such as `STORYBOARD_PANEL`, `FIRST_FRAME`, `LAST_FRAME`, `CHARACTER_REFERENCE`, `ENVIRONMENT_REFERENCE`, `PRODUCT_REFERENCE`, `VIDEO_REFERENCE` and `STYLE_REFERENCE` and verify hashes.

The test fixture covered a 6-second shot: exactly 30 samples at 5 fps, paginated as `25 + 5`. A short shot produced only its naturally available samples.

## Delivery contract

The Google bridge wrapped the existing canonical Hermes Google backend rather than creating a second credential system. A capability probe returned the four required booleans:

```json
{
  "drive_read": true,
  "drive_write": true,
  "sheets_read": true,
  "sheets_write": true
}
```

The safe test adapter exercised `write → read/verify → RESULT → FINISHED`. The production delivery code keeps `FINISHED=false` when the capability probe or remote readback fails; it never infers remote success from a local render.

## Empty-directory cleanup

Inventory empty directories first. Confirm that Hermes/runtime creates first-write directories dynamically or that the path is not a precondition. Remove bottom-up so empty parents left by child deletion are removed too:

```python
changed = True
while changed:
    changed = False
    for directory in empty_directories_bottom_up(profile_root):
        directory.rmdir()
        changed = True
```

In the verified cleanup, 17 empty directories were removed, including empty historical job/runtime/cache/log/output trees and their newly empty parents. A recursive post-test scan reported `0` empty directories. Non-empty structural roots (`skills`, `runtime`, `workflow`, `schemas`, `tests`, `workspace/jobs`) remained intact.

## Minimum final verification

- self-test: PASS, no paid provider call;
- unit/migration suite: 8 tests, all PASS;
- Python compile/import: PASS;
- recursive empty-directory scan: `0` remaining;
- no active runtime reference to the removed package tree;
- report `EMPTY DIRECTORIES REMOVED: <count>` explicitly.
