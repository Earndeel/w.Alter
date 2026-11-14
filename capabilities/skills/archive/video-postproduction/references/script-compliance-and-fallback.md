# Exact spoken-script compliance and fallback

Use this reference whenever a video brief contains client-supplied spoken copy, dialogue, narration, or an on-camera presenter who must say specific words.

## Core distinction

There are two separate acceptance criteria:

1. **Audio-copy compliance:** the delivered audio contains the client script, in the required order, without silently added or omitted copy.
2. **Visual speech compliance:** the visible presenter appears to speak that copy (lip-sync / on-camera delivery).

A generated prompt, a Flow composer preview, or a successful render status proves neither criterion. A deterministic TTS replacement can satisfy audio-copy compliance only; it does not satisfy visual speech compliance.

## Release workflow

1. Store one canonical script before generation. Preserve punctuation, accents, numbers, proper nouns, and the required order. Split it into clip boundaries only after the canonical whole is saved.
2. Include the canonical script in the generation prompt when the provider is expected to render speech, but treat that as an instruction, not evidence.
3. After export, extract the audio from the actual candidate MP4 and run ASR in the requested language. Normalize only harmless punctuation/diacritic differences, then compare the ordered transcript to the canonical script. Keep the transcript and mismatch summary in the run record.
4. Inspect the presenter at native/full resolution around the spoken sections. Mark audio-copy and lip-sync separately as pass/fail; do not infer lip-sync from the existence of an audio stream.
5. Reject the candidate if the transcript is missing, materially mismatched, or the requested on-camera delivery is visibly absent. Do not rename a file `verified` merely because its metadata or prompt is correct.

## Decision matrix when the provider ignores dialogue

| Requirement | Correct action | Label in delivery |
|---|---|---|
| Voiceover only is acceptable | Mute the untrusted original speech and synthesize the exact canonical script; keep only an approved ambience/music bed | `voiceover` / audio-copy checked; not lip-sync unless separately proven |
| Presenter must visibly say the script | Regenerate with a provider/model capable of the required speech, or use a dedicated lip-sync step; inspect and transcribe again | `lip-sync verified` only after both gates pass |
| User has not authorized a paid rerender and the trade-off is material | Report the mismatch and present the voiceover-vs-rerender trade-off before spending credits or changing the creative | Never silently substitute TTS for an on-camera requirement |
| ASR is unavailable | Do not claim script compliance. If an explicitly approved voiceover fallback is delivered, state that it was synthesized from the canonical text but remains ASR-unverified | `script-unverified` / no `verified` claim |

A TTS fallback must use the canonical text exactly, remove or suppress the provider's incorrect speech rather than mixing two intelligible dialogues, and keep the audio stream aligned to the requested duration. Silence after a short narration is preferable to an audible wrong dialogue underneath it, but disclose the creative trade-off.

## Generated text and logo cleanup

Provider-generated text is untrusted even when it looks like a plausible brand, product label, certification, URL, or legal claim. Inspect the full-resolution contact sheet and the first frame of every close-up; do not limit QA to the known platform watermark corner.

For a small fixed hallucinated label:

1. Create a glyph-shaped mask with a small antialiased halo, not a panel-sized rectangle.
2. Apply `removelogo`/inpainting or a localized patch only while that label is visible.
3. Inspect the exact first frame and several nearby timestamps after every pass. Reject residual letters, a visible rectangular blur, a white band, or a texture discontinuity.
4. Keep the smallest acceptable mask. If local reconstruction remains obvious, replace the shot or disclose the artifact rather than shipping a polished-looking defect.

Check filter options with `ffmpeg -h filter=<name>` before using provider-specific examples; do not assume every build exposes the same `delogo` options.

## Evidence checklist

Keep these artifacts together for a script-sensitive run:

- `canonical_script.txt`
- generated prompt/run record
- candidate MP4 and extracted audio
- ASR transcript with timestamps (or an explicit `ASR unavailable` note)
- normalized comparison result
- native-resolution frames around speech and cleanup areas
- final `ffprobe` JSON and full FFmpeg decode result

The delivery message must state whether the result is **audio-copy compliant**, **lip-sync compliant**, both, or unverified. Never collapse those into a single vague “final” claim.
