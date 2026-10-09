# Google Flow / Omni through Camoufox

Session-specific operational notes for the class-level `reference-to-video-ugc` workflow. This file contains no account credentials or session cookies.

## Verified UI sequence

1. Open `labs.google/fx` in the authenticated Camoufox session and create/open a Flow project.
2. In the prompt composer, open `add_2` / **Ajouter un contenu multimédia**, choose the upload path, and attach the approved reference. The local bridge used in the run had no direct filechooser API; page-context injection worked:
   - locate `input[type=file]` after opening the media dialog;
   - create a browser `File` from the local image bytes;
   - add it to a `DataTransfer` and assign `input.files`;
   - dispatch a bubbling `change` event;
   - wait for the media dialog to show the asset and click **Ajouter au prompt**.
3. Open **Paramètres** and verify the live labels. The run showed **Omni Flash**, portrait **9:16**, and output multipliers `1x/2x/3x/4x`.
4. Submit a prompt that states `exactly 10 seconds`, one continuous UGC action, the identity/wardrobe/location anchors, and explicit exclusions for subtitles, logos, watermarks, device-in-device framing, and invented signage/claims.
5. Wait for the paid confirmation. The first verified request was displayed as: `Voulez-vous que je lance la génération de cette vidéo (1), qui coûtera 15 crédits ?` The request was accepted and entered the queue.

## Spend and duplicate-billing guard

The x2 control was selected during the run, but the Flow Agent confirmation still said `video (1)` and 15 credits. Therefore x2 is not proof that two videos will be created. Always read the confirmation’s count and price. For two distinct variants, submit separate prompts or use a count setting only after the confirmation explicitly reflects two outputs; never blindly click twice while the first request is queued.

The queue message observed was: `I've scheduled your UGC testimonial video. It's currently in the queue due to high demand...` Treat that as an accepted queued state. After any client-side exception, reload the same project and inspect the collection before resubmitting. In the run, reloading restored the project and showed `Man in greenhouse testimonial video`; no second asset was visible, so a second generation was not assumed or reported as complete.

## Export and verification

A generated Flow video exposed a media URL of the form:

```text
https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=<media-id>
```

The browser-authenticated page returned `HTTP 200`, `video/mp4`, and a measured content length for the first asset. Plain `curl` and a `requests` call without the live browser context returned `401`; page-side `fetch` was also blocked by CORS even though Flow exposed the URL to its video element. This is an export/authentication boundary, not evidence that a queued task failed.

Use Flow’s authenticated native download or a binary fetch through the authenticated Playwright context. Keep the transfer host-restricted if adding a local Camoufox helper route; never make a generic proxy. After transfer:

```bash
ffprobe -v error \
  -show_entries format=duration,size:stream=index,codec_name,width,height,r_frame_rate \
  -of json output.mp4
```

Do not deliver a Flow card, thumbnail, media URL, or claimed local path as the finished artifact. The completion gate is an actual non-zero MP4 plus measured duration, dimensions, codecs, audio presence, and file size.

## Prompt design notes

For a reference-preserving male UGC test, use two camera variants rather than two unrelated scenes:

- **Variant A:** continuous front-camera selfie, chest-up at eye level, one small conversational gesture.
- **Variant B:** slightly wider chest-up handheld take, shoulders turn once toward the installation, then return gaze to camera.

Keep spoken French short enough for 10 seconds and descriptive rather than making unverified product promises. Generate without baked-in subtitles, captions, logos, or visible brand text; add approved copy later during post-production after the product fact sheet is locked.
