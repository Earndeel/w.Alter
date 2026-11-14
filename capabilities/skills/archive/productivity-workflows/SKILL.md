---
name: productivity-workflows
description: "Use for productivity reviews, triage, and follow-up."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [productivity, triage, planning, meetings, follow-up]
---

# Productivity Workflows

Use this class-level skill for recurring personal and team workflows that turn messages, meetings, calendars, tasks, notes, and commitments into a bounded set of decisions and approved follow-up. Connector skills provide access to each system; this skill owns the cross-system reasoning, evidence, and approval boundary.

## When to Use

- Triage an inbox or decide what needs attention.
- Turn meeting notes or transcripts into decisions, owners, and follow-up.
- Run a weekly review across commitments, projects, calendar, notes, and waiting items.
- Reconcile proposed tasks or messages with existing records before writing.

Do not use this for a provider-specific API operation or for an implementation plan that does not depend on personal/workflow records.

## Always-on rules

- Define the accounts, sources, time window, timezone, pagination boundary, and allowed side effects before retrieval.
- Read complete relevant threads or records, preserve source identifiers and timestamps, and label missing or truncated evidence.
- Separate observed facts, explicit commitments, proposals, and unresolved assumptions; never invent an owner, date, status, or commitment.
- Default to read-only analysis and drafts. Sending, deleting, archiving, creating records, or changing status requires explicit approval mapped to an exact target.
- Search for an existing record before creating a task, ticket, follow-up, or duplicate project item.
- After every approved write, read back the exact provider record or recipient-visible artifact; a successful request is not proof of persistence or delivery.

## Inbox triage

1. Resolve the mailbox/account and scope; default to read plus draft, not send or delete.
2. Retrieve complete threads with bounded pagination and record coverage gaps.
3. Classify each thread as urgent reply, reply, action without reply, waiting, reference, or noise, with a reason tied to the thread.
4. Draft replies that answer material questions, preserve the user's tone, and avoid invented commitments.
5. Present an approval batch containing account, recipient/thread, action, draft summary, deadline, and risk.
6. Apply only approved mutations and inspect the provider state before reporting completion. If a send times out, check Sent before retrying.

## Meeting follow-through

- Distinguish decisions, proposals, commitments, questions, blockers, risks, and context before extracting actions.
- For every action record the concrete outcome, explicit owner or `unresolved`, explicit due date or `unresolved`, dependency, acceptance condition, and source quote/timestamp/page.
- Reconcile existing tasks before proposing creates or updates; preserve owner/date/status conflicts for confirmation.
- Prepare minutes, proposed tickets, and follow-up messages as drafts until each external effect is approved.
- Re-read every approved destination and attach meeting provenance so recurring meetings do not create duplicates.

## Weekly review

1. Set the review period, planning horizon, timezone, authoritative task store, calendars, inboxes, and write boundary.
2. Cover the completed week and the next one to two weeks: commitments, meetings, deadlines, travel, preparation, and capacity.
3. Clear declared capture points into next action, project, waiting, scheduled, someday, reference, archive, or delete proposal without mutating them first.
4. For each active project identify outcome, next action, owner, deadline, blocker, last meaningful activity, and source; flag stalled, duplicate, contradictory, or ownerless work.
5. Review promises made and items owed by others; propose follow-ups with an owner, date, and channel instead of treating silence as completion.
6. Choose a small capacity-aware set of outcomes and state what is deferred. Apply only approved updates and verify each changed record.

## Connector boundary

Load the relevant connector for Gmail/Calendar/Drive/Sheets, Notion, Obsidian, Airtable, or another source. Keep provider-specific authentication, pagination, field shapes, and mutation commands in that connector; keep cross-system decisions and approval gates here.

## Verification

A finished workflow reports covered sources and time boundaries, evidence-backed classifications, unresolved gaps, proposed versus completed actions, exact read-back results for approved writes, and anything still awaiting approval. Never call a review complete because a summary or draft was produced without coverage and state verification.
