# durable-computer-use-architecture — Product-scope audit (backend versus device product): the front-door checklist, approval propagation, effect verification, identity-bound pixels, goal-router evidence.

Moved verbatim from SKILL.md on 2026-11-01.

## Product-scope audit: backend versus device product

A durable Computer Use backend is not automatically a universal device node.
When assessing an implementation against a broader W.Alter-style architecture,
keep these planes separate:

| Plane | What counts as evidence | Common false positive |
|---|---|---|
| UI control plane | AX/UIA/AT-SPI or DOM tree, input delivery, exact target identity, screenshots | Calling a cross-platform CUA library a W.Alter OS adapter |
| Device node | A resident/local component exposing system, files, apps, packages, services, and capabilities through one contract | Counting Hermes' separate terminal/file tools as a device node |
| Verification | Domain postconditions such as `package_present`, `service_running`, or `file_exists` | Treating transport `ok` or driver `effect=confirmed` as task success |
| Privilege broker | Structured capability, risk, consent, TTL, audit, and revocation policy | Treating an approval callback or an `unrestricted` mode as an admin broker |
| Session gateway | Authenticated remote transport, device identity, ephemeral sessions, expiry, and revocation | Treating a local CuaDriver session ID as Tailscale/tsnet connectivity |

Use a scope matrix backed by file/line evidence and live tests. Run the audit
at two levels: **code scope** (what the current repository/plugin implements)
and **deployed scope** (what the live Tailscale/SSH wrappers, services, and
target-side daemons already provide). A missing gateway in one repository is
not evidence that remote connectivity is absent system-wide. Inspect the live
route before concluding, then state the boundary precisely — for example,
“remote transport works for the enrolled Mac, but it is not yet productized as
a generic Device Node session gateway.”

A generic Computer Use schema should be checked for system/file/package/service
actions; if it only exposes capture/input/browser actions, the device plane is
absent from that schema. Likewise, a backend claiming macOS/Windows/Linux
support does not cover Android unless an Android-specific adapter and permission
path are actually present.

### Front-door surface audit (the model-facing checklist)

When auditing or extending the one `computer_use` front door, verify that every
layer of the surface stays in sync; a backend method that is not on the schema
is invisible to every model. The goal is one model-facing tool, not a family of
Walter-specific GUI tools:

- schema action enum ≤ actual `_dispatch` handlers (set-diff both ways);
- `goal` stays inside the existing `computer_use` action enum; transport
  choices (`native`, AX, page, vision, pixel) remain runtime policy, never model
  arguments;
- every enum action is classified in `_SAFE_ACTIONS` or
  `_DESTRUCTIVE_ACTIONS` (destructive → approval, persistent focus → its own
  `bring_to_front` scope);
- the bundled `computer-use` skill's Actions table matches the schema
  (doc-drift is a runtime-exposure gap);
- the core tool retains approval, dispatch, session lifecycle, and multimodal
  result shaping; plugins provide a named backend factory and policy, not a
  duplicate tool or approval layer;
- no hardcoded pixel-scale literal on the input hot path — if physical→logical
  mapping is ever needed, consume the driver's `backing_scale_factor` and fail
  closed when unknown;
- non-vision main models can be served a compact AX payload (image dropped,
  not merely rerouted to auxiliary vision), with bounded labels/elements and
  explicit state markers.

#### Approval propagation is part of the contract

A local tool callback must consult the same central approval resolver as the
Hermes CLI/session (`approvals.mode: off`, YOLO, manual, or session grants).
A global explicit bypass that is ignored by a nested Computer Use callback is a
real integration bug: the request times out before the backend is reached.
Add a regression test that patches the central bypass resolver and proves the
local callback is skipped; test the manual path separately. Never solve this by
silently disabling approval for ordinary sessions.

#### Verification must prove the requested effect

Keep three levels distinct:

1. **Delivery** — the input was accepted by the transport.
2. **UI read-back** — AX/DOM state or a fresh semantic snapshot confirms a
   changed control.
3. **Task postcondition** — a system/API probe confirms the requested outcome.

`verified=true` or `effect="confirmed"` is action evidence, not automatically a
completed user goal. A liveness predicate such as `window.exists=true` proves
that the target survived; it cannot turn an `unverifiable` click into success.
`verify_state` predicates with `unknown` status never imply completion. If no
semantic or state probe exists, say that vision or user confirmation is still
required rather than claiming certainty.

#### Pixel evidence is identity-bound

Raw coordinates are valid only against the newest pixel-bearing capture whose
PID, native window ID, geometry, and coordinate basis match the action target.
An AX-only refresh, target change, failed capture, or stale snapshot must clear
that geometry/token evidence. Prefer element indices or opaque snapshot tokens;
never use a remembered screen size to authorize a later pixel action.

#### Goal-router evidence and benchmark discipline

A useful goal router returns compact state plus a deterministic completion
status, and fails closed when the app/window is not addressable or no target is
proven. Measure separately:

- model-facing tool calls;
- logical backend calls and route names;
- screenshots and auxiliary-vision calls;
- verification calls;
- router latency and result size/token estimate.

Report backend-call savings as model-visible round reductions, not invented
wall-clock speedups. Validate with a deterministic live goal (for example,
launch an explicitly named native app and observe its exact window) and a
negative goal (for example, no selectable AX target); the latter must return
`needs_user_input`/`unverifiable`, never an invented click.

#### Front-door selection is a separate contract

A correct goal router is not a working front door if the model-facing schema,
system guidance, or skill discovery still teaches the model to start with
`capture` and compose primitives. Treat natural selection as its own contract:

