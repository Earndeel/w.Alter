# Numbered Client Brief → Voice-Over B-Roll Master

Use this recipe when a client pack contains numbered deliverables and one variant is a voice-over edit assembled from existing clean footage.

## 1. Resolve the numbered deliverable from the source of truth

Do not infer “the last video” from the most recently edited local file. Resolve it from the named client’s direct brief or conversation first.

Capture, separately:

- deliverable number and format (`UGC homme`, `UGC femme`, `voix off`, etc.);
- exact spoken script;
- branding, logo, CTA, music, subtitle, aspect-ratio, and duration requirements;
- client-supplied documents and visual references.

Keep one canonical script string. Do not silently substitute a prior video’s script because the campaign subject overlaps.

## 2. Build a clean B-roll inventory

Prefer approved clean masters already generated for the same campaign before buying new generation credits. Create contact sheets for each candidate and map safe source intervals by function:

- hook / solar panels;
- technology / fan, duct, hybrid panel detail;
- process / drying racks and harvest;
- benefit / modernized equipment;
- CTA / verified campaign end card.

For a voice-over deliverable, a hand operating equipment is usually valid B-roll; a face or talking body is not, unless the brief explicitly allows presenters.

## 3. Preflight every trim boundary at native cadence

A 1 fps storyboard is insufficient for short generated transitions. It can miss a presenter visible for 0.1–0.3 seconds.

Before assembly:

1. inspect candidate source boundaries every 0.10–0.25 s;
2. identify the first and last frames fully compliant with the voice-over role;
3. trim to those safe points;
4. if the safe source interval becomes too short, stretch a static/detail shot slightly with `setpts` (and `minterpolate` when motion needs smoothing) rather than exposing the unwanted transition.

After assembly, render a full-program 4 fps contact sheet (80 frames for a 20 s master) and inspect every tile for transient faces, bodies, text, black frames, and logo collisions.

## 4. Fit exact voice-over copy without rewriting it

For an exact client script:

1. synthesize the full copy with an appropriate voice;
2. measure the actual audio duration;
3. if it narrowly exceeds the master, use a small `atempo` correction (about 1.03–1.08) rather than deleting words;
4. normalize with headroom and pad/trim to the master duration;
5. transcribe the rendered voice itself with word timestamps;
6. correct only verified ASR punctuation, capitalization, clitics, and campaign terms in the subtitle layer.

The prompt/script is not timing evidence. The delivered waveform is.

## 5. Align the end card to the spoken CTA

Use the final voice word timestamps to find the actual CTA start. Start the end card on that timestamp, not on an arbitrary round-number cut.

If the approved end card is shorter than the remaining master duration, retime the static/low-motion card with `setpts` to fill the interval. Disable the added corner logo at the end-card transition if the card already owns that region. Use a second ASS style in a verified empty lower band when CTA subtitles would cover the card’s existing copy or button.

## 6. Add a light music bed

Use a licensed or locally generated bed at the master sample rate. Keep it below narration and sidechain-compress it from the voice so it returns in pauses. Measure hook, speech, pauses, CTA, and full-program levels separately; a global mean alone cannot prove that the music is subtle.

## 7. Release gates

Do not call the file final until all pass:

- exact numbered brief and script confirmed from the client source;
- full decode succeeds;
- duration, resolution, frame rate, and audio streams match the brief;
- actual delivered narration transcribes to the canonical script;
- representative active words highlight correctly;
- no unwanted presenter appears in the voice-over body at 4 fps review cadence;
- added logo is stable in body footage and absent/relocated on the end card as designed;
- CTA subtitle and campaign end card remain readable;
- no black frames, clipping, or audio peaks at/above full scale.

## THALEOS session example

For Élie’s three-video pack, “the last video” meant numbered **Video 3 – Voix off**, not another revision of the woman’s video. The exact brief was recovered from Élie’s WhatsApp conversation. The final 20 s master reused approved solar-panel, ventilation, drying-rack, harvest, equipment, and MaPrimeSerre end-card footage. A 1 fps QA initially missed sub-second presenter transitions; source-boundary probes and a final 4 fps contact sheet exposed and removed them. The CTA began at 16.00 s in the rendered voice, so the end card started there and the added Ministry logo was disabled at the same boundary.
