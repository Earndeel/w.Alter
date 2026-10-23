# Connected two-part advertising video in Google Flow

Use this reference when a brief asks for a longer advertisement assembled from
multiple short Flow generations, especially **2 × 10 seconds → 20 seconds**.

## Required delivery contract

Do not call the job complete after writing prompts or after Flow says a render
is queued. The usable deliverable requires:

1. clip A downloaded as a real MP4;
2. clip B downloaded as a distinct real MP4;
3. both clips measured with `ffprobe` (duration, dimensions, codecs, byte size);
4. the 20-second assembly rendered and measured;
5. the final file transferred to the requested destination and read back or
   checksum-verified.

If Flow is overloaded or B remains queued, report that blocker explicitly. Do
not substitute a previous static render or claim that a queued asset is ready.

## Brief decomposition

For a connected 20-second ad:

- **A / 0–10 s:** open on the problem, introduce the mechanism, and end on a
  clear motion/eyeline that can continue into B.
- **B / 10–20 s:** begin from the same motion or last frame, show the outcome,
  explain eligibility/financing, and close with the CTA.
- Lock the same actor identity, wardrobe, location, weather/light, color grade,
  screen direction, and sound bed across both clips.
- Use the original actor image as the identity anchor for A. Once A exists,
  prefer attaching A itself as the continuity reference for B; an image alone
  cannot reliably preserve the final camera movement.

## Prompt construction

Write the prompt in English for Flow's visual planning, while keeping the
approved spoken French dialogue in quotation marks. Use a time-coded shot list:
usually four or five motivated shots per 10-second clip, with a visible visual
or camera change every 1.5–2 seconds. Specify the exact A→B handoff, for example
“clip B begins on the same fan rotation / forward walk / whip-pan direction as
clip A ends.”

Do not contradict the shot plan. If the prompt requests multiple shots, never
also say `no cuts` or `one continuous shot`; those instructions regularly force
a static talking head or confuse the agent. Say instead: `five motivated
commercial cuts, no unmotivated jump cuts, no frozen talking-head take`.

Default to keeping exact brand/legal typography out of the render: add the
verified logo, financing claim, disclaimer, subtitles and CTA deterministically
in post when copy accuracy is non-negotiable. If Monsieur explicitly asks for
Flow-native advertising graphics, do not fall back to footage-only prompting:
analyze the source's graphic system, attach a sanitized style board separately
from the product/identity reference, allow-list every permitted phrase, and
inspect animated text at roughly 2 fps. Native style matching never authorizes
copying a real institutional logo, legal mark, unwanted product or forbidden
object from the source. Do not add claims absent from the approved brief; qualify
financing with the stated eligibility conditions. The detailed conditional
workflow is in `flow-native-voice-motion-graphics.md`.

## Native generated dialogue gate

When Monsieur explicitly wants Flow to pronounce the script, do **not** add an
external TTS track by default. Put the approved French dialogue in quotation
marks, state that these are the only spoken words and must occur exactly once,
set a start/end window, and specify narrator accent, register, pace, and whether
the voice is off-camera. For connected A/B clips, ask B to preserve A's narrator
timbre, room tone, and music bed; attach A when possible because text-only voice
descriptions do not reliably preserve identity.

Native video dialogue is not self-verifying. For every exported clip:

1. extract a mono 16 kHz WAV;
2. transcribe it with a capable French ASR model;
3. compare the transcript against the approved copy, including numbers,
   eligibility language, repetitions, and inserted words;
4. treat a clear insertion, paraphrase, duplicated clause, or changed commercial
   claim as QA failure even if the visuals pass.

Use a second transcription or listening check when ASR uncertainty is
plausible. Do not silently repair native dialogue with post-production TTS when
the brief specifically requests in-model speech. A paid retry requires the
revised prompt to be shown again and the additional credit cost to be approved.

## Direct Create mode and bounded parallelism

When the brief calls for exact prompt injection, use the **Créer** composer, not
Agent mode. Before entering a paid prompt, take a fresh snapshot and verify the
composer exposes the intended video controls. For the 10-second vertical
workflow, the validated target state is `Vidéo · 10s`, `crop_9_16`, and `1x`;
these labels are accessibility text and may be duplicated, so resolve the
current refs immediately before each click.

Treat two requested clips as two independent paid operations. A second tab in
the same Flow project or browser context may return to the project/list page
without materializing a second job while one render is active. Do not infer
parallel queueing from an HTTP 200, a route change, or an unchanged composer.
After each submission:

1. capture the project state after propagation;
2. compare the count of real `/edit/` entries and actual `video`/media redirect
   identifiers against the pre-submit baseline;
3. wait a bounded interval for the second entry to appear;
4. if only one new job exists, do not click again blindly—use a separate Flow
   project and an independent authenticated browser context for the second
   clip, then verify its new project state.

