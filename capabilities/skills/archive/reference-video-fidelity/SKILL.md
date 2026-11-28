---
name: reference-video-fidelity
description: "Use when adapting videos. Verify reference fidelity."
---

# Reference-led video fidelity

## Acceptance contract
- Treat “same style” as a shot-level contract, not a generic genre label. Record shot order, subject roles, wardrobe, locations, visible actions, framing, transitions, timing, overlay placement and typography; assess voice and music separately when evidence permits.
- Trace the original attachment to its message ID and sender before analysis; generated identity clips and cropped motion references are derivatives, not the original creative authority. Read the client's exact brief separately from the reference's commercial claims.
- Verify native-video analysis against timestamped frames at detected scene changes and independent ASR. Model summaries can omit object-to-presenter reveals, round away cuts, or deny a quiet music bed; retain disagreements and do not turn uncertain speaker identity or motion continuity into facts.
- Preserve the approved benefit when adding eligibility conditions: qualification should explain access to a desirable offer, not replace the benefit with repeated dossier/candidature language. Never restore unapproved financial promises merely to match the reference.
- For selfie-only adaptations of mixed-camera references, map each useful action to a speaker-held-phone equivalent rather than copying third-party coverage or flattening every role into an identical static presenter. Derive editorial beats from narrative functions, not generation-slot durations.
- Distinguish the ad itself from screen-recording chrome, unrelated forms and personal data. Removing these does not authorize redesigning the ad.
- Preserve meaningful roles and actions. Do not collapse a rooftop installer and technical spokesperson into a single static presenter merely for identity consistency.
- Adapt commercial claims only to the approved offer, keeping the reference's visual structure separate from factual claim validation.

## Natural UGC and karaoke requirements
- For Monsieur's UGC ad work, use believable smartphone footage, conversational delivery, small handheld movement, practical locations and purposeful actions with varied shot sizes; avoid static corporate spokespeople and decorative stock-style inserts.
- Generate clean footage only: no generated captions, titles, logos, labels or graphic bands. Keep instructions about later karaoke rendering out of generation prompts; specify only the absence of added text there.
- Add captions in postproduction as short readable groups with the currently spoken word highlighted, timed from the actual final audio. Do not mistake phrase-level subtitle replacement for word-synchronous karaoke.
- Verify word alignment, punctuation, safe areas, contrast and absence of residual generated lettering in the final video. Never cover lettering defects with a large invented footer.
- Reject concurrent headline/karaoke blocks that repeat the same utterance even when their bounding boxes do not intersect: geometric non-overlap does not establish a readable text hierarchy. Prefer one caption track with emphasis inside the active group, and distinguish duplicated blocks from literal glyph collisions in the diagnostic.
- Measure the interval after the last useful spoken word and detect reused source intervals before accepting pace. Do not pad a requested duration with repeated smiles, frozen people or a long music-only tail; change the editorial duration or obtain approval for a purposeful ending. Place reframing cuts at motivated gestures or sentence boundaries, not evenly spaced zoom cycles.
- Treat changes of creative direction as revisions to preproduction, not automatic authorization for another paid generation; retain explicit prompt approval.

## Native-audio renderer QA

Read `references/native-post-renderer.md` when building a local EDL/ASS renderer, testing native-audio cuts, handling raw ASR defects or checking AAC duration.

## Social-ad hook relevance
- When resuming a social ad, revalidate the opening against the client's current acquisition brief before continuing an old shot list. Show the advertised product and its approved benefit immediately; an available generated scene or an incidental reference action is not a reason to lead with it. For solar-panel ads, a tarp-deployment scene does not substitute for compelling solar-roof visuals. Propose the opening's imagery, spoken hook and transition for approval before spending on a revised direction.

## Before spending
- Present the shot-by-shot adaptation beside source frames and obtain prompt approval before generation.
- If the raw reference cannot be supplied directly, use suitable crops or explicit per-shot constraints rather than a vague UGC description.
- Compare the first generated clip against the source before conditioning subsequent clips on it. Internal consistency with generated content can propagate the initial mismatch.

## QA and rejection
- For solar-roof hooks, inspect the native moving clip and full-resolution frames during the reveal: crossed, raised or overlapping modules can look like a damaged installation even when the overall roof reads as photovoltaic. Reject major geometry defects rather than hiding them with captions or relying on a small contact sheet. A new clean visual take may reuse an independently verified native voiceover from an earlier take when no speaking face is visible; record separate audio/video provenance and re-audit the final mix.
- Run a neutral native-video observation pass before supplying expected script or caption design; leading requirements can produce invented yellow captions on a clean master or an imagined visible phone. Retain the contradictory response, resolve disputed claims against timestamped full-resolution pixels and source hashes, and do not promote blanket model approval to a release gate.
- Name QA sidecars with the complete media filename (for example `final.mp4.asr.json` and `final.webm.asr.json`); replacing only the suffix silently overwrites evidence when multiple export formats share a stem. If a collision happened, preserve the last sidecar under its actual format and retain the prior process transcript plus verified audio packet identity rather than inventing two independent JSON receipts.
- Separate codec playback capability from file integrity: a Chromium build lacking H.264/AAC can reject a fully decodable MP4. Preserve that failed test, exercise the VP9/Opus WebM through the real ended event, and do not claim Hermes desktop playback from preview-open success when the desktop driver is unavailable.
- Use contact sheets for composition, visible text and morphology, not to infer camera stability, motion quality or lip-sync. Resolve motion-dependent concerns on the native video with audio before accepting or rejecting; keep the earlier concern and the additional evidence in the QA record.
- Make reference fidelity a separate final gate alongside transcript accuracy and technical quality. A decodable file with the right words is not necessarily a compliant ad.
- Assess vocal naturalness separately from intelligibility, native-audio provenance and playback integrity. A model saying “clear” or “dynamic”, or sample-identical native PCM, cannot refute a user's perception of unnatural speech or certify good pace; retain uncertainty and compare the actual mixed audio, source takes, pauses and vocal continuity before claiming acceptance.
- For rejected-master audits, distinguish intelligible dialogue from natural delivery and overlapping glyphs from redundant simultaneous claim/caption blocks. Quantify music-only tails and repeated native-source intervals separately from cut counts; retain neutral audiovisual disagreements instead of forcing them to match the complaint. These distinctions prevent technically correct evidence from becoming an invented perceptual diagnosis.
- Preserve overlay geometry and typography. Do not cover unwanted generated text with an invented persistent band that changes the visual direction; disclose the defect and obtain approval for a materially different or credit-consuming remedy.
- After rejection for lack of resemblance, stop credit-consuming work, compare source and output, acknowledge concrete deviations, and propose revised storyboard/prompts for renewed approval. Never treat dissatisfaction as authorization to regenerate.
