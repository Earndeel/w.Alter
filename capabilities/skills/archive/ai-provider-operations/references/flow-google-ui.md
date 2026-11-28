# Google Flow UI generation quirks (browser-driven media provider)

Drive flow.google.com's generation agent and asset library through headless browser automation. Provider-level quirks only; generic gates live in `provider-and-media-gates.md`.

## Prompt policy wording
- For legal-crop content (industrial hemp), write "chanvre légal / exploitation horticole" and describe planting, watering and tending. Naming the crop "cannabis" together with loading plants into containers reads as trafficking and returns the refusal "Cette génération pourrait enfreindre nos règles".
- A refusal clears the composer including its ingredient chips and may leave the prompt in a non-obvious field. Re-verify prompt location and re-bind every chip before resubmitting.

## Agent chat flow
- The generation agent answers with a rewritten storyboard plan and asks for plan confirmation BEFORE the billable gate ("…1 vidéo, qui coûtera N crédits ?"). Verify the plan text against the brief — scene order, wardrobe, dialogue quotes, duration, no-text — before confirming; the plan is the contract the renderer follows.
- Cost-gate rows are `div.option-row`, not `button`/`[role=button]`, and their textContent concatenates icon and label with no separator ("checkApprouver"); accessibility refs miss them. Dismissed or superseded gates stay on screen as `option-row read-only` with dimmed labels. Click only the LAST non-read-only "Approuver" row — a stale gate submits the older plan without later-added ingredients.
- Ingredient chips attach to the NEXT message only; they never join an already planned generation retroactively. To add one to a pending request, send a follow-up message carrying the chip and wait for the agent to re-plan. Chips vanishing from the composer after submit means the message consumed them.

## Composer state before submit
- If the composer's model menu lists only image models (Nano Banana family), the composer is in image mode and the submission produces an image. Verify a video model (Omni/Veo family) and the 9:16 ratio chip before the send click.
- A usage-rules dialog ("Règlement sur les utilisations interdites…" offering J'accepte) can silently swallow uploads and submissions; accept it before diagnosing a dead file input or a stuck upload.

## Duration
- A bound video reference raises the quoted price but does not automatically extend output length: the fixed duration setting (e.g. 10s) still wins. Verify the duration readout before the billable click. When the required length exceeds the cap, generate missing scenes as separate clips and assemble locally (ffmpeg split/concat) to the target order and length — that local repair is sanctioned, not a workaround to avoid.

## Asset download
- Resolve a generated asset by opening ITS tile in the editor, then take the strictly new media UUID from `performance.getEntriesByType('resource')` (`flow-content.google/video/<uuid>`). A plain tile click loads only a thumbnail and adds no video resource entry, and hover previews of other tiles enqueue old asset URLs into the same list even newest-first — the single most recent entry can be a different asset. Fetch the signed URL with a plain uncookied GET; validate bytes with ffprobe and full decode. Never strip signatures or log signed query strings.

## Scene editor
- The editor's edit-by-prompt can consume a message and produce no response, no spinner, and an unchanged single-clip timeline. Treat an unchanged timeline after a short wait as a no-op: generate the missing scene through the agent chat and assemble locally.

## QA
- Triage with a tiled contact sheet (ffmpeg `tile` filter) for scene order, wardrobe continuity and burned-in text, then full frames per scene for identity and captions. Verify exact duration, resolution, audio presence and the requested scene order before delivery.
