---
name: multimodal-conversational-intake
description: Design, implement, test, and deploy conversational intake systems that collect planning-ready briefs from text, images, and voice while separating collection, planning, and execution responsibilities.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [multimodal, conversational-intake, planning, voice, vision, workflow-orchestration]
---

# Multimodal Conversational Intake

Use this skill when a chat agent must gather enough grounded information to plan a project from natural text, images, and voice. The core problem is not merely multimodal parsing: it is preserving one authoritative intake brain, asking only for genuinely missing information, and delaying planning/execution until the brief is complete.

## Core architecture

Separate responsibilities explicitly:

1. **Transport adapters** acquire inputs without interpreting them beyond necessity.
   - Text passes through unchanged.
   - Images remain first-class multimodal content parts.
   - Audio is passed natively only when the selected model/provider truly supports it; otherwise use faithful STT and preserve source metadata.
2. **Conversation/intake brain** owns understanding, extraction, deduplication, and clarification.
3. **Planner** runs only after intake declares the brief planning-ready.
4. **Executor** remains behind deterministic approval and workflow-state guards.

Do not let a cheap preprocessing model become the hidden reasoning brain. STT may transcribe, but the intake model must decide what the speech means. An image helper may normalize bytes or URLs, but the intake model must see the actual image whenever its provider supports vision.

## Required brief contract

Define the planning fields before prompting or coding. Typical fields include:

- objective and success criteria;
- deliverable/media type;
- product/project description;
- target audience;
- channel/distribution context;
- style, tone, visual references;
- format/aspect ratio;
- duration and quantity;
- CTA;
- constraints, exclusions, compliance needs;
- budget/timeline when relevant;
- explicit validation and execution-approval state.

Classify each field as `known`, `strongly inferred`, `missing`, or `not applicable`. Never invent a value merely to complete a schema. Ask a narrow question for the highest-impact missing field, preferably grouping only tightly related gaps.

## Implementation sequence

1. Verify the exact model ID and provider capability metadata before coding.
2. Trace every inbound route: normal text, photo with caption, photo then follow-up, voice, guided intake, callbacks, resumed session, and stale-media context.
3. Identify deterministic branches that bypass the main agent. These are the usual hiding place for inconsistent model routing.
4. Build one canonical message-construction function:
   - text content for ordinary turns;
   - `text + image_url` parts for images;
   - transcript plus a private source marker for audio transported through STT.
5. Make intake readiness explicit through a structured tool call or state transition such as `status=awaiting_validation`.
6. Invoke the planner lazily at that transition, using the intake model's grounded structured brief.
7. Persist the planner output, then let the conversation model present/clarify it naturally.
8. Keep execution approval separate from plan validation.

## Multimodal rules

### Images

Pass the real image URL/data to the intake model. Do not replace it with prose from another vision model unless the target model lacks vision and the product explicitly accepts that quality trade-off.

For delayed follow-ups, store pending media with a freshness bound. Reuse it in both natural and guided-intake branches. Stale media must not hijack unrelated future chat.

### Voice

Check provider metadata at implementation time. If raw audio is unsupported:

1. transcribe faithfully with low-temperature STT;
2. do not summarize in the STT layer;
3. mark the transcript internally as audio-derived;
4. send it to the intake brain for extraction and clarification;
5. describe the architecture honestly as “STT transport → intake-model analysis,” not “native audio analysis.”

## Planner handoff

The planner should not run before every conversational turn. Trigger it only when intake emits a planning-ready state. Hand it a serialized, grounded brief rather than asking it to reconstruct the conversation independently.

A robust handoff includes:

- known/inferred fields;
- unresolved caveats;
- source/evidence notes when media mattered;
- requested deliverable;
- constraints and exclusions;
- the client's current validation state.

If planning fails, preserve the collected brief and continue safely; do not discard intake state or launch execution.

### Deterministic handoff gate

Treat the intake model's `planning_ready` output as a request, not authority. Persist intake through a dedicated state-update tool, then immediately before planner invocation reload the active snapshot from the authoritative store and recompute readiness in code. This second read is mandatory because an intake update and planner request may occur in the same multi-tool turn while the context assembled before the turn is already stale.

If the snapshot is incomplete, synthesize a `brief_not_ready` tool observation, make zero planner calls, and leave project status unchanged. Promote to `awaiting_validation` only after the planner returns a structurally valid plan; on planner failure return a recoverable observation, preserve the brief, and do not manufacture a validation state. Execution approval remains a third, separate gate.

### Free-form continuity and invisible reasoning

Persist one mergeable snapshot with separate known facts, strong inferences, evidence, missing decisions, and readiness. Confirmed facts override matching inferences; evidence appends and deduplicates. Attach this active snapshot to plausible short follow-ups such as `plutôt 15 secondes`, while suppressing stale context for clear small talk or explicit new-project intent.

Keep provider reasoning internal. Never require a visible chain-of-thought block or internal JSON in assistant content. Default to 1–2 short sentences, answer first, ask at most one high-impact question, and make buttons optional rather than mandatory.

## Pitfalls

- **Eager planning:** increases latency/cost and lets the planner steer incomplete intake.
- **Hidden guided-flow bypass:** a questionnaire branch silently routes to a different model or drops image/audio context.
- **Vision-by-summary:** the intake brain sees only another model's interpretation, not the evidence.
- **Audio overclaim:** documentation says raw-audio understanding while runtime actually uses STT.
- **Validation conflation:** “brief complete” is treated as “approved for production.”
- **Mock sequence drift:** removing an eager planner call changes test call order/count; update behavioral fixtures rather than restoring wasteful runtime behavior.
- **Broad-suite misattribution:** dirty-worktree or unrelated UI failures are blamed on model routing without reproduction.

## Verification matrix

Test behavior, not source strings:

- exact conversation model and reasoning level;
- direct image content part reaches the conversation request;
- STT happens before the conversation request and the transcript retains audio-source metadata;
- normal and guided routes use the same intake brain;
- pending images survive into guided follow-ups;
- incomplete turns do not invoke the planner;
- the planning-ready transition invokes the planner once;
- persisted plan comes from the planner handoff;
- execution tools remain blocked without explicit approval;
- async tool responses do not cause redundant final-model calls;
- deployment dry-run, real deploy version, and live health probe succeed.

## References

- `references/scena-luna-sol-july-2026.md` — concrete Cloudflare Workers/Telegram migration: Luna high intake, Sol xhigh lazy planning, image and voice routing, regression implications, and deployment verification.
- `references/stateful-intake-handoff-harness.md` — durable brief schema, merge rules, authoritative handoff gate, natural-response contract, and hostile-path regression matrix.
