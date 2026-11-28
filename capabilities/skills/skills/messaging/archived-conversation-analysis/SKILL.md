---
name: archived-conversation-analysis
description: Use when Beeper is offline or chat archives are partial.
---

# Archived Conversation Analysis

Load alongside `beeper-messages` and `contact-intelligence-systems` when live chat access fails or evidence is incomplete.

## Original evidence before inference

- Verify live device availability once before switching to archives. Explain that live access is unavailable; do not turn an archive's last event into a claim about the present.
- Discover candidate social identities and validate platform accounts or previous explicit user confirmations. A first-name match or the first person-card result does not resolve a cross-channel identity. Client reinstalls may change room IDs while the platform identity stays the same.
- Use canonical original events, not remembered relationship summaries, as evidence. Inspect current schema and metadata-only thread counts, privacy classes, direction counts and date ranges before reading content.
- Treat an empty cloud-safe semantic search as inconclusive: private messages may be redacted-cloud rather than cloud-allowed. No search result is not proof that no chat exists.

## Privacy-safe read boundary

- Do not expose unrestricted event-reader output to a cloud model. Specify the privacy ceiling explicitly, exclude all local-only content, pseudonymise redacted-cloud content before output and discard secret detections. Never output the local pseudonymisation mapping.
- A local-only log cannot be recovered through a different unfiltered copy, transcript or export. Another storage path is not another permission.
- Reading conversations for analysis is not permission to create a new durable contact dossier or ingest them into persistent memory. Use the configured scratch directory for necessary intermediates.

## Coverage and attribution

- Separate authored text from system notices, incoming-call notifications, reactions, link previews, view-once placeholders and blank messages. Event totals are not automatically interpersonal-message totals.
- Preserve direction from original outgoing flags or canonical sent/received event type. Do not infer direction from display names; retain unknown attribution when necessary.
- Give the accessible date range and latest captured trace per channel in the user's timezone. Sparse or uneven outgoing capture rules out investment ratios, initiation ratios, reply-delay calculations and assertions about absent replies.
- Read whole observed episodes before interpreting individual lines. Shared-post captions are third-party text, not personal statements; do not infer the sender's intent from a caption alone.
- Never claim that an audio was transcribed, a picture viewed or a call answered from metadata. State unavailable media and calls as limits.

## Synthesis

- Verify every final quotation against original text, speaker, platform and timestamp. Preserve exact spelling and punctuation.
- Distinguish expressed affection, requests to discuss, concrete behaviour changes and demonstrated follow-through. One does not automatically prove another.
- Label explanations as hypotheses, provide counter-evidence and avoid diagnoses or certainty about hidden motives.
- Distinguish renewed contact from accountability. When the user requires spontaneous acknowledgement and an apology before a call or meeting, do not reframe that requirement as merely wanting contact or automatically recommend asking for the apology; that reverses the desired sequence and substitutes prompted wording for the initiative they want to assess.
- Do not infer manipulation from a refusal to resume contact. Explain uncertainty about unsolicited accountability without inventing motives, predicting a return, or supplying tactics to pressure the other person.
- When drafting a firm boundary, respect a request for direct, non-pleading wording instead of imposing emotional disclosure or a conciliatory tone. Express the user's own conditions for participation and their decision if unmet; do not turn firmness into contempt, intimidation or a tactic to force an apology, and do not endorse the premise that acknowledging hurt is weakness.
- Preserve clarified constraints across follow-up drafting requests. A request for a more elegant or firmer message does not, by itself, waive an earlier requirement for unsolicited accountability. Do not repeatedly offer reworded apology demands; explain the incompatibility once and present the real choice between stating the condition and leaving the initiative to the other person, without endorsing the belief that expressing a need is humiliating.
- Provide an honest, non-manipulative next step aligned with the user's actual boundary: observable commitments where relevant, not retaliation, strategic silence or hidden tests.
