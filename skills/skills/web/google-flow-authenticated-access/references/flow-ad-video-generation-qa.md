# Flow direct video generation and QA recipe

Use this reference after authenticated access has been proven with a fresh `PRO`
snapshot. It records the reusable failure modes and verification gates discovered
while generating a vertical advertising clip.

## Safe prompt submission

1. In the `Créer` composer, confirm the exact model, duration, aspect ratio and
   variant count immediately before typing. For a single vertical clip, verify
   `Vidéo · 10s`, `crop_9_16` and `1x`.
2. Attach the identity/product reference and confirm its chip or preview is in
   the composer. If using a still extracted from an older render, remove any
   visible platform star/watermark before upload.
3. Flow's prompt field is Slate/contenteditable. Use real keyboard input, but
   pass one single-line string to `/tab/keyboard-type`. Newline characters are
   interpreted as Enter events and can submit each paragraph as a separate,
   incomplete generation. Replace paragraph breaks with semicolons and explicit
   time ranges.
4. After typing, take a fresh semantic snapshot and confirm the full prompt is
   visible. If typing times out, inspect first; do not blindly retry, because the
   text may already have been accepted or submitted.
5. Click Create once. Keep the prompt text and the creation timestamp in a local
   run record, but never store cookies, tokens or account balances in it.

## Progress and candidate selection

Record the pre-submit media redirect IDs, then click Create once. The
accessibility snapshot is the useful progress signal, but it is not the final
truth. The DOM's edit-link `innerText` can be empty or omit a visible percentage
while the semantic snapshot still reports `40%`.

A client-side `Application error` immediately after Create does not prove that
the paid request was rejected. Do not submit again. Wait, reload the same
project, and compare actual `media.getMediaUrlRedirect?name=` identifiers with
the baseline. A transient failure label can coexist with a job that later
materializes a new ID; conversely, success prose can exist without media. Poll
within a bounded window and accept completion only after a new media ID exports
as an MP4. Check live profile credits rather than assuming a failed-looking card
was refunded.

A malformed multiline submission can create isolated cards such as a single
"hero shot" or "product demo". Reject those for a full-ad brief. Prefer the
newest card whose prompt contains the complete single-line brief, then enumerate
actual `<video>` elements and their `currentSrc`; edit-link count is not video
count.

## Authenticated export

For each candidate media redirect, call:

```text
POST /tab/fetch-binary
{"userId":"...","tabId":"...","url":"https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=..."}
```

The route runs through the authenticated Playwright context. It can return raw
bytes rather than a JSON object: write the HTTP response body directly. Require
HTTP 200 and an MP4 signature before saving. Plain context-free HTTP requests
are not a valid substitute for this export path.

## Delivery QA

Run `ffprobe` and record measured values for duration, dimensions, frame rate,
video codec, pixel format, audio codec, sample rate, channels and byte size.
Decode the complete file with FFmpeg and reject decoder errors. Check that audio
is not silent, then ASR-transcribe any required native dialogue and compare the
normalized words to the approved copy. A volume scan proves signal, not speech.

Create a regular-timestamp contact sheet and inspect it visually. One frame per
second is enough for footage-only clips; use roughly 2 fps when screen-space
text, karaoke highlights or fast graphics animate. Confirm motivated cuts,
actor/location continuity, product geometry, hero framing, natural hands/faces,
and the intended continuity handle.

Typography rules are conditional:

- when graphics were not requested, reject generated captions, random signage,
  logos, certification marks and unrelated panels;
- when Flow-native graphics were explicitly requested, read every visible word
  and compare it to the allow-list, rejecting malformed accents, duplicate
  caption rows, gibberish, fake official marks and physical-surface text that
  should have been screen-space graphics.

Do not trust negative prompts for forbidden objects. If the same object recurs,
change composition to remove the risky region from frame before a bounded retry.
A small platform star may still appear despite a negative prompt; if the brief
specifies the known mask area `x=574:y=1137:w=60:h=50`, apply a narrowly scoped
`delogo`/interpolation pass, re-encode H.264/AAC, inspect the same corner again,
and rerun `ffprobe`.

Treat technical validity, spoken copy, visual content, generated typography and
continuity as separate PASS/FAIL columns. Only deliver after all required gates
pass or Monsieur explicitly accepts a named defect. The native-voice and
reference-style workflow is detailed in
`flow-native-voice-motion-graphics.md`.