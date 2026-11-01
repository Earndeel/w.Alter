---
name: minimax-h3-native-ugc
description: Use when generating native MiniMax H3 UGC via Kie.ai.
version: 0.1.0
platforms: [linux, macos, windows]
---

# MiniMax H3 native UGC

## When to use
Use for MiniMax H3 via Kie.ai, especially native-voice, single-character, variable-duration UGC. Load `kie-video-generation` for shared account/task operations and `reference-video-fidelity` plus `flow-selfie-physical-qa` for acceptance. Do not confuse the exact H3 contract with legacy Hailuo. This skill stores procedures, not credentials, credit balances or project progress.

## Prerequisites
Use Walter's web front door to read the live official sources before paid submissions:
- https://kie.ai/minimax-h3
- https://docs.kie.ai/market/minimax-h3/text-to-video
- https://docs.kie.ai/market/minimax-h3/reference-to-video
Obtain renewed script/prompt approval after a rejection or creative rewrite. Do not purchase credits, add paid storage, substitute models or retry automatically without approval.

## Contract discovery
Observed exact IDs: `minimax-h3/text-to-video`, `minimax-h3/reference-to-video`. Both input schemas define `prompt` (1–7000 chars), integer `duration` (4–15 inclusive), `resolution` (`768P` or `2K`) and `aspect_ratio`. Explicitly set requested 2K/9:16. Reference-to-video defaults to adaptive ratio; T2V does not permit adaptive. No `generate_audio` field was present: direct original native speech and absence of generated music through the prompt instead of inventing a parameter. Recheck these observations against current sources.

For a visual beat under four seconds, describe multi-shot sequencing inside one valid 4–15-second generation. The marketing FAQ can say 5–15 seconds while the API enum includes 4: preserve the contradiction and follow the actual schema rather than silently changing the user's duration.

When normal extraction omits API properties/prices, inspect the SAME official page's embedded JSON using `terminal` and a bounded Python parser. Product pages expose model-specific `pricingDesc` in `__NEXT_DATA__`. Apidog/Remix docs can expose flattened devalue arrays in `window.__remixContext.streamController.enqueue(...)`: decode the JavaScript JSON string, then the JSON array, resolve `_N` dictionary keys and numeric graph references, and select the object with prompt/duration/resolution. Save the resolved schema with `write_file`; do not dump full HTML or infer fields from adjacent models.

## Procedure
1. Calculate per-scene dialogue length and costs with a tool, then obtain approval of the rewritten creative. Observed rates: 2K 13 credits/s ($0.065/s), 768P 8 credits/s ($0.04/s). Generated duration PLUS input-video duration is charged at that resolution rate. First five input images and input audio were listed as free; further images 4 credits each. Re-read current pricing, disclose retries separately and label account balances as snapshots.
2. Generate one anchor speaker scene first. Inspect actual full-speed image AND native sound before accepting its natural delivery, identity and selfie geometry. A clear voice or codec/hash test cannot certify natural prosody.
3. Extract one clean accepted portrait and a clean 2–15-second segment of native speech from that SAME take. Condition later reference-to-video jobs with both `reference_image_urls` and `reference_audio_urls`, asking for matching timbre/accent/identity while speaking the NEW exact dialogue, never replaying the reference. Do not reuse a rejected voice or silently dub with external TTS.
4. Verify actual uploaded reference media at the exact returned URLs before binding them. Use documented temporary uploads; do not introduce Cloudflare/R2 costs without approval. Treat retention as a service constraint to recheck, not guaranteed persistence.
5. Submit the exact approved model/settings. Read back the task receipt and inspect downloaded originals; upscaling is not proof of native 2K. Inspect each take for spoken words, stable voice, fluency/breathing, lip-sync, physical selfie camera, panel geometry, no generated lettering/music and no unsafe actions.
6. Only after source acceptance, add one caption track and music in postproduction. Reject duplicated headline/karaoke messages even without intersecting boxes. Cut on gestures or phrase boundaries, not evenly spaced zoom cycles. Measure the final useful word and reused source intervals; do not pad with repeated smiles or a long music-only tail.

## Reference constraints to recheck
- Images: max 9; <=30 MB each; 256–5760 px sides; aspect ratio 0.4–2.5; JPG/JPEG/PNG/WEBP/HEIC/HEIF; HTTP(S) or OSS addresses.
- Audio: max 3 WAV/MP3; <=15 MB each; 2–15 s per segment; <=15 s total. Audio cannot be used alone: accompany it with image or video.
- Video: max 3 MP4/MOV; <=50 MB each; 2–15 s per segment and <=15 s total; H.264/H.265 video with AAC/MP3 audio; 256–5760 px sides; aspect ratio 0.4–2.5; 23.976–60 fps.

## Prompt guardrails
Show the product immediately; request neat parallel solar rows with coherent physical geometry. Establish one fictional speaker and genuine front-camera geometry: device outside frame, one foreshortened holding forearm, free hand available, no third-person filming or dangerous roof walking. Specify scene-specific actions, exact dialogue once, conversational emphasis and natural breaths. Do not force vowels to fill duration or authorize voice retiming. Reserve all captions and music for postproduction, rejecting generated captions, signs, jingles and a second narrator.

## Verification
Keep pricing/schema evidence, task receipts, downloaded media probes and actual audiovisual review. Inspect the mixed FINAL export as well as raw clips. Report contradictions honestly: intelligibility/native provenance do not refute a user's criticism; generic automated praise does not establish editorial quality. Completing a preproduction pack is not delivering a regenerated video.

- Do not use full-take Whisper agreement as proof that no repeated speech exists: it can silently collapse an immediately repeated clause. When native review flags a repetition that ASR omits, isolate the disputed interval, obtain an unprimed focused audio transcription, and independently transcribe overlapping short crops. If both occurrences are demonstrated, remove the redundant occurrence with synchronized video/audio cuts and review the actual edited take before acceptance.
- Resolve rhythm claims against measured pauses instead of accepting generic 'continuous speech' praise. Cut the middle of pauses on source-frame boundaries while protecting phonemes; never synthesize captions over unverified dialogue or stretch native voice to meet an arbitrary runtime.
- Distinguish successful task generation from a complete download. Inspect partial-byte growth and original Content-Length before attributing a slow transfer to a failed generation. Prefer a bounded alternate download/resume of the exact same result URL, then require native media probing and full decoding; do not submit a paid regeneration for a transport problem.
