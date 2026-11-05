---
name: minimax-h3-selfie-ugc-workflow
description: Use when generating or retrying native-voice MiniMax H3 selfie UGC that needs physical POV validation and consistent speakers across scenes.
type: workflow
requires: [minimax-h3-native-ugc, flow-selfie-physical-qa]
---

# MiniMax H3 selfie UGC workflow

Apply this chain when MiniMax H3 generation and selfie acceptance are both required. The sub-skills own their detailed procedures; this workflow coordinates their inputs, gates and handoffs.

## 1. Prepare and generate

Load minimax-h3-native-ugc with skill_read.

Supply the requested scenes, exact dialogue, speaker references, output requirements and current authorization. Follow its preparation and generation procedure, starting with the anchor scene when establishing a shared speaker.

Hand off an attempt record containing the approved prompt and dialogue, settings, task receipt, stable media identity, downloaded original and reference provenance. Before review, confirm that the original is complete and corresponds to the recorded attempt. Resolve missing or incomplete downloads before assessing the take.

## 2. Validate the actual take

Load flow-selfie-physical-qa with skill_read.

Supply the attempt record, original audiovisual media, required gestures and exact dialogue. Apply its physical POV, action, speech and output-identification checks.

Return a timestamped acceptance or rejection record tied to the exact media identity, including unresolved defects and any accepted fallback. A generation receipt or completed thumbnail cannot satisfy this gate. An anchor advances only after both physical acceptance here and native voice/identity acceptance under the generation skill.

## 3. Continue scenes or route a correction

Load minimax-h3-native-ugc with skill_read.

For an accepted anchor, hand back the accepted source and QA record so its reference procedure can establish later scenes. For a rejected take, hand back the specific defect, relevant timestamps, preserved fallback and latest authorization. Classify the next action as transport recovery, reversible editing or an authorized new generation; do not treat QA failure as retry permission.

Before submitting another generation, confirm that the revised creative and submission are covered by current approval. If required approval is missing, stop at the documented correction proposal. Hand each resulting scene or corrected take to the next step with its own attempt record.

## 4. Recheck and select

Load flow-selfie-physical-qa with skill_read.

Review every new or edited candidate against the prior defect and the full acceptance criteria. Compare it with any accepted fallback and record the exact selected media identity and reason. Repeat steps 3–4 only within explicit authorization; preserve unresolved failures when no acceptable candidate is available.

## 5. Finish and deliver

Load minimax-h3-native-ugc with skill_read.

Hand over only accepted sources, their selection records and speaker-reference lineage. Follow its postproduction and final audiovisual verification procedure. Confirm that the export uses the selected sources and retains the accepted dialogue, voice continuity and physical credibility. If finishing introduces a defect, route the affected media through the correction and QA gates again.

Deliver the verified export with concise evidence of source selection and any remaining limitations. Keep generation success, source acceptance and final delivery as separate recorded states.
