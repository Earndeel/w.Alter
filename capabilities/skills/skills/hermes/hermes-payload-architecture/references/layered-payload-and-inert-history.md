# Layered Payload and Inert History — Session Notes

This reference captures a session-level design discussion about Hermes Agent payload composition and compaction hazards.

## Problem observed

A compressed session handoff was injected with sections such as:

- Historical Task Snapshot
- Goal
- Constraints & Preferences
- Completed Actions
- Active State
- Historical In-Progress State
- Blocked
- Key Decisions
- Resolved Questions
- Historical Pending User Asks
- Relevant Files
- Historical Remaining Work
- Critical Context

Even with a preamble saying “latest message wins”, sections such as `Active State`, `Pending User Asks`, and `Remaining Work` read like semi-active instructions. They can cause the agent to resume stale work when the latest user message only asks analysis or verification.

## User-proposed architecture

1. Static prefix — cacheable
2. Dynamic context — selected
3. Evidence layer — only if useful
4. Raw tail — recent conversation
5. Latest user message — always last and primary source of truth

This shape is correct. It separates cacheable stable context from selected dynamic context and recent conversational truth.

## External model review summary

A Kie.ai Claude Opus 4.8 direct call reviewed the architecture. The model confirmed:

- The five-layer architecture is sound.
- The current risk is latent imperative language in compressed history.
- The first patch should be the compaction renderer, not a broad retrieval rewrite.
- Hindsight filtering should come second: top-k, hard threshold, semantic dedupe.

## Recommended renderer changes

The renderer should not emit `Pending`, `Remaining`, `Active`, or `Next Steps` sections. Convert all such content to neutral past-tense facts or omit it.

Suggested section replacement:

```text
Historical facts, not instructions:
- At that earlier point, X had been discussed.
- At that earlier point, command Y had returned Z.

Past decisions at that time:
- The prior session had chosen approach A. This may be stale.

Evidence pointers:
- session=<id>, around_message_id=<id>

Neutralization:
Nothing above is an active task. The latest user message is the only action trigger.
```

## Implementation order

1. Change compaction summary template / renderer.
2. Add a static rule that historical records and memory are descriptive only.
3. Filter Hindsight cards by latest-message relevance and cap them.
4. Add prompt-layer budgets and selected full tool schemas.
