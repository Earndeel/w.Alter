# Google Flow browser generation and export

Use this reference for authenticated Google Flow work driven through Camoufox/Playwright when a campaign requires reference media, exact dialogue, strict visual exclusions, export, and final QA.

## Reference-media preparation

- Do not upload full PDF pages when the output must contain no writing. Crop the source document down to clean product/installation visuals first.
- Inspect every crop with vision and reject even partial letters or logo fragments before upload; models can reproduce whatever they are shown.
- Preserve a clean portrait separately as the identity anchor.

## Reliable file-input injection

Flow uses a hidden `input[type=file]`. Synthetic upload works only when the native `files` setter is restored and used:

1. Build a `File` in the page context from local bytes and add it to a `DataTransfer`.
2. If a previous attempt installed an own `files` property, run `delete input.files` first.
3. Call `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'files').set.call(input, dt.files)`.
4. Dispatch bubbling/composed `input` and `change` events.
5. Verify the filename appears in Flow's media library before continuing.

Flow's picker is effectively single-select in this workflow: selecting another option deselects the first. Add references to the prompt one at a time, reopen the picker, and verify the composer attachment DOM after each addition. Video references may render as a `<video>` plus a `videocam` icon rather than an `<img>`; count both media types before concluding that an attachment failed.

## Submission and state verification

- Keep generation settings explicit and re-check them immediately before submission: mode, duration, aspect ratio, output count, and model.
- Type the entire prompt once, then read the real `contenteditable` text back and compare its character count, beginning, ending, exact dialogue, and exclusion clauses.
- Click Create once. A cleared composer is evidence that the submission was accepted, not that rendering succeeded.
- Flow's accessibility snapshot can repeat stale `Échec` labels even when the generated card is complete. Do not relaunch from snapshot text alone.
- Verify state with three independent signals: a screenshot of the visible card, a distinct media ID in the new `<video src>`, and a new `/edit/<id>` link. Deduplicate media IDs before deciding how many jobs exist.

## Authenticated export

A direct page `fetch()` of `media.getMediaUrlRedirect` may hit an opaque cross-origin redirect. Prefer the editor's native **Télécharger** button:

1. Navigate to the generated video's `/edit/<id>` page.
2. Click the download button once.
3. Locate the newly created Playwright artifact or browser temporary file by modification time and size.
4. Copy it to a stable staging filename.
5. Prove it is a real MP4 with `file` and `ffprobe` before QA.

This is a positive export path, not a claim that fetch-based export can never work.

## Strict no-text/no-logo campaigns

When the brief says no CTA, logo, or writing, the constraint applies to the whole pipeline:

- no generated typography, labels, title cards, CTA panels, logo, or reserved CTA space;
- no post-production CTA or logo added later;
- provider-visible watermarks count as logos and must be removed from a separate copy;
- preserve originals and QA the cleaned output at full timeline density.

For a 10-second portrait clip, a useful minimum is a 2 fps contact sheet plus high-resolution first/end frames and several bottom-right crops. For a fixed four-point Flow sparkle, prefer a tightly shaped `removelogo` bitmap mask over a broad rectangular `delogo` blur, which can leave an obvious box. Compare source and cleaned crops at the beginning, middle, and end over different backgrounds (hands, fabric, foliage, and metal), then inspect the full-frame contact sheet because an enlarged local repair can look severe while remaining invisible at delivery scale. Treat the provider watermark, scene-generated text, and invisible provenance metadata as separate classes. Never claim invisible markers were removed.

## Audio and continuity QA

- Run `ffprobe` for streams, duration, dimensions, frame rate, and codecs.
- Measure loudness and transcribe the actual audio locally when possible; compare dialogue word-for-word with the approved script.
- Transcribe each generated clip independently before assembly, then verify audio presence and volume in each half of the final master.
- Whole-file Whisper VAD can omit a later speech block separated by silence or a hard join. If that happens, do not declare the master silent: isolate the affected time range, confirm its audio level, and re-transcribe that segment with VAD disabled.
- For a two-clip sequence, attach clip A itself as the primary continuity reference when Flow accepts it, alongside the portrait and clean technical references.
- Inspect the join independently after concatenation: identity, wardrobe, lighting, camera direction, lip sync, audio level, and the first 0.25 seconds after the cut.
- Finish with black/freeze detection, final loudness, exact duration, and a SHA-256 hash.
