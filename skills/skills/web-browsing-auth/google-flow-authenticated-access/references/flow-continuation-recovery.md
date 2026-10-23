# Flow continuation recovery recipe

Use this reference when a user supplies an exact Google Flow edit URL and asks
for the next clip with the same actor. It records the tested recovery path for
the case where the source clip is an Omni Flash video and the native extension
control is disabled.

## Observed failure and fix

- Symptom: after attaching a reference and filling the prompt through
  `/tab/type`, Flow shows `Application error: a client-side exception...` when
  `Créer` is pressed. No new media ID is visible in the project, so do not
  assume a paid job was accepted.
- Cause in this workflow: the prompt is a Slate/contenteditable editor;
  locator filling made the text visible but did not reproduce the editor's
  keyboard events/state transitions.
- Fix: focus the visible `[contenteditable="true"]`, send the prompt through
  `/tab/keyboard-type` (real Playwright keyboard events), and click the final
  `arrow_forward`/`Créer` control with `/tab/click-at` using a fresh bounding
  rectangle. Verify the button has `aria-disabled="false"` first.

## Tested sequence

1. Keep the authenticated Camoufox `userId` and `tabId`; run `/health` first.
2. Navigate directly to the supplied `/project/.../edit/...` URL. Inspect the
   actual `<video>` source, duration, last frame, prompt, and visible timeline.
   Do not choose the actor from the root grid.
3. Use the timeline `+` menu only if native `Prolonger (Veo 3.1 - Lite)` is
   enabled. If the source is Omni Flash and the option is disabled, go to the
   project root and use the **Créer** composer instead.
4. Open the `add_2` media picker. Select the exact existing video by title and
   media type (the picker can show it even when the root grid looks stale). The
   selected row must expose `aria-selected=true`; then press `Ajouter au prompt`.
   Prefer the video over a saved frame because it carries motion and identity
   context. A saved final frame is a fallback only.
5. Confirm Agent is off (`aria-pressed=false`) and the composer still exposes
   `Vidéo · 10s`, `crop_9_16`, and `1x`.
6. Focus the visible contenteditable, call `/tab/keyboard-type`, then inspect
   its `innerText` and the submit button state. Use `/tab/click-at`, not a stale
   semantic ref, for the final click when an overlay or portal is involved.
7. After clicking, inspect the live page. An error screen or unchanged project
   is a failed submission; refresh before deciding whether to retry. Never
   launch a second paid click solely because the UI was reassuring.
8. Poll the project/card state with a bounded interval. A progress card may
   disappear during a refresh; reload the project and look for a new media
   redirect identifier tied to the newest prompt. Old play icons and prior
   `Woman showing...` cards are not proof of the new result.

## Export and candidate selection

`POST /tab/fetch-binary` returns the raw response body for a media redirect, not
necessarily JSON. Save `response.content` only after HTTP 200 and
`content-type: video/mp4`; do not attempt JSON/base64 decoding when the first
bytes are an MP4 `ftyp` header.

Run `ffprobe` for duration, dimensions, frame rate, codecs, frame count, and
size, then decode the complete file with:

```bash
ffmpeg -hide_banner -loglevel error -i candidate.mp4 -f null -
```

When multiple fresh IDs are present, extract source-end, candidate-start, and
candidate-end frames plus a storyboard around 0/2/4/6/8/10 seconds. Select the
candidate associated with the newest prompt/card and confirm that the start
matches the source end, the intended product action is visible mid-clip, and
there is no identity/location reset. A valid 10-second MP4 alone is not enough
for delivery.

## Minimal media evidence to retain

Keep the source media ID, selected continuation media ID, prompt text, measured
`ffprobe` result, and the storyboard/contact sheet path. Never retain or print
cookie values, raw authenticated state, or account credentials.
