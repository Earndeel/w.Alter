# Live Observation Bus — seam audit and closure discipline

Use this reference when a passive Computer Use observer needs facts that are
richer than `CaptureResult` or the model-facing `computer_use` response. It
records class-level architectural findings from Walter Operator Lot 2.2; it is
not a claim that any particular deployment is closed.

## Authority boundary

Keep the roles explicit:

```text
Hermes orchestrator LLM
  understands the goal, chooses strategy, requests observations/actions,
  interprets results, and adapts the plan

Walter Operator substrate
  DeviceContext + observations + capabilities + execution primitives
  + interruption/safety enforcement + native/AX/vision mechanisms
  + verification facts
```

The observation bus transports facts. It must never add app recipes, workflow
branches, retry planning, or a second general-purpose LLM. The public Hermes
tool remains `computer_use`; a product/architecture name must not force a tool
rename or add another model-facing tool.

## Data-loss ladder

The four relevant observation surfaces have different fidelity:

1. **Persisted state/event sidecar** — strongest process isolation, but delayed
   and potentially truncated. It cannot recover native refs that were never
   persisted.
2. **`post_tool_call` / tool middleware** — stable plugin seam and authoritative
   tool-level timing, but sees the serialized/model-facing response.
3. **Backend wrapper after method return** — stable plugin backend seam and full
   `CaptureResult.elements`, including `UIElement.element_token`; however raw
   transport-only fields such as an explicit `snapshot_id` or `generation` may
   already have been discarded during conversion.
4. **Resolved transport-result seam before conversion** — highest fidelity:
   full `structuredContent`, native element tokens, snapshot/generation when the
   driver actually supplies them, backend health, and geometry. This is the
   correct conceptual seam when those fields are mandatory, but Hermes should
   expose it as a supported observer callback rather than requiring a plugin to
   monkey-patch private session methods.

Never state that a backend wrapper preserves every native field merely because
it preserves the full AX element list. Verify `snapshot_id`, `generation`,
geometry, and health separately and leave absent values unknown.

## Why private transport interception is tricky

In the current Cua backend, the data path is not a single naïve callback:

- `_CuaDriverSession._call_tool_async(name, args)` returns the extracted MCP
  result dictionary;
- `call_tool(...)` performs recovery and can fall back to
  `_call_tool_via_cli(...)`;
- capture and window enumeration also contain explicit direct CLI re-fetches
  when an MCP result is empty or missing the required payload;
- typed-browser routing may retain a bound `call_tool` callback created during
  backend initialization.

Consequences:

- wrapping only backend methods loses transport-only fields;
- replacing `session.call_tool` after backend construction may miss callbacks
  already bound elsewhere;
- wrapping only `_call_tool_async` misses direct CLI re-fetches;
- wrapping both `_call_tool_async` and `_call_tool_via_cli` can emit two events
  for one logical observation when an MCP response succeeds but is unusable and
  V1 re-fetches via CLI;
- wrapping `call_tool` plus `_call_tool_via_cli` can also double-publish when
  `call_tool` itself invokes the wrapped CLI fallback.

Therefore a private interception implementation is **not closable** until tests
cover all MCP, retry, reconnect, empty-result re-fetch, and direct CLI paths and
prove exactly one final observation per logical V1 acquisition. The durable
solution is a host-owned callback emitted once after V1 has selected the final
resolved backend result and before conversion/truncation.

A conceptual host contract is:

```python
result = existing_v1_backend_call()
deliver_to_v1(result)
try:
    observer.enqueue_immutable_copy(result)  # bounded, non-blocking
except Exception:
    record_shadow_failure_out_of_band()
```

The callback must not execute observer logic on the V1 thread. Its only
critical-path work is a bounded immutable copy plus `put_nowait`; queue full
means a measured shadow drop, never blocking or retrying V1.

## Lifecycle and isolation

- Create no worker thread merely by importing a plugin.
- Scope one observer runtime to one backend/session instance.
- Start the queue without starting an extra device transport.
- On shutdown, stop the existing V1 backend and close the observer in `finally`;
  an observer shutdown failure must not suppress V1 cleanup.