This is a bounded workaround for Flow's project/context concurrency behavior,
not permission to submit unlimited retries. An app error or a reassuring route
change is not evidence that a paid render was accepted; inspect the project
before retrying to avoid duplicate credits.

Flow media libraries are project-scoped. An asset named in the source project
may appear as `Aucun résultat` in a newly created project. If the exact
reference is unavailable, import/upload a clean local frame showing the actor,
wardrobe, and setting; verify the asset title/type in the picker and its
thumbnail or name in the composer before submitting. Prefer a crop without
end-card text, platform watermark, fake certification marks, or other text
that could contaminate identity conditioning. Keep the original prompt and
reference filename in the local run record, but never print cookie values or
raw authenticated state.

## Flow UI sequence

1. Start with the correct project and confirm the target aspect ratio/duration.
2. Use the composer’s `add_2` control to open the media picker.
3. In the picker, identify the asset by its exact title and media type. Select
   the actual `role=option`/asset row and verify `aria-selected=true`; clicking
   a title, thumbnail child, or library card can open the asset-detail page
   instead of attaching it.
4. Click `Ajouter au prompt` only after the correct row is selected.
5. Confirm the composer contains the attached media (asset name/thumbnail or
   image element). The accessibility tree may misleadingly show
   `0 de contenu multimédia de référence`; do not treat that label alone as
   proof that no media is attached. For a video continuity reference, inspect
   the DOM/screenshot for the video attachment icon and, when available, the
   media redirect name. Use a screenshot/DOM check when unclear.
6. Type the prompt and submit.
7. For B, attach the generated A video when possible, not only the original
   still image.

Accessibility refs are ephemeral. Settings changes, navigation, media-picker
opening, agent responses, and asynchronous renders renumber refs. Always take a
fresh snapshot immediately before a click; never reuse a ref copied from an
older snapshot. If a click opens the wrong picker or feedback control, stop,
refresh the snapshot, and identify the current control rather than clicking a
second stale ref.

Approval text can appear duplicated in the accessibility tree. Select the
current request’s final visible `Accepter` from a fresh snapshot, then verify
that the agent reports the specific clip as scheduled. A confirmation message
is evidence of queueing only, not of a completed downloadable video. If the
same history contains both `Échec` and a reassuring `scheduled` sentence, the
failure wins until a new thumbnail/media ID is observed; never download an old
asset merely because the agent claims success.

For a paid retry, distinguish a stale approval from the current request by
checking the visible dialog/coordinates and the newest prompt immediately
above it. Do not accept repeated stale confirmations or launch parallel
retries while the service is overloaded.

## Queue and media verification

Old prompts, failed attempts, and play icons remain visible in the project
history. They are not proof of a new output. Count actual video thumbnails or
inspect the media URL names exposed by the page. A new clip must have a new
`media.getMediaUrlRedirect?name=...` identifier and must download as MP4.

If the Create click is followed by a client-side `Application error`, do not
submit again. Preserve the project ID, wait briefly, reopen that project root,
and compare media IDs against the pre-submit baseline. After a frontend crash,
a card can briefly expose a warning or a stale percentage while backend state
continues to propagate. Classify the job from durable evidence: a fresh media ID
plus an exportable MP4 wins; a failure is final only when the failure state
persists through the normal render window and no fresh media ID appears. Before
any paid retry, reopen the profile modal and read the live credit balance: a
render that looked failed may still have debited the account.

Download through the authenticated tab:

```text
POST /tab/fetch-binary
{"userId": ..., "tabId": ..., "url":
 "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=<media-id>"}
```

Require HTTP 200 and `video/mp4`, then run `ffprobe`. Do not rely on an edit
link count: Flow can expose edit pages for images, references, or videos.

## Assembly

When both files have matching H.264/AAC properties, a concat demuxer may be
used. Otherwise use a filter concat and re-encode to normalize timestamps and
formats. In either case, inspect the seam and measure the final file; do not
assume two nominal 10-second inputs produce a valid 20-second output.

## Visual QA and stop conditions

Technical validity is necessary but not sufficient. Before delivery:

1. Extract a contact sheet at roughly 2-second intervals for the full master.
2. Extract several frames immediately before and after each clip boundary.
3. Inspect full-resolution frames near the end card and any claimed CTA.
4. Reject visible invented text, fake legal/certification copy, random logos,
   signage, watermarks, broken anatomy, or a continuity reset. If exact copy
   is required, regenerate with a clean end frame or add verified overlays in
   post; do not trust a negative prompt alone.
5. Keep the raw clips, the QA evidence, and the master separate. Transfer only
   after the master passes both `ffprobe` and pixel-level review.

A service-overload failure should lead to one bounded retry after confirming
that the correct reference is attached, not to a loop of paid submissions.
Record the new media ID and validate it independently from the agent response.
If a second render is needed, surface the additional credit cost before
accepting another approval when the user has not already authorized it.
