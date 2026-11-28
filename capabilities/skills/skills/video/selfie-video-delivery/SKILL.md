---
name: selfie-video-delivery
description: "Use when completed selfie clips need post-production, Whisper speech analysis, and a physical credibility check before delivery or an authorized retry."
type: workflow
requires: [video-postproduction, whisper, flow-selfie-physical-qa]
---

# Selfie Video Delivery

Use this chain when all three stages apply. For a standalone edit, speech analysis, or generation request, use the relevant sub-skill directly. Start with completed media and record the clip roles and order, requested edits and output format, speech task, approved script if exact wording matters, and expected selfie actions. Do not treat a pending preview as an input.

## 1. Prepare the candidate MP4

Load video-postproduction with skill_read. Assemble or revise the completed clips as requested, or inspect the existing MP4 if no edit is needed. Before passing it on, confirm that the candidate plays through, matches the requested format and clip order, retains the intended audio, and passes the visual checks relevant to the edit. Resolve failures here rather than analyzing the wrong export.

**Handoff to Whisper:** Candidate MP4 path and revision, duration, clip roles and seam times, speech task, and approved script if applicable. If using extracted audio, record which candidate it came from.

## 2. Establish what is audible

Load whisper with skill_read. Run the requested transcription, translation, or language identification on the candidate's actual audio. Use an original-language transcript for exact-copy checks; a translation is not evidence of verbatim compliance. Check timestamps against the candidate duration and compare required wording in playback order across joins. Flag uncertainty or discrepancies rather than marking them as passes. If required speech verification is unavailable or inconclusive, hold release; a confirmed mismatch may proceed to step 3 for diagnosis, but not for approval.

**Handoff to selfie QA:** The same MP4 and revision, speech results with timestamps where applicable, the exact-copy verdict if required, and any uncertain or mismatched passages to review in playback.

## 3. Confirm physical credibility and decide whether to release

Load flow-selfie-physical-qa with skill_read. Review the same candidate in motion against the brief: confirm that the camera viewpoint is consistent with self-filming, the required gestures are physically plausible, and the visible performance agrees with the audible dialogue. Use the speech findings to locate suspect moments, not as a substitute for watching them. Confirm that the selected file is the one that was reviewed.

**Decision:** Release only the exact candidate that passed the media, required speech, and physical checks. For an edit or mix problem, return to step 1. For a source-performance problem, keep the best inspected take as a fallback and generate a replacement only if authorized. Send any completed replacement or revised export through steps 1–3; approval does not carry over to a different file. If a required check remains unresolved, report the blocker and do not label the candidate final.