- Return the exact V1 object/value unchanged. Do not reconstruct or normalize the
  value returned to Hermes.
- Never reacquire facts: no extra capture, AX observe, SSH call, Mac RPC,
  screenshot request, or vision request.
- Observer callback exceptions, slowness, and queue overflow must be tested and
  must not change V1 return values, call counts, or exception behavior.
- Keep a packaged-plugin smoke test in an isolated Hermes home: load the real
  dependency and observer plugin, instantiate without transport start, and
  compare the `computer_use` schema digest before/after.

## Validated integrated-plugin pattern

When the active configuration already selects a named plugin backend, prefer an
**additive update of that same backend/plugin name** over a new observer backend
or a private transport proxy. The narrow proven pattern is:

1. call the existing backend method exactly once;
2. complete all existing V1 finalization first (integrity marking, target/cache
   updates, recovery metadata);
3. build one immutable, pixel-free observation from the full returned object
   before core response capping/serialization;
4. enqueue it with bounded `put_nowait` fan-out;
5. return the exact same V1 object by identity;
6. observe `ActionResult` only after the existing atomic `_action` returns.

This preserves full AX elements and opaque native tokens without changing the
backend selector, public tool, action enum, prompt, approvals, or dispatch. It
also avoids the duplicate-event traps of wrapping MCP plus CLI fallback paths.
Do not claim transport-only `snapshot_id`/generation fields at this seam when
the backend object does not expose them.

The observer must be privacy-preserving **opt-in**. Importing the plugin or
constructing a backend with no explicit enable flag must create no worker.
Bound every historical retention, not merely the event queue: critical-path
samples, enqueue/wait/processing samples, compaction rows, and stale-ref state
must all use fixed windows. Preserve cumulative counters separately. A bounded
queue plus unbounded metrics is not a bounded subsystem.

For shutdown, wait on the queue's task-completion condition with a deadline;
do not busy-poll. Observer close failures remain isolated from V1 cleanup.

## Goal and interruption evidence

Do not re-run a goal through a proxy router merely to observe atomics; that risks
changing V1 semantics and can become a hidden second planner. Observe the
transport calls generated by the existing V1 execution.

If goal attribution uses in-memory context:

- use only a short bookkeeping lock; never serialize device execution;
- under concurrent or ambiguous attribution, classify the composite goal as
  `unknown` rather than guessing;
- keep atomics and composite goals on different denominators;
- classify L0/L1/L2 from observed atomic operations only;
- no active warning or confirmation belongs in a passive lot.

## Native-ref accounting

Keep these counters distinct:

- `native_refs_input`: opaque refs read from the source `CaptureResult` before
  event construction;
- `native_refs_preserved`: multiset intersection between source tokens and
  tokens actually emitted into the immutable event;
- `native_refs_disclosed`: refs retained in the selected compact view;
- `refs_lost`: source multiset minus emitted multiset;
- `refs_mutated`: unexpected emitted tokens plus an explicit exact-sequence
  failure when multisets match but order changed;
- `exact_sequence_failures`: source token sequence hash/order differs from the
  emitted sequence;
- `generation_bound_refs`: refs whose native generation/snapshot evidence was
  actually present;
- `snapshot_ref_replacements_observed`: tokens removed by the latest current-set
  replacement.

Do not hard-code `preserved=input`, `lost=0`, or `mutated=0`. The detector must
have adversarial tests for loss, replacement, duplicate loss, extra token, and
reordering, and the live ledger must aggregate the detector's results. A
sanitized shape fixture that has only one token list cannot prove preservation;
mark its integrity as unevaluated and bind the claim to the integrated boundary
comparison.

A stale/generation gate is not proven by zero failures when zero refs were
checked. If the backend object exposes no explicit native generation, keep
`generation=null` and call set churn what it is: a **snapshot token-set
replacement observation**, not a native generation proof. Keep only the current
set plus the most recent removed set so ref history remains bounded; older refs
become `unknown`, never guessed current or stale.

## Progressive observation and User Presence

