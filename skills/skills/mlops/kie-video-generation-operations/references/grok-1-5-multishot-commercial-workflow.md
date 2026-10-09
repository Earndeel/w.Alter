# Grok Imagine 1.5 — multi-shot commercial workflow

Use this recipe for a 10–20 second vertical advertisement that needs exact product geometry, exact commercial copy, several visual beats, and deterministic release QA. It supplements the live API contract; verify the current Kie model page before every paid run.

## Why separate shots

A single long text-to-video request is acceptable for one continuous UGC scene, but it is a weak fit for a premium ad with product reveal, price card, family benefit, bonus product, CTA, and end card. Generate independent text-free shots, then assemble them deterministically. This gives bounded retries: reject one bad two-second plan instead of paying to regenerate the whole master.

## 1. Forensic the reference first

1. Probe duration, dimensions, frame rate, codecs, audio channels, loudness, and true peak.
2. Detect candidate cuts, then confirm them with a 2 fps contact sheet and full-resolution frames near every boundary.
3. Transcribe the actual reference audio with word timestamps; map spoken phrases to visual beats.
4. Record typography, palette, logo position, active-word subtitle behavior, safe zones, transitions, and legal footnotes.
5. Separate elements that can be reused from those that conflict with the new brief. Never leave a forbidden product in a reused roof/background shot simply because the foreground changed.

## 2. Build a clean product reference

For product fidelity, use image-to-video from a clean 9:16 keyframe:

- crop out all supplied copy, logos, prices, badges, UI chrome, and watermarks;
- keep the full product silhouette, mounts, fan, tank, and enough architectural context;
- resize to the target vertical ratio before upload;
- inspect the crop at full resolution before spending credits.

With one `image_urls` item, let the source ratio govern output unless the current model page explicitly allows `aspect_ratio` at the same time.

## 3. Submit bounded Grok tasks

A practical 15-second ad can use four generated shots plus deterministic cards:

- 3–4 s I2V product reveal;
- 2–3 s T2V house/offer context;
- 2 s family/benefit shot;
- 2 s bonus-product shot;
- remaining time for aid card, CTA, and end card composed locally.

For every visual prompt:

- request one continuous shot and one simple camera move;
- state the required subjects and stable geometry;
- explicitly prohibit generated text, logos, digits, badges, watermarks, duplicate equipment, and the brief’s forbidden objects;
- reserve negative space for later copy;
- describe physically impossible failure modes when the subject invites them (for air conditioning: no visible water, fabric, smoke, mist, ribbons, or material jet).

Simple phrases such as `slow dolly-in`, `subtle upward tilt`, or `low gimbal push-in` worked reliably; the mistake is overloading a short prompt with competing camera choreography, not using camera language at all.

## 4. QA each provider output before assembly

For every clip:

1. Download immediately; if Python `urllib` gets HTTP 403 from a Kie temporary result URL, confirm it is live with `curl -I` and download with `curl -fsSL`.
2. Probe duration, dimensions, frame rate, streams, and file size.
3. Build a start/middle/end contact sheet.
4. Reject product drift, duplicate equipment, forbidden objects, generated text, anatomy defects, visible airflow-as-material, or missing negative space.
5. Regenerate only the failed shot with the defect named explicitly in the prompt.

Record every consumed task, including rejected outputs. At the observed 720p Grok 1.5 route, billing was 3 credits per generated second; verify the actual balance delta rather than relying on this historical rate.

## 5. Deterministic post-production

- Generate exact narration separately; measure its rendered duration and obtain word timestamps from the actual voice file.
- Use Pillow, ASS, Remotion, or FFmpeg for prices, logos, CTA, legal copy, and active-word subtitles. Never trust generated typography for a commercial master.
- Normalize every video branch to the same size, frame rate, timebase, pixel format, and sample aspect ratio (`setsar=1`) before FFmpeg concat.
- Mix voice and licensed/approved music explicitly; pad and trim both to the master duration.
- Compose a deterministic end card and keep all claims inside explicit safe margins.

If a reused source segment already contains subtitles, do not stack a second global caption layer. Either use a clean source, mask/rebuild the embedded text, or suppress the new layer only when the embedded phrase and its timing match exactly. Probe the last 0.25 seconds of the reused segment so it does not reveal the next source sentence prematurely.

## 6. Release gate

A final master passes only after:

- complete FFmpeg decode with no errors;
- exact requested duration and format;
- measured audio loudness/peak and present stereo/mono stream as intended;
- final-audio transcription against canonical copy;
- 2 fps whole-program contact sheet;
- higher-cadence probes around every reused-caption and scene boundary;
- explicit checks for forbidden objects, product stability, text clipping, safe zones, duplicate captions, CTA collisions, and end-card legibility;
- claim/brand/legal approval called out separately from technical QA.

Static end cards may trigger `freezedetect`; interpret that signal against the designed timeline instead of treating every intentional hold as a defect.
