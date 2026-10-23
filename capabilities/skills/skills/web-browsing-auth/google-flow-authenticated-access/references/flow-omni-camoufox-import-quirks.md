# Gemini Omni Flow — composer and reference-import refinements

Use this reference with `google-flow-authenticated-access` when a short
reference-conditioned video is generated through the headless Camoufox Max
service.

## Verified composer sequence

1. After the authenticated home check, dismiss any one-time Flow update dialog
   using the current semantic `Commencer` control.
2. Open `Nouveau projet` and inspect the live composer. The default composer may
   be an image configuration (`Nano Banana 2`, `crop_16_9`, `x2`), even when the
   requested task is video.
3. Open the generation-settings control and select the `Vidéo` tab first. For
   Gemini Omni, the live model label is `Omni Flash` in the French Flow UI.
4. Select the requested duration explicitly (`10s` for this class of task), keep
   `16:9`, and set the variant tab to `x1`. Verify the composer summary reads
   `Vidéo · 10s`, `Omni Flash`, `crop_16_9`, and `x1`; verify the displayed cost
   before submission.
5. Keep `Agent` off (`aria-pressed=false`). Agentic mode is a different path and
   must not be mistaken for direct video creation.
6. Select `Ingrédients` only after the video settings are correct. Preserve the
   approved reference order: environment, Character A, Character B.

## Reference upload gate

- The hidden `input[type=file]` can report `multiple=true`, but setting its files
  is not proof that Flow imported them. Verify the resulting thumbnail/chip,
  media item, or media ID in the live UI/snapshot after the upload completes.
- The first media selection can open a Flow `Notification` dialog about third-
  party rights and responsible video creation. Accept the current semantic
  `J'accepte` button before attempting later reference selections; otherwise
  later `DataTransfer` assignments can merely replace the DOM input without
  adding media to the composer.
- Do not send several original multi-megabyte images in one `/tab/evaluate`
  request. The Camoufox HTTP body can reject that request with HTTP 413 before
  the page receives it. Preserve the originals, compact each image in memory
  (for example, bounded JPEG dimensions/quality), and upload in a small batch
  or sequentially. A successful `input.files` result still requires a Flow UI
  verification afterward.
- If a browser-side upload event produces no UI change, inspect the body/snapshot
  for the rights notification and current media controls before retrying. Do not
  press `Créer` as a probe.

## Cookie-output safety

Keep decrypted cookies only in memory while extracting and injecting them. Never
print, return, JSON-serialize to stdout, save, or include in a tool result the
cookie values, decrypted key, or raw SQL rows. Diagnostic output may contain only
counts, domains/host counts, and a tightly allow-listed set of cookie names
needed to confirm session-integrity cookies are present.

## Submission boundary

Before clicking `Créer`, re-snapshot and confirm the live settings, exact prompt,
reference attachments/media IDs, `Agent=false`, and displayed cost. A submission
acknowledgement is not a deliverable; download the resulting MP4 through the
authenticated media route and run `ffprobe` plus visual QA before reporting
success.