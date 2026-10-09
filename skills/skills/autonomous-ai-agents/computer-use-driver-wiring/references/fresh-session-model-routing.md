# Fresh-session model-facing routing gates

Use this reference when a `computer_use` backend plugin adds a high-level action such as `goal`, changes schema ownership/precedence, or is released behind the gateway.

## Validate the real product surface

A fresh conversation is not necessarily a fresh agent process. Validate after the live plugin is installed and the gateway has restarted, using the exact platform profile that normal sessions use.

Check the actual assembled payload, not only fixtures:

- selected backend and plugin owner;
- live `computer_use` schema, including the high-level action and its argument property;
- plugin prompt section and its precedence;
- normal platform skill index;
- first structured device tool call in a genuinely new session.

If a high-level front door is intended, competing low-level skills must not force `capture → primitive → capture` before the first goal call. Keep primitives available for explicit low-level work, debugging, and bounded adaptation rather than making them the ordinary route.

## Completion semantics

`process_running=true` proves only that an application process exists. It is never sufficient proof that a URL, interaction, multi-app sequence, or verification goal completed.

Fail closed:

- A requested URL needs evidence that the request was accepted and the target window became addressable.
- A goal containing later interaction or verification steps cannot return `completed` after launch alone.
- `window_ready=false`, missing native window ID, or absent AX target returns `needs_action`, `unverifiable`, or `adaptation_required` with the first blocker.
- Preserve the distinction between native launch success and user-task completion.

Natural-language routing must tolerate ordinary model paraphrases. Regression cases should use the **actual model-emitted goal argument**, not only the user's original wording: tense, infinitive/imperative, accents, and connectors such as “vers/to” must not silently erase URL or interaction intent.

## Loop and input gates

- Bound retries for an identical observation failure with no changed evidence.
- Permit native/AX continuation when pixels fail but are unnecessary; otherwise return adaptation/user-input state.
- Refuse an identical unverifiable action when no fresh observation shows progress.
- A driver's safe-window is capture infrastructure, not the semantic keyboard target.

## E2E evidence without contaminating the test

Measure and inspect persisted structured messages only **after** the user task. Count structured tool calls, not tool-like strings emitted in reasoning or prose.

Report separately:

1. user message → first structured device call;
2. user message → native launch result;
3. total wall time;
4. structured counts for `skill_view`, history search, and repeated observations;
5. first concrete blocker on failure.

A schema/routing pass is not a product pass. Completion requires the requested GUI actions and final verification. If the full E2E fails, skip any persistence-only second session and report `NOT COMPLETE`.
