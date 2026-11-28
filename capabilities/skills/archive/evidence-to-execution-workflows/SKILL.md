---
name: evidence-to-execution-workflows
description: "Use for evidence-backed planning and approval gates."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [productivity, planning, triage, approvals, evidence, google-workspace]
---

# Evidence-to-Execution Workflows

Use this class-level skill when records, messages, meetings, or account data must become a trustworthy brief, bounded plan, and approved follow-up. Connector skills retrieve data; this skill owns evidence handling, cross-source reconciliation, account routing, and side-effect gates.

## Operating sequence

**Resolve sources → retrieve completely → normalize evidence → separate facts from proposals → reconcile contradictions → request approval → execute narrowly → read back.**

Default to read-only analysis and drafts. Do not send messages, create or delete records, publish, spend, or alter state while a material assumption is unresolved.

## Retrieval and evidence

- Define source accounts, private/group scope, time window, timezone, pagination boundary, and permitted side effects before retrieval.
- Resolve exact identities and addresses; never silently normalize near-matches or switch to a similar contact.
- Fetch enough pages to cover the active request, dependencies, deadline, and both sides of a conversation. Label one-sided or truncated results incomplete.
- Include relevant audio, images, video, PDFs, and links; mark identified-but-unavailable attachments as unverified rather than describing them.
- Preserve source ID, timestamp, speaker/account, extraction method, and confidence for every material fact.
- Separate observed facts, explicit commitments, inferred claims, proposals, and unknowns. Keep evidence attached to the claim instead of relying on a summary alone.

## Account and OAuth routing

- Treat each Google identity as its own token home, pending OAuth state, scope set, and route; do not overwrite one account while authorizing another.
- Check client type and exact registered redirect URI before creating an OAuth URL, and reuse the same isolated state for callback exchange.
- Request only required scopes; verify the resulting profile, granted scopes, and a bounded harmless read before considering auth usable.
- Search each account independently and label every finding with the confirmed profile address. A cross-account 404 is a routing signal, not proof of absence.
- Keep tokens, client secrets, callback URLs, OTPs, signed links, and tracking parameters out of logs, prompts, durable notes, and reports.

## Inbox, meeting, and commitment triage

Classify records as urgent reply, reply, action without reply, waiting, reference, noise, decision, proposal, commitment, question, blocker, risk, or context. For every proposed action record the concrete outcome, explicit owner or `unresolved`, explicit due date or `unresolved`, dependency, acceptance condition, and source evidence.

Search for existing tasks, tickets, projects, and follow-ups before proposing creation. Preserve owner/date/status conflicts for approval; do not infer completion from silence. If a send or write times out, inspect the provider state before retrying.

## Contact or project brief

Capture deliverables, formats, duration, resolution, aspect ratio, platforms, audience, promise, CTA, language, brand constraints, source assets, commercial scope, deadline, variants, and approval owner. Convert voice notes and linked sources into evidence-backed facts, but keep inaccessible media explicitly unavailable.

For every contradiction, preserve both evidence paths and propose a decision plus compliant fallback. Use approval gates for:

1. brief and scope lock;
2. facts, claims, and compliance;
3. scripts, storyboard, CTA, and creative package;
4. brand kit and source assets;
5. low-cost preview;
6. production or execution;
7. final QA and delivery.

At each gate state the objective, reviewable output, assumptions, blockers, and exact validation required. Do not advance a pending or revise gate.

## Weekly and recurring review

Set the review period, planning horizon, timezone, authoritative stores, calendars, inboxes, and write boundary. Cover completed and upcoming commitments, capacity, deadlines, travel, preparation, waiting items, stalled or ownerless projects, and promises owed. Propose a small capacity-aware set of outcomes and state what is deferred before applying updates.

## Delivery contract

An operation is complete only when the exact external record or recipient-visible artifact has been read back. Report covered sources and boundaries, evidence-backed findings, unresolved gaps, proposed versus completed actions, observed write state, and anything still awaiting approval. Never turn a draft, token, process exit code, or API acceptance into proof of completion.
