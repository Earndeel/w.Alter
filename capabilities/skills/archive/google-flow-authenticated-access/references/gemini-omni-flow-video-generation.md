# Gemini Omni video generation in Flow via Camoufox

Use this reference when generating a short reference-conditioned video in Google Flow through an authenticated Camoufox session.

## Durable workflow

1. **Prepare the prompt before opening the credit-consuming Flow path.** Write the exact prompt to a temporary file and present it inline for explicit user validation. Do not navigate to generation or submit while the prompt is still ambiguous.
2. **Keep reference roles explicit and ordered.** State `Image1 = environment`, `Image2 = Character A`, and `Image3 = Character B` in the prompt. Upload the same three files in that order and verify that Flow displays the intended thumbnails before submitting.
3. **Re-time the prompt when the requested duration changes.** Never submit a prompt whose shot timecodes exceed the requested duration. Preserve the shot order and content, but compress all intervals so the final beat ends exactly at the target duration. For the Bulldog/Viper 15-second sequence adapted to 10 seconds, the verified boundaries are: 0.0–1.7, 1.7–3.0, 3.0–4.8, 4.8–6.4, 6.4–7.4, 7.4–9.0, and 9.0–10.0 seconds.
4. **Set Flow controls explicitly.** Select Gemini Omni, the requested duration, 16:9, and audio when the prompt contains an audio design. Do not rely on a remembered UI default; inspect the active controls immediately before submission.
5. **Use the authenticated browser route only for this Flow task.** Inject the approved Brave session into Camoufox Max, navigate to Flow, and use the UI for reference upload, model/ratio/duration selection, submission, and download. Do not silently switch to Kie.ai or OpenRouter.
6. **Verify the delivered artifact, not just the UI toast.** Download the MP4 to the project workspace, then check with `ffprobe` that duration, dimensions, aspect ratio, frame rate, video/audio streams, and codec are present. Run an `ffmpeg -f null` decode check, inspect audio levels, sample a 1-fps storyboard, and perform visual QA for identity drift, reference-sheet residue, watermarks, extra people, anatomy failures, and the requested final pose.

## Pitfalls

- A 15-second shot list pasted into a 10-second generation is not a harmless detail: Gemini may truncate the final pose or collapse the fight beats. Re-time first.
- A successful Flow submission message is not proof of a saved video. Require a local MP4 and technical QA before reporting completion.
- Preserve the original raw download separately from any trimmed/re-encoded deliverable so later visual or audio comparisons remain possible.
