# Scena Telegram guided-intake correction

## Observed failure

At the final brief summary, the client challenged feasibility because no image reference had been provided. The Worker treated that objection as generic free-text intake data, appended it to `notes`, and rendered the same summary again. The visible result was a bot that ignored the question while claiming the brief was ready.

## Root cause

`index.ts` gave active `project_intake` deterministic priority over the natural agent. The summary handler assumed unrecognized text was either a field modification or additional notes. Prompt improvements in `agent.ts` could not help because this path never reached `handleAgentMessage(...)`.

## Correction pattern

- Keep deterministic parsing for explicit changes such as count, duration, ratio, CTA, or constraints.
- Detect questions and project objections only after checking for those explicit mutations.
- For a conversational turn, call the existing agent with a delimited payload containing:
  - `client.name` from D1;
  - the exact client message;
  - current `project_intake` JSON;
  - current stage and resume instruction;
  - rules to answer first, avoid tools/state mutation, and return to the project briefly.
- Send the natural reply with `buildIntakeKeyboard(intake)` so the guided flow remains usable.
- Add a system-prompt rule for the intake marker to block production/project mutation tools.
- Add a general system-prompt identity rule: use the trusted client first name naturally and sparingly.

## Regression case

Given a complete intake at `stage='summary'` and the message:

`Attends, mais tu vas générer les images et vidéos comment ? Je ne t'ai pas envoyé d'image de référence.`

Assert that:

- the agent endpoint is called;
- its payload contains `Lucas`, the exact objection, the current brief, and the instruction to answer before resuming;
- the Telegram response answers the reference concern and addresses Lucas naturally;
- the validation/modification keyboard remains attached;
- `notes.project_intake` is unchanged;
- no provider-generation endpoint is called;
- the old full recap is not emitted again.

Keep a sibling regression proving `change le format par 3:4` still updates the draft without duplicating the user text.

## Verification lesson

Focused Telegram/agent tests should be followed by the workflow approval regression, because conversational routing and launch gating are adjacent contracts. A stale test mock that matches an obsolete SQL status list can report a false product regression; update the mock to the actual query and verify the resulting terminal state semantically (`completed` when the validation step is last), rather than preserving an outdated expected status.
