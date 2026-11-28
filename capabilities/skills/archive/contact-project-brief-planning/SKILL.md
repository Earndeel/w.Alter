---
name: contact-project-brief-planning
description: "Turn a contact's recent messages, voice notes, attachments, and linked sources into an evidence-backed project brief and a staged execution plan with explicit approval gates."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [messages, project-brief, execution-plan, approvals, multimodal, compliance]
---

# Contact → Project Brief → Staged Execution

Use this skill when Monsieur asks to inspect a conversation with a contact, understand the work the contact wants, and prepare a plan that Monsieur will validate step by step before execution. It is a bridge between messaging intelligence and project execution; it is not a relationship dossier and not an implementation plan for a codebase.

## Operating rule

**Read first, synthesize second, propose third, execute last.**

Do not generate assets, send messages, publish, submit forms, incur spend, or make irreversible changes while the brief still contains unresolved assumptions. Each phase ends with a compact approval gate.

## Phase 1 — Resolve and time-box the source

1. Resolve the named contact against the complete private-chat list. Paginate the chat endpoint when the first page is insufficient; never switch to a similar-looking contact.
2. Exclude group chats unless Monsieur explicitly includes them.
3. Record the chat, network, and current Bangkok time. Convert source timestamps from UTC to `DD/MM HH:mm` in UTC+7 before using words such as "hier", "ce matin", or "récent".
4. Fetch the newest message page first. Beeper returns messages newest-first. Sort chronologically only for presentation, and follow `sortKey` pagination far enough to reconstruct the active request, dependencies, and deadline.
5. Detect whether outgoing messages are present. If the source returns only one side, label the synthesis incomplete rather than inventing the missing side.

## Phase 2 — Include multimodal evidence

- Detect voice-note attachments in the retrieved window and transcribe them automatically when they can affect the brief. Do not silently omit an audio request.
- Beeper media files on the Mac may have no extension. When sending them to a transcription service, provide an explicit upload filename and MIME type, such as `voice.ogg` and `audio/ogg`.
- Inspect relevant images, videos, PDFs, and URLs. Keep the source message ID and timestamp attached to each extracted fact.
- If an attachment is identified but unavailable, say `identified, not retrieved` and do not describe its contents as verified.
- For a linked page, use the ordinary extraction method once. If its backend fails, switch to a browser or atomic extraction fallback; do not waste turns repeating the same failed route.

## Phase 3 — Extract a compact evidence-backed brief

Separate facts from proposals and unknowns:

### Deliverables

Count, type, aspect ratio, resolution, duration, variants, audio/subtitles, file format, and delivery location.

### Content and creative brief

Audience, product/service, problem, promise, offer, scripts, tone, language, CTA, required source assets, and urgency.

### Brand constraints

Logo and mark, palette, type, layout, badges/labels, safe areas, imagery, and reference-site elements.

### Platform constraints

Target platforms, ad-review risks, text density, aspect ratio, safe zones, prohibited or risky claims, and whether separate platform variants are needed.

### Commercial constraints

Quoted price, budget, deadline, test status, promised turnaround, and whether each item is a request, an estimate, or an already-approved commitment.

### Unknowns

Every unstated parameter that would change the work: duration, quality level, source-file availability, legal wording, platform, approval owner, or delivery format. Keep these visible; do not fill them with convenient defaults without labeling them as proposals.

## Phase 4 — Reconcile contradictions before production

Cross-check the contact's request against accessible landing pages, source documents, previous messages, and platform context. Flag contradictions instead of resolving them silently. Common examples:

- an absolute funding or performance claim versus variable eligibility, amount, or disclaimer language;
- a requested badge, flag, watermark, or logo versus a previous statement that it failed ad review;
- a deadline that conflicts with the current date or the availability of source assets;
- a requested resolution or quality level that conflicts with the quoted budget;
- a script claim that is not supported by the product source.

For each contradiction, propose a decision and a compliant fallback variant. Do not present the fallback as the user's intent until Monsieur approves it.

## Phase 5 — Produce the approval-gated plan

Use a numbered plan. For each step state: objective, concrete output, assumptions, blocking unknowns, and the exact approval needed.

Recommended gates:

1. **Brief lock:** deliverables, formats, duration, platforms, deadline, budget, and variants.
2. **Facts and compliance:** approved product facts, claims, footnotes, disclaimers, and risky wording.
3. **Creative package:** scripts, CTA, storyboard/shot list, text overlays, and visual references.
4. **Brand kit:** logo, palette, typography, composition, and reusable visual rules.
5. **Low-cost preview:** stills or keyframes to validate the visual direction before full generation.
6. **Production:** generate, edit, voice, subtitle, and render the approved variants.
7. **Final QA and delivery:** check factual text, spelling, brand fidelity, platform render, filenames, and package contents.

At each gate, stop and request Monsieur's validation. If he changes the brief, update the downstream steps rather than continuing with stale assumptions.

## Output style

Lead with the conclusion: what the contact wants, what is certain, what is unresolved, and the proposed next gate. Use concise French by default. Do not dump a raw transcript unless requested. Quote only the messages needed to prove a scope, contradiction, deadline, or claim.

## Verification checklist

Before asking for approval, confirm:

- contact identity and private-chat scope are correct;
- all relevant timestamps are in Bangkok time;
- relevant voice notes and linked sources were included or marked unavailable;
- every factual claim has a source or is labeled as unverified;
- assumptions are visibly marked as proposals;
- contradictions have an explicit decision gate;
- no side effect has occurred before approval.

See `references/gating-checklist.md` for a reusable brief template and approval-gate format.
