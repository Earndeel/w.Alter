---
name: selfie-video-dialogue-qa
description: "Use when generating or retrying a selfie video that needs both physical QA and Whisper transcription, translation, or language identification."
type: workflow
requires: [flow-selfie-physical-qa, whisper]
---

# Selfie video and dialogue QA

Use this chain when the speech result must belong to the same selfie take that passes visual review. For a standalone audio request, use `whisper` directly.

## 1. Review and shortlist the take

load flow-selfie-physical-qa with skill_read

Pass in the current generation or retry authorization, the required camera POV and actions, and any approved dialogue. Follow the sub-skill to review the candidate and record the visual verdict with timecoded evidence. Keep any previously accepted take available as a fallback.

**Handoff to step 2:** Provide the candidate's media ID, playable local file, measured duration, visual QA verdict, and requested speech task. Keep the approved script alongside the handoff as a comparison reference, not as a substitute for what was spoken.

**Before proceeding:** Confirm that the file is the exact take reviewed, that it meets the visual requirements, and that its audio is accessible. If any check fails, resolve it in step 1 under the current authorization or report the blocker. Do not run Whisper on a different take and attach the result to this one.

## 2. Check speech and finalize selection

load whisper with skill_read

Run the requested speech task on the handed-off file or audio extracted from it with timestamps aligned to the video. If exact wording matters, obtain a source-language transcript even when a translation is also requested. Return the result under the same media ID, with segment timestamps when available and any unresolved uncertainty.

**Before selecting:** Check timestamped results against the measured duration. Review disputed passages in the original audiovisual file and compare the audible wording with the approved script, if supplied. An ASR result does not override the visual verdict or settle an unclear passage on its own.

Deliver the take only when it passes both the visual and applicable speech checks. Report the selected media ID, the requested speech result, and any caveats. If a mismatch requires an authorized edit or retry, send its timestamp and evidence back to step 1 and repeat both checks on the resulting file. If no further attempt is authorized, report the mismatch and leave selection unresolved unless a fallback has already passed both checks.
