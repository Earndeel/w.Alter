---
name: beeper-contact-dossier
description: Use when Beeper conversations or media must supply evidence to build, refresh, or audit a Kardex contact dossier.
type: workflow
requires: [beeper-messages, contact-intelligence-systems]
---

# Beeper Contact Dossier

Orchestrate Beeper evidence collection followed by contact intelligence analysis. Use for requests that need both stages; ordinary message reading, sending, or verification-code retrieval belongs to beeper-messages alone.

## 1. Collect the scoped evidence

Load beeper-messages with skill_read.

Apply its contact-resolution, retrieval, chronology, and media procedures. Establish the requested contacts, time range, and dossier objective before collecting deeply. Resolve every requested contact; keep ambiguous matches separate and obtain clarification before analyzing an uncertain identity.

Hand the next step an evidence packet containing:
- Requested objective and resolved contact-to-chat mappings, with supporting identity evidence and unresolved candidates.
- Source message IDs, chat IDs, participants, direction, original timestamps, and normalized chronological text.
- Media references and linked transcripts or descriptions, distinguishing retrieved material from unavailable attachments.
- Retrieval time, covered interval, pagination completion or stopping reason, and known omissions.

### Handoff check

Verify that each record remains traceable to its source, chronology is consistent, and coverage supports the requested analysis. Do not present a bounded retrieval as full history. If identity is unresolved, pause that contact's analysis. If retrieval fails or coverage is partial, pass the limitation explicitly rather than treating missing evidence as an empty conversation.

## 2. Build, refresh, or audit the dossier

Load contact-intelligence-systems with skill_read.

Pass the validated evidence packet and requested objective. Apply its identity-resolution, episode-analysis, provenance, and dossier procedures; load only the supporting references needed for the task. Check the current architecture before persistence: historical implementation examples do not authorize retired services or direct Kardex writes. Persist only through the supported Walter Memory ingestion interface and processors when persistence is within the user's request.

Produce the requested dossier or audit, linked to the evidence packet. Preserve distinctions between established claims, interpretations, contradictions, and unresolved questions. For refreshes, distinguish new evidence from existing dossier material and avoid treating repeated ingestion as independent corroboration.

### Completion check

Verify that material claims have evidence references, uncertain identities remain unmerged, and current-state statements reflect the covered dates. Report coverage limitations and distinguish analysis produced from updates actually persisted. If more source evidence is needed, return to step 1 with a specific contact, interval, or media gap, then repeat the handoff check before revising the dossier.

Return the requested contact context with source references, relevant uncertainty, and any unresolved gaps. This workflow does not itself authorize outbound messages or expand an analysis request into a system rebuild.
