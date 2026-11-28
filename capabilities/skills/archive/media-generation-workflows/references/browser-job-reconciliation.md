# Browser job identity and recovery

Use this reference when a browser-based media monitor reports ambiguous outputs, loses progress after a reload, or mistakes existing assets for a new generation. This is a read-only diagnosis and correlation procedure, not a claim that the provider's failed generation can be repaired locally.

## Establish identity before submission

1. Read the latest manifest and retain the intended project, clip, prompt, input handles, attempt identity, and previously completed media IDs.
2. Obtain the current project's media inventory. A visible `img` count is insufficient: virtualized or lazy-loaded galleries can omit existing assets while the composer or an ingredient picker is open.
3. Reconcile inventory IDs with already completed clips from that project. Preserve the original observation if repairing an incomplete baseline, and record the evidence used for the repair; do not silently rewrite submission history.
4. Persist the baseline before the billable click. If completeness or identity cannot be established, stop with an identification problem rather than saving an empty baseline and treating every later tile as new.
5. After submission, retain the provider receipt or job ID when exposed. Prefer exact job-to-output correlation; inventory differences alone cannot distinguish concurrent jobs.

## Diagnose an interrupted or ambiguous monitor

1. Inspect the live project and the saved submission evidence before any retry. Check the existing attempt rather than spending again to investigate a local exception.
2. Read provider messages, local monitor errors, current project inventory, and credit balance as separate evidence. A stable balance is a spending observation, not proof of the provider's internal failure reason.
3. Identify completed media by stable project-scoped IDs. CDN thumbnails may use opaque paths with no UUID; signed URLs may rotate, and duplicate DOM nodes may represent one asset. Do not extract the first UUID from an arbitrary URL or compare complete signed strings as identity.
4. Exclude reference uploads, stock/template assets, and other projects. A new image upload is not a completed video.
5. Compare candidate media with the submission receipt or intended prompt and baseline. If multiple unrelated candidates remain, preserve them for reconciliation instead of choosing the first.
6. If only previously completed videos remain, report no recoverable new output. A disappeared progress indicator or failure tile does not establish success, and absent output alone does not establish why generation failed.
7. Keep reference binding separate from provider causality: selected ingredient chips can establish what was attached, but do not establish that an attachment caused rejection.

## Flow: observed read-only inventory source

Load `camoufox-max-api-current` and its `references/flow-omni-current-ui.md` for browser controls and generation gates. Keep Flow automation headless; this diagnostic does not require a visible Mac browser.

When thumbnail URLs no longer expose media IDs, inspect response bodies from the already authenticated browser's observed `batchexecute` requests. Do not guess or replay undocumented generation endpoints.

An observed project-inventory response used this layout:

- Response lines containing JSON arrays included records shaped like `["wrb.fr", rpc_id, payload_json, ...]`.
- The observed inventory RPC ID was `Zzl0ze`; decode its JSON-string payload only after checking the record shape.
- `payload[1]` held project tile records: `tile[0]` was the tile ID, `tile[3][0]` the title, and `tile[3][4]` the media ID.
- `payload[2]` held asset records: `asset[0]` was the media ID, `asset[1]` the project ID, and `asset[2]` the tile ID.
- Video records had populated video metadata at `asset[7]`; an uploaded reference image instead had populated image metadata at `asset[6]`.
- `payload[3]` contained a separate template bank. Recursively collecting IDs from the entire payload would incorrectly count these as project results.

These positions describe an observed private wire format, not a stable public contract. Validate array lengths, project membership, asset type, and tile-to-media joins against the current page before using them; if the shape changes, inspect the new response rather than guessing fields. Treat thumbnail URLs only as display resources, not canonical identifiers.

Reduce response data locally to project ID, media ID, type, title, and relevant correlation evidence. Keep raw authenticated responses private and redact signed URLs, cookies, authorization headers, account identifiers, and unrelated assets from diagnostic output.

## Validate the repair without buying a generation

Use recorded, sanitized evidence for regression tests and exercise the corrected reader against the live project in a bounded read-only pass. Require these cases:

- Existing clips remain old when the baseline DOM was empty or their thumbnails become visible later.
- Opaque CDN paths and rotated signatures cannot create new media identities.
- Duplicate thumbnail nodes deduplicate to one stable media ID.
- Uploaded reference images and template-bank records are excluded from video results.
- A new video from another prompt or job is not accepted for the intended clip.
- Unknown response layouts fail closed instead of manufacturing an empty inventory.
- Provider failure and local tracking failure retain separate states.
- Updating one attempt's result preserves reference and QA fields changed by another worker.

A passing reconciliation test proves the tracking behavior only. Declare generation recovered only after the intended output is identified, downloaded, decoded, reviewed, and made accessible to the recipient.
