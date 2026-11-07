---
name: conversational-intake-orchestration
description: Design, debug, and test guided chat intake flows that combine deterministic form state with natural agent conversation, identity-aware replies, resumable project context, and explicit execution gates.
---

# Conversational Intake Orchestration

Use this skill when a Telegram bot, chat assistant, onboarding wizard, or project brief flow mixes inline buttons/state-machine fields with free text and starts behaving like a rigid form: repeating summaries, treating objections as notes, losing project context, or launching too early.

## Core invariant

**The state machine owns structured fields; the agent owns dialogue.**

A guided flow must never assume every free-text message is a field value. A client can answer, amend, question, object, pause, or ask for professional advice without abandoning the project.

## Required routing model

For every free-text turn inside active intake, classify into one of three behavioral branches:

1. **Explicit field answer or mutation**
   - Examples: `3 vidéos`, `format 3:4`, `sans voix off`, `change le CTA`.
   - Apply the deterministic mutation and advance or re-render the relevant stage.
2. **Conversational interruption**
   - Examples: `comment vas-tu générer sans référence ?`, `pourquoi ce format ?`, `je ne comprends pas ce choix`, objections and feasibility questions.
   - Route to the real conversational agent with a structured intake snapshot.
   - Preserve intake state and the current keyboard.
3. **Approval or execution command**
   - Handle through a separate, strict approval gate.
   - A question, objection, recap modification, or planning sentence is never execution approval.

### Ordering matters

Apply unambiguous requested mutations before the conversational classifier. This lets `peut-on passer en 3:4 ?` update the format while still allowing a natural acknowledgement. Only then decide whether the remaining turn needs agent dialogue.

Do not use a broad rule such as `active_intake => save text as notes`. That is the classic recap-repetition factory.

## Conversational continuation envelope

Pass the agent a delimited, structured envelope containing:

- trusted client display name from the database/profile;
- exact user message;
- current project/intake fields;
- active stage;
- exact question or action to resume after the answer;
- explicit constraints: answer first, remain concise, do not call tools, do not mutate intake, do not imply validation or launch.

The agent response should:

1. answer the question or objection precisely;
2. acknowledge the concern like a professional collaborator;
3. use the client's first name naturally and sparingly when available;
4. bridge back to the current project stage in one sentence;
5. avoid repeating the full recap unless the client asked for it.

Keep the existing inline keyboard attached to the response so the user can continue without the dialogue branch destroying navigation.

## Identity and tone

- Source the name from trusted tenant/client data, never infer it from arbitrary message text.
- Sanitize the name before prompt injection (remove line breaks/control characters and cap length).
- Tell the model to use the first name at the first meaningful reply or pivot, not in every sentence; mechanical name repetition is merely a different species of bot.
- Keep project vocabulary, constraints, and current decisions in the envelope so the answer stays framed on the work rather than drifting into generic chat.

### Concision is a product contract

When Monsieur flags a client-facing agent as too verbose or formal, do not merely replace “professional” with “concise.” Encode measurable rules in every prompt layer that can answer the user:

- Default visible reply: **1–2 short sentences**. Expand only when the client explicitly asks for details, a list, or a recap.
- Use natural, direct, relaxed language and simple words. Follow the product’s configured address mode (for Scena: French tutoiement).
- Start with the useful information. Avoid ceremonial openings such as “Très bien”, “Parfait”, “Je vous propose”, or “Voici le récapitulatif”.
- Do not reformulate the user’s last message or recite the stored brief. Surface only the next useful fact, question, or decision.
- Machine-only metadata and contextual button blocks do not count toward the visible sentence budget.
- Apply the same contract to the global system prompt **and** route-specific continuation/guided-intake prompts. A stale “3–4 professional sentences” instruction in one branch will override the intended UX.

Regression tests should inspect the real outbound model payload for both regular and guided branches and assert stable semantic markers such as `1 à 2 phrases courtes` and `ton naturel, direct et détendu`. This tests the assembled behavior contract rather than grepping source text.

## Model routing consistency across modalities

Treat the conversational model, provider, and reasoning level as one product contract. A guided branch, a voice turn after transcription, or a helper intake route must not silently downgrade the primary conversational brain.