1. Put `computer_use(action='goal', goal=...)` first in the tool description and
   system guidance. Describe `capture`, `click`, and related primitives as
   secondary paths for continuation, diagnostics, explicit low-level requests,
   or a runtime-directed continuation — never as the normal high-level workflow.
2. Keep legacy transport recipes out of normal discovery without deleting their
   documentation. Use the existing offer-time metadata condition
   `metadata.hermes.fallback_for_tools: [computer_use]` on SSH, raw-driver,
   legacy screen-server, and competing CDP skills. Explicit `skill_view` and
   preload must remain available for maintenance.
3. Apply the offer filter consistently to the system-prompt index,
   `skills_list`, slash/autocomplete surfaces, and plugin metadata. A skill
   hidden in only one surface remains a bypass in another.
4. State the precedence explicitly: the current supported tool/runtime outranks
   historical sessions and old implementation recipes; the latest explicit user
   target (for example, Safari) outranks remembered preferences (for example,
   Brave). Historical search may recover user context, never execution plumbing.
5. Make the runtime own no-target decisions. When the current AX observation
   does not prove the requested target, return compact `no_target` or
   `needs_user_input` state and perform no reload, arbitrary wait, vision
   fallback, pixel attempt, or plausible-but-unverified click.

The acceptance test must be a fresh, unconstrained natural-language session —
not a prompt that names `goal`. Record model-facing calls, loaded skills,
terminal/SSH/session-history/raw-driver calls, backend routes, screenshots,
vision calls, latency, and tokens. Do not call the front door enforced until
the trace proves natural `computer_use(goal)` selection and the negative
no-target case performs no mutation.

**Completion gate.** A failing regression suite, an unexecuted smoke run, or a
route observed only under a constrained prompt is evidence of incomplete
validation, not partial proof to summarize as complete. Preserve the
work-in-progress status and report the exact blocker; never turn an unverified
attempt into a recommended workflow. If the session ends before the natural
trace, leave the acceptance status open and rerun it from a fresh session.

A goal result with `status: "needs_user_input"` and
`completion_known: true` is terminal for that model turn. The conversation loop
must not hand control back to the model for exploratory `list_apps`, `capture`,
`wait`, `vision`, legacy-skill, SSH, or session-history calls. Test this at the
orchestration seam, not only in the backend: assert that a terminal no-target
result produces zero subsequent tool calls and preserves the backend's
`screenshots`, `vision_calls`, and click counters. A backend that correctly
returns `needs_user_input` while the model continues probing is only a partial
fix. The six natural smoke cases must run as six independently created Hermes
sessions with their raw verbose traces retained; aggregate summaries or a
single wrapper session do not prove isolation.

### Generic terminal-result enforcement

The boundary belongs in the agent loop, not in the goal router and not in
prompt prose. Classify structured tool results generically and record the first
terminal result for the current turn whenever `completion_known: true` and the
status is `needs_user_input`, definitive success/completion, or definitive
`impossible`/`not_available` with no automatic strategy remaining.

Terminality and direct user disclosure are separate capabilities. A legacy
`message` field remains model-facing and must never be returned directly. The
zero-provider-call path requires the complete explicit contract:

```json
{
  "completion_known": true,
  "terminal": true,
  "user_message": "A user-facing final message",
  "safe_to_return": true
}
```

Treat producer certification as necessary but not sufficient: reject direct
return when the payload carries an error/failure status, when forced Hermes
redaction would alter the message, or when the text is shaped like a stack
trace, backend diagnostic, internal error, credential, or transport identifier.
The producer should grant this capability only for a narrow known outcome; for
Computer Use, the high-level `goal` boundary may certify a known-complete,
error-free `needs_user_input`, but arbitrary tool `message` fields may not.

After a terminal result, use exactly one of two paths:

1. **Certified safe final text** — append/persist the assistant text and close
   the turn locally, with zero additional provider calls.
2. **No certified safe text** — preserve the existing one-shot model
   continuation, but send no function schemas (`tools=[]` or the transport
   equivalent). If the model emits stale tool calls anyway, never dispatch
   them; consume only its text and terminate, using protocol-safe skipped
   results only when role/tool-call pairing requires them.

Reset terminal state at the start of the next user turn. Unknown or ambiguous
negative payloads remain non-terminal rather than being guessed terminal. The
classifier and direct-return contract must work for tools other than
`computer_use`.

The regression matrix must prove: certified terminal text → one provider call
total; terminal without certified text → current text-only continuation;
non-terminal → normal loop; internal error/stack trace/secret/diagnostic → never
directly exposed; Computer Use `needs_user_input` → direct reply; and another
tool → same generic contract. Instrument first-provider latency, tool latency,
direct-final overhead, end-to-end time, tokens, and exact call counts. Do not
report completion from old smoke logs: compile touched modules, run focused and
existing dispatch tests, then run a fresh unconstrained smoke on the exact final
source tree.

See `references/terminal-tool-result-enforcement.md` for insertion points,
security gates, test matrix, trace parsing, and benchmark discipline.

See `references/model-facing-front-door-audit.md` for the exact seam method
names, the five-gap Lot 1 inventory, and the uncommitted-work preservation
list. See `references/lot1-front-door-contracts.md` for the approval bypass,
verification, geometry, compact-AX, routing, and E2E evidence patterns. See
`references/natural-front-door-enforcement.md` for the Lot 1.2 discovery,
precedence, trace, and no-op regression record.

When the wider product is not yet built, the next efficient vertical slice is
usually one local device (macOS first if that is the proven host): observe
capabilities, expose bounded system/file/app primitives, add postconditions,
then add the privilege broker. Add Tailscale/tsnet and temporary support
sessions only after the local contract is stable; do not start with Android or
remote distribution.

