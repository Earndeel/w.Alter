# macOS operator completion — integration and acceptance guardrails

Use this reference when extending a plugin-backed macOS Computer Use operator from a narrow active loop to a general-purpose surface. It records reusable integration lessons; it is not evidence that any particular release is complete.

## Preserve the one-front-door contract

- Keep `computer_use` as the only model-facing tool. Plugin actions are extensions of its action discriminator, not separate Walter tools.
- Hermes remains the only semantic planner. The runtime may expose device facts, capabilities, refs, interruption decisions, one primitive, and bounded verification. It must not select a multi-control app recipe.
- An arbitrary goal that names no application is not inherently unsupported. Observe the current active app/window generically (`list_apps` + `list_windows` + targeted AX), return compact state/offers, and let the LLM decide. Return `needs_user_input` only when no current on-screen target can be established. Never add an app-specific recipe merely to pass an unknown-app test.
- For long completion programs, finish all non-blocked vertical slices before reporting. Treat `must_fix` as immediate work and `should_fix` as backlog; perform the requested single global review only after E2E evidence exists.

## Dynamic action registration: verify the effective surface

Plugin action registration is dynamic and scope-bound. The static `COMPUTER_USE_SCHEMA` action enum is intentionally unchanged; registration is visible through the action-extension registry and the registry's dynamic schema overrides.

Consequences:

1. Do not test a plugin action by asserting that the static base enum was mutated.
2. In a fresh Hermes process, load `PluginManager`, then verify `registered_action_extensions()` / `get_action_extension(name)` and the effective registry schema.
3. A conversation's tool schema is fixed when that session starts. A newly deployed/restarted plugin action can still return `unknown action` in an already-running conversation even when a fresh process proves registration. Run the natural model-facing acceptance trace in a fresh Hermes session after cutover.
4. Separate these verdicts in reports: `plugin action registered`, `effective schema offers action`, and `current conversation received refreshed schema`.

This distinction prevents both false negatives (a stale conversation says unknown) and false positives (a fresh Python process registers the action, but the model-facing session never received it).

## Inspect the live driver contract instead of rebuilding it

Before adding wrappers, start the selected plugin backend in a fresh process and inspect the live driver tool schemas. Treat names and JSON schemas as the authority for the connected driver version. Reuse existing primitives such as clipboard, zoom/crop, verification, window framing, cursor, drag, horizontal scroll, and exact PID/window targeting when advertised.

Keep this inventory read-only. Do not infer availability from package release notes alone, and do not create a parallel native stack for a primitive already exposed by cua-driver.

## Presence and interruption enforcement

- Cache read-only presence with a TTL; do not probe once per primitive while state is fresh.
- Preserve `unknown` as unknown. Never normalize it to `false`.
- L0 inventory/observation should not force a presence probe.
- L1 is effect-derived. Explicit foreground user work may proceed with a collision warning; autonomous work may defer when the user is active. Locked desktop must refuse visible input before driver dispatch.
- L2 is capability/effect-derived and fail-closed before mutation. Goal-text matching may conservatively escalate, but it is not sufficient as the only classifier for the primitive surface.
- Apply the gate to every mutation primitive, not only the high-level goal route.

## Progressive observation and vision sensor

- `minimal`, `relevant`, and `detailed` remain AX-only unless pixels are explicitly needed.
- Use driver-native window crop/zoom where available. Preserve exact PID/window identity and driver geometry metadata.
- Visual refs are short-lived and bound to snapshot, generation, PID, window ID, crop dimensions, source region, confidence, and TTL. Invalidate on new capture/target/generation and reject stale refs before input.
- A fast vision request returns only target bounds and confidence. It never chooses or executes an action.
- Never invent Retina scaling. Unknown or low-confidence mapping returns `adaptation_required=true` with no click.

## Uniform action result

Every mutation should preserve driver fields and add an operator envelope containing at least:

- `success`, `effect`, `verified`, `verification_source`, `new_snapshot`;
- `failure_reason`, `stale`, `adaptation_required`, `needs_confirmation`;
- `next_authority=llm`, plus interruption/presence state when relevant.

Tests for extensible metadata must assert required keys additively, not compare the entire dict exactly. Exact-dict assertions turn legitimate additive contracts into fake regressions.

## Acceptance discipline

A completion claim requires all of the following on the exact final candidate:

1. targeted and full regression suites green;
2. fresh-session natural `computer_use(goal)` selection;
3. representative live macOS E2E, including one multi-decision LLM loop, unknown app, stale AX/visual refs, L2 no-mutation, user-active/idle policy, and targeted vision fallback;
4. useful measured metrics, not benchmark theatre;
5. one independent final review with `must_fix=[]`;
6. transactional deployment, gateway restart if required, fresh effective-schema verification, and rollback preservation.

If a tool-iteration cap interrupts the work, report `NOT COMPLETE` and preserve the exact unfinished gate. Do not convert partial unit coverage into production completion.