Progressive views are deterministic projections of the same immutable raw
source: `minimal`, `relevant`, and `detailed`. There is no LLM in the compactor.
Report raw and compact character counts, token estimates such as
`ceil(chars/4)` explicitly as estimates, information loss, ref disclosure, and
compaction latency.

For User Presence, reuse only fields already acquired by V1/driver. An absent
signal remains unknown. A separate read-only DeviceContext probe can be designed
only as an independently justified, bounded source; it must not run once per
goal or be disguised as part of the observation bus.

## Benchmark and closure gates

Use **one backend instance and one driver session**, with baseline/observer
captures alternated pairwise. Sequentially benchmarking two separate sessions
confounds observer cost with target/session drift and fallback instability.
Instrument the existing MCP and CLI fallback transports for counting only; the
observer must never call either. Require equal call dictionaries between arms,
not an idealized fixed transport path.

Treat live AX payload equality as descriptive rather than a semantic gate when
captures are non-simultaneous. The semantic gate comes from exact-return
identity tests plus the AX/no-pixel contract. Report paired wall-clock
differences without attributing the full noisy p95 to the observer; separately
measure the boundary critical path, enqueue, queue wait, processing, and
compaction.

Never accept zero-on-zero ref preservation. A final refs gate requires
`native_refs_input > 0`, exact source→emitted sequence integrity, and at least
one real token-set replacement if replacement behavior is claimed. If a live
target becomes empty/invalid, move to another already-open safe AX target or
leave the benchmark blocked; do not weaken the gate. A failed run can remain as
latency-only evidence only when labeled non-certifying.

Run enough independent samples per arm and exclude warmups. Measure, rather than
assume:

- V1 total and backend latency p50/p95/min/max;
- observer enqueue, queue-wait, processing, and compaction latency;
- real extra critical-path latency;
- backend/Mac RPC/capture/AX counts in each arm;
- observer events, errors, drops, and V1 failures;
- raw/compact chars and token estimates;
- native refs received, preserved, disclosed, lost, mutated, generation-bound,
  and stale-checked;
- User Presence known vs unknown without promotion.

Async does not mean `0 ms`. `extra_critical_path_latency=0` is valid only as a
process-topology invariant for an out-of-process sidecar; an in-process enqueue
must be measured.

Before declaring closure, require all of the following on the exact final source
and clean extracted artifact:

1. full tests and static guards pass after the last seam change;
2. live comparative benchmark completes on a verified safe target;
3. compare the **deployed baseline plugin** and candidate plugin dynamically in
   two isolated Hermes homes under the same certified runtime: raw core schema,
   dynamic override digest, tool name, backend, registered actions, action enum,
   and extension properties must match. Do not compare against an unrelated
   editable checkout merely because it is importable;
4. device-call counters are equal and duplicate observations are zero;
5. no V2 mutation/screenshot/vision and no observer exception affects V1;
6. source→emitted ref integrity and a non-vacuous replacement test pass;
7. presence unknowns are not promoted;
8. two independent reviews on the final immutable commit return `passed=true`
   and `must_fix=[]`; any correction invalidates prior reviews and requires two
   fresh reviews;
9. create the archive from Git-tracked files, add verbatim review JSON, a final
   manifest and per-file checksums, normalize archive metadata, then extract,
   verify checksums, and rerun the full suite;
10. installation is a separate transaction: backup the old plugin outside
    discovery, atomically swap the same plugin/backend name, explicitly enable
    the opt-in observer, restart through the real supervisor, health-check and
    run compatibility in a fresh process, and automatically restore plugin,
    config, and service on failure. This must not start Active Mode.

The archive builder itself must fail closed on a missing/failed reviewer or
failed benchmark/surface-equivalence evidence. Verify determinism by creating
two archives from identical inputs and comparing bytes/hashes. Keep test-smoke
reviews clearly synthetic and never ship them as final certificates.

A benchmark that never reached the target, a seam edited after the last green
test run, or a reviewer that timed out leaves the lot OPEN. Do not convert those
conditions into a certificate or a recommended implementation pattern.
