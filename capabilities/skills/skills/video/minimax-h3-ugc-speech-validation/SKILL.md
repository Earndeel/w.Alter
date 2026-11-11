---
name: minimax-h3-ugc-speech-validation
description: Use when generating native-voice MiniMax H3 UGC via Kie.ai and validating its spoken dialogue with Whisper, including speaker continuity across scenes.
type: workflow
requires: [minimax-h3-native-ugc, whisper]
---

# MiniMax H3 UGC speech validation

## When this chain applies
Use for native-voice H3 video delivery that needs transcription-based dialogue checks after generation. Follow generation → transcription → reconciliation → final acceptance. The sub-skills own their implementation details and approval requirements; this workflow coordinates their inputs, outputs and acceptance gates.

## 1. Generate and inspect source takes
Load minimax-h3-native-ugc with skill_read.

Provide the approved scene scripts, requested language, speaker requirements and output settings. Follow its generation and speaker-reference procedure, including its required supporting skills and approval gates.

Hand off downloaded source clips, scene-to-file mapping, approved dialogue per scene, measured media durations, task receipts and audiovisual review notes. Preserve which accepted anchor take supplied speaker references.

Gate: require complete, decodable originals and an initial audiovisual review before transcription. Resolve transport failures before judging generation quality. Keep unresolved speech concerns attached to the relevant clip and interval.

## 2. Transcribe the generated speech
Load whisper with skill_read.

Use the actual source clips or audio extracted from them. Transcribe in the spoken language with timestamps; retain translation separately if requested. Keep the approved script for subsequent comparison rather than supplying it as the expected transcription.

Hand off raw ASR results, language, timestamped dialogue and source-file identifiers. Map any cropped audio timestamps back to the original clip timeline.

Gate: compare transcript bounds with measured media duration and flag out-of-bounds output. Preserve in-bounds discrepancies for review. A transcript alone cannot establish natural delivery, speaker continuity or audiovisual quality.

## 3. Reconcile speech discrepancies
Load minimax-h3-native-ugc with skill_read to evaluate the transcript against the approved dialogue and actual audiovisual evidence. Load whisper with skill_read whenever focused retranscription is needed.

Build a per-scene discrepancy record containing expected words, observed words, source intervals and review findings. Route disputed repetitions or omissions through the focused verification procedure in the sub-skills; do not accept whole-take ASR agreement as the deciding evidence.

Hand off accepted speech intervals and verified dialogue for editing, plus any unresolved defects. Apply corrections under the generation skill's approval rules. Stop affected scenes from advancing while material discrepancies remain unresolved; paid regeneration requires the applicable approval.

## 4. Validate the edited delivery
Load minimax-h3-native-ugc with skill_read for postproduction and final audiovisual acceptance. Load whisper with skill_read to check the actual final export when edits or mixing could change speech completeness, timing or intelligibility.

Pass verified dialogue and accepted source intervals into postproduction. Reconcile final-export transcription with the edit timeline and captions, then review the actual export audiovisually.

Deliver the final video with its verified transcript, scene/source mapping and concise validation findings. Distinguish completed generation, accepted source takes and accepted final delivery; report unresolved issues explicitly instead of declaring acceptance.
