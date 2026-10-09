# Google Flow video-generation guardrails

Use this reference for every authenticated Google Flow generation, especially image-conditioned video through Camoufox Max.

## Non-negotiable completion contract

A Flow task is complete only when one of these is verified:

- a local MP4 exists and its media metadata is readable; or
- Flow returns a stable job/media identifier and a verified download URL/file.

A configured composer, an imported media library, a visible progress message, or an unverified queue claim is not completion. Never tell the user that a video was generated without the artifact or a verifiable job/download handle.

## Workflow

1. **Load the Flow skill first.** Confirm the authenticated tab, project URL, account tier/credits, requested model, duration, aspect ratio, reference order, prompt, and output target. Do not improvise a browser workflow when this skill is available.
2. **Use live refs only.** After every navigation, upload, menu open, or React rerender, obtain a fresh accessibility snapshot/DOM inspection. Never reuse refs from an older snapshot.
3. **Upload through the real image input.** Prefer the page's `input[type=file][accept*="image"]` and dispatch the normal input/change path. If the Camoufox request hits a body-size limit, preserve the originals and create temporary in-memory, visually faithful compressed copies; upload one file or a small batch under the limit. Accept Flow's rights/usage dialog when it appears. Verify that every filename appears in the imported library before proceeding.
4. **Attach media to the composer, not merely the library.** Imported cards are not ingredients by themselves. For each required reference, use the live card: hover/pointer events to reveal its toolbar, focus the `more_vert` menu, open it with the keyboard (`Enter` is more reliable than synthetic click for Radix menus), and choose **Ajouter au prompt**. After each selection, verify the filename and a `cancel` removal control appear in the same composer container as the Slate prompt. Ignore duplicate library cards and verify the intended role/order.
5. **Fill the real prompt editor.** Use the current live Slate textbox with the supported typing endpoint (or real keyboard path). Re-snapshot and verify the exact prompt text, all ingredient chips, and settings together. Text visible in a contenteditable DOM node without the composer state updating is not proof.
6. **Validate before spending credits.** Confirm model, duration, aspect ratio, and any start/end-frame settings. The actual submit button must be enabled (`aria-disabled` absent/false and not disabled). If it remains disabled, diagnose the current mode/state and stop; do not force-click or claim submission.
7. **Submit and approve explicitly.** Click the live submit ref only after validation. If Flow shows a cost/rights/approval dialog, record the displayed credit cost and approve the intended generation. Capture the resulting job/media ID or an unambiguous status handle.
8. **Poll and download.** Poll the job until complete using the authenticated browser/session. Download the resulting MP4 through the supported Flow path, then verify the file exists, is non-empty, and has valid video metadata (duration/aspect/codec as relevant). Preserve the exact path/URL/ID for the final response.
9. **Report blockers plainly.** If any step fails, state the precise last verified state (for example: “three chips attached; submit remained disabled; no job ID”) and do not say the video is ready or queued without evidence.

## Camoufox Max interaction notes

The active server commonly exposes `/tab/snapshot`, `/tab/evaluate`, `/tab/click`, and `/tab/type`. Use `/tab/evaluate` for DOM inspection and controlled keyboard/event fallbacks, but treat a returned DOM `File` list as input state only; it is not proof that Flow accepted or attached the media. The proof is the imported library entry and then the composer chip/removal control.

## Session-specific detail

For the Bulldog/Viper 10-second workflow, the reusable prompt and reference filenames are not part of this class skill; keep them in the task/session state. Do not hard-code stale project IDs, accessibility refs, credit balances, or output paths into this reference.
