# Adaptive Universal Operator — contract patterns

Use this reference when evolving Computer Use from a fixed goal router toward a generic adaptive operator while keeping the LLM as the decision-maker.

## Architectural split

- **LLM:** interprets the goal, chooses an offered capability, decides whether to observe more, research via Walter Browse, act, or adapt after failure.
- **Runtime:** discovers devices/capabilities, returns compact deterministic facts and costs, enforces safety, executes exactly one selected step, observes, and verifies.
- **Walter Browse:** owns public Web research/documentation. Computer Use must not grow HTTP, Scrapling, Camoufox, Playwright, or visible-browser research paths.
- **Device Node:** owns device-local execution and state probes; it does not invent workflows.

Unknown goals should normally produce observation/capability evidence for another LLM decision, not `unsupported_goal` or an app-specific recipe.

## Anti-RPA invariants

- No `if app == ...` workflows in the generic runtime.
- No hidden planning, polling, retry, or adaptation loops.
- Capability ranking is advisory; expose `selection_authority=llm` and never auto-dispatch the first offer.
- Provider offers carry immutable effect/precondition metadata; the model cannot lower their interruption class.
- Fast vision only locates/returns geometry and confidence. It never clicks.
- Act → Observe → Verify executes one LLM-selected offer. On failure return structured evidence plus `adaptation_required=true`.

## DeviceContext split and merge rules

Keep stable and volatile state distinct:

- stable profile: device ID, platform, hostname, transport references, displays, installed apps/capabilities;
- volatile state: activity and health, each with its own `observed_at`;
- never persist AX trees, screenshots, refs, or view snapshots in DeviceContext.

Safe merge rules:

1. A `device_id` cannot change platform.
2. A stale discovered profile cannot overwrite a newer profile.
3. Activity/health updates must not overwrite stable fields or extend the stable-profile TTL.
4. Merge app/capability collections deterministically; do not synthesize a field-by-field hybrid machine.
5. Store credential references only, never secrets.

Provide a dedicated `update_runtime_state()` path instead of overloading full-profile `upsert()` with partial observations.

## Enforcement contract

L0/L1/L2 are effect-derived safety classes, not an escalation ladder:

- **L0:** silent, non-disruptive action;
- **L1:** visible/disruptive action with warning receipt;
- **L2:** sensitive/irreversible action with explicit confirmation grant.

Derive the class from provider-declared immutable effects. Enforce immediately before dispatch. Evidence must be opaque, scoped to device + offer/step + effects, expiring, and single-use. If the required gate/reader is absent, refuse rather than assuming an external layer handled it.

## Progressive observation contract

Use deterministic disclosure levels such as `minimal → relevant → detailed → pixels`:

- preserve AX order by default;
- filter only when the caller supplies an explicit literal query;
- bind refs to snapshot/generation and reject unknown or stale refs;
- require an explicit crop for pixels;
- do not silently attach AX elements to a pixels-only response;
- bind action preconditions to a trusted runtime `snapshot_reader`, not merely a snapshot ID echoed by the model.

## Executable façade

A compact façade may expose `inspect | act | status`, but each operation must be real and fail closed:

- `inspect` returns offers/observations without execution;
- `act` resolves one registered Computer Use offer, validates trusted current snapshot and safety evidence, then prepares/dispatches one step;
- `status` reads only through an injected operation reader and does not poll or retry automatically.

## TDD guards worth keeping

Add focused tests for:

- partial activity refresh preserving stable profile fields and TTL;
- stale profile ignored; platform mutation refused;
- injected cost weights changing advisory order without execution;
- missing route evidence failing a benchmark;
- visual scenario requiring both minimum and maximum screenshot/vision counts;
- unknown detailed ref refused; pixels requiring crop;
- bound snapshot requiring a trusted reader;
- `status` refusing without an injected reader.

## Review and artifact discipline

Freeze the deliverable as an archive with a SHA-256 manifest, extract it into a fresh directory, verify every manifest entry, rerun tests and the contract benchmark from the extracted copy, then ask the independent reviewer to audit that exact archive hash. A review started before the final hash cannot certify later changes.
