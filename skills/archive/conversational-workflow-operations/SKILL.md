---
name: conversational-workflow-operations
description: Use for guided conversational intake and workflow gates.
tags: [conversation, intake, workflow, multimodal, approval, d1]
metadata:
  hermes:
    tags: [conversation, intake, workflow, multimodal, approval, d1]
---

# Conversational Workflow Operations

Use this class-level skill when a chat agent collects requirements, handles text/image/voice turns, prepares a durable brief, and gates costly or asynchronous execution.

## Separate dialogue from execution

Let deterministic state own structured fields while the agent owns natural dialogue. Classify free text as an explicit field mutation, a question/objection, or unrelated conversation before updating the brief. Answer objections first and preserve the guided keyboard; do not turn every message into notes or repeat a summary.

Persist one mergeable brief snapshot containing confirmed facts, inferences, evidence, missing decisions, and deterministic readiness. Recompute completeness in code and invalidate a plan when a validated input changes. Treat model claims of readiness as requests, not authority.

## Multimodal handoff

Keep text unchanged, pass images as first-class content parts to the semantic model, and use a dedicated transcription adapter for voice before returning the transcript to the same conversation brain. Preserve fresh media context across guided text turns. Separate collection, planning, and execution tools so recording a brief cannot spend credits.

## Approval and runner gates

Use separate transitions for brief validation and launch/spend approval. Before starting a run, reload the authoritative project/brief, reject stale or unrelated active runs, prefer the persisted workflow ID, and require explicit approval. Production tools are allowed only when mode, run status, current step, and requested tool all match. Handle no-tool steps with deterministic transitions rather than leaving them pending.

## Fault containment

Parse model tool arguments once, require an object, correlate malformed calls to their tool ID, catch each execution error, keep logs subordinate to the user-visible failure, and do not advance state on failed tools. Never retry a mutation or paid generation without durable idempotency and reconciliation.

## Visible response contract

Default to one or two short direct sentences, answer the user's point first, ask at most one high-value question, and keep internal JSON/reasoning and choice markers out of visible text. Test the actual outbound payload and real state transitions, not source-string presence or an assistant claim that something was recorded.

## Verification

Run focused channel/agent/workflow regressions, multimodal payload tests, planner-call-count tests, database migration checks, Worker dry-run, and the full suite with unrelated failures separated. Verify approval transitions and persisted state before claiming execution.

Exact historical intake, multimodal, Telegram, planner, and tool-failure recipes are routed in `references/curator-conversation-archive-routes.md`.