- Keep speech-to-text separate from dialogue: STT may use a specialist provider, but its transcript must re-enter the same conversational model route as typed text.
- Centralize model ID and reasoning effort in shared constants, then apply them after caller payload fields in the network wrapper so call sites cannot override or downgrade them.
- Expose provider, model, and reasoning effort in diagnostics/config endpoints and status messages. Sweep prompt copy and operator labels when the routing contract changes; stale observability is still a regression.
- Assert the actual outbound URL, model ID, reasoning object, and tool payload for regular chat, guided intake, and post-STT voice flows.
- Distinguish planner and executor requests by model ID, never by reasoning effort: both roles may legitimately use the same maximum effort.

See `references/openrouter-model-reasoning-contract.md` for the Scena case, live-catalog checks, and regression pattern.

## Progressive conversation memory

Keep durable project facts in structured state; do not rely on a raw transcript as the project database. For conversational continuity, combine that structured state with a rolling summary and a small verbatim tail.

When the raw message window reaches its limit:

1. split it into an older segment and the latest 2–3 complete turns;
2. merge only the older segment into the existing cumulative summary;
3. persist the recent turns unchanged and feed both summary + recent turns to the next model call;
4. preserve the current workflow/tool state during compaction;
5. if summarization fails, retain a bounded deterministic fallback containing the previous summary and the tail of the compacted segment.

Never compact by summarizing the entire conversation and then clearing the message array. That creates periodic amnesia exactly when a long intake becomes valuable. Regression tests should exercise the real persistence path and verify that older facts reach the cumulative summary while the latest turns remain verbatim in storage.

## State and execution safety

A conversational interruption must not:

- append the question verbatim to `notes` or the brief;
- advance the intake stage;
- mark the brief validated;
- call generation/credit-consuming tools;
- replace the current keyboard with unrelated suggestions;
- create duplicate project records.

If the agent normally has tools, add a system-level rule for the intake marker/envelope that forbids tool use on this branch. Do not rely only on a casual user-message instruction.

## Implementation sequence

1. Reproduce the exact bad turn with the same active stage and stored intake.
2. Trace routing before changing prompt copy; confirm whether deterministic code bypasses the agent.
3. Separate mutation handling from conversational handling.
4. Add a narrow conversation-turn detector for questions/objections; preserve ordinary brief answers.
5. Build and pass the structured continuation envelope to the existing agent.
6. Reattach the current stage keyboard to the natural response.
7. Inject trusted client identity into the global agent system prompt.
8. Add behavior tests before deployment.

## Behavioral tests

At minimum cover:

- an objection at summary stage reaches the agent instead of being stored as notes;
- the agent payload contains the exact question, client name, current brief, and resume stage;
- the returned reply is sent with the current intake keyboard;
- intake state is unchanged after the conversational turn;
- the recap is not repeated verbatim;
- an explicit format/count change still mutates the draft;
- no production tool or workflow run is created by the question;
- explicit approval still works through its own gate.

Prefer assertions on state transitions and outbound payloads, not source-text snapshots.

## Verification

Run the focused intake/agent tests, then adjacent workflow approval tests, then the Worker build/dry-run. After deployment verify the deployed version and health endpoint. Avoid injecting a forged message into a real client's active chat merely to claim a smoke test; use an isolated test tenant or ask the client to repeat the original phrase.

## Pitfalls

- **Prompt-only fix:** useless when deterministic routing never reaches the prompt.
- **Route every free-text turn to the agent:** loses reliable structured field updates.
- **Classify every sentence beginning with “mais” as a question:** swallows valid amendments such as `mais je veux 3 vidéos`.
- **Answer then drop the keyboard:** the conversation feels natural once and stranded afterward.
- **Always prefix the name:** sounds less professional, not more.
- **Treat `Je valide` and planning language alike:** risks premature production.

## Reference

- `references/scena-telegram-guided-intake.md` — concrete Scena failure mode, routing correction, and regression shape that produced this class-level pattern.
- `references/client-facing-response-style.md` — response-length/tone contract, prompt surfaces, payload-level tests, and Worker verification pattern.
- `references/openrouter-model-reasoning-contract.md` — provider/model/reasoning contract, live-catalog evidence, multimodal routing checks, and the model-ID-vs-effort regression lesson.
