# Audit of a candidate "lot" / plugin upgrade against a certified baseline

Use when the deliverable is a git-tracked candidate (a "lot", an upgrade SKU, a
plugin version bump) that must PROVE it (a) changed nothing in the frozen
baseline / V1 core, (b) added no new model-facing surface, (c) satisfies
isolation/fail-open/boundedness gates, while (d) still returning the exact
same objects to the host. Pre-stated pass counts ("133 before review") are
signals to reproduce, not to trust.

Scenario that produced this: Lot 2.2 "passive observation bus" added to a
previously certified Lot 2.1 plugin. Audit verdict was `passed:true` with 0
must-fix; the checklist below is the reusable method.

## 1. Prove no baseline mutation (in-repo side)
- `git rev-parse HEAD` → pin the audited commit. Reject drift.
- `git diff --name-status <seed>..HEAD` must be ALL `A` (added) — any `M`/`D`
  on a V1/frozen file is an immediate fail. A purely-additive diff is the
  strongest single proof of "no V1 core touched".
- Confirm the V1/frozen core is NOT inside the candidate repo at all (e.g. no
  `tools/` dir). If it lives elsewhere, that's a feature: the repo can't mutate
  what it doesn't contain.

## 2. Prove the external baseline is intact
- The V1 core is a separate release tree. Verify it is git-clean
  (`git status --porcelain` empty) — an empty status during the audit.
- Pin the model-facing schema: `sha256(json.dumps(COMPUTER_USE_SCHEMA, sort_keys=True, separators=(",",":")))` must equal the certified baseline SHA. Assert it again *after* loading the plugin so you prove plugin-load doesn't mutate the schema.

## 3. Prove "no new model-facing surface"
- Byte-compare the candidate's `register()` surface (backend name, action name,
  prompt section id) against the *deployed predecessor* at its install path.
  Identical registration ⇒ the diff added no backend/action/prompt/schema even
  when the whole file shows as `A` in the diff (file moved into the repo).
- Count registrations: exactly one backend, one action, one prompt; assert no
  `register_tool(`, no new backend name string, in the source.

## 4. Seam contract: exact-object return
For an instrumentation hook layered onto existing methods, the gate is
**object identity, not shape**: assert `result is original` / `result is expected`
on the return path. A hook that deep-copies or rebuilds the return object is a
silent behavior change even if bytes look equal.
- `capture()` → run V1 → publish on a seam *after* V1 completes; `_action()` →
  `super()._action()` then publish; return the SAME object.
- Grep that the seam is NOT a private-transport hook (`_call_tool_async`,
  `_call_tool_via_cli`, `session.call_tool =`).

## 5. Isolation / forbidden-capability gate (observer, plugin internals)
Do not trust the doc's "imports no X" claim or an in-repo test asserting it —
verify both directly:
- AST import-set analysis of the module; assert disjoint from
  `{anthropic,httpx,mcp,openai,playwright,requests,selenium,socket,sqlite3,subprocess,urllib}`.
- Grep the module source for forbidden markers: `CuaDriverBackend`, `.call_tool(`,
  `open(`, `write_*`, `vision_analyze(`/`web_search(`/`web_extract(`.
- Grep for recipe/planner/app-specific logic (retry planning, app names) if the
  gate is "no active control / no Active Mode".

## 6. Fail-open + bounded async
- Producer catches all exceptions (fail-open): a crash/drop in the observer must
  never alter V1's returned object. Prove with a test that injects a blocking
 + crashing consumer, runs several returns, asserts identity preserved AND
  `dropped>=1`, `consumer_errors>=1`.
- Bounded: `queue.Queue(maxsize=N)` with `put_nowait` (drop on Full, never wait),
  daemon worker, `close()` joins with a timeout. Grep the constants.

## 7. Honest-unknown + no-fabrication gates
- Absent fields must be explicitly `null`/`None` (`generation`, User Presence),
  never inferred from opaque tokens and never filled in.
- Stale detection by *set replacement* (`current - next`), never by parsing the
  token value; statuses current/stale/unknown.
- When generation/identity doesn't exist in the V1 boundary, an honest 0%
  "unknown reduction" with a stated reason is CORRECT — it is not a defect.
- Sanitized artifacts: re-run the sanitizer's own forbidden-string assertion
  (`assert_sanitized` / grep for secret markers) over the shipped JSON.

## 8. Running the suite read-only with an external release
- Tests import the frozen core (`tools.computer_use.*`): set
  `PYTHONPATH=<external release path>`.
- Keep strict read-only: `PYTHONDONTWRITEBYTECODE=1 ... pytest -p no:cacheprovider`.
- End with `git status --porcelain` empty to prove the audit mutated nothing.
- Confirm the 133/live benchmark numbers are reproducible from the committed
  artifacts and that the report is internally honest (schema SHA before==after,
  `model_facing_schema_changed=false`, `v1_semantic_behavior_changed=false`).

## Pitfall: vacuous self-check metrics
A telemetry counter/metric computed *after* the value it guards was already
replaced is 0 by algebra and can never fire (e.g. an "incorrectly_current"
count computed after `current = new`). The code may even carry a comment
admitting it. It's not a security gate and never blocks, but flag it as
non-blocking dead instrumentation rather than crediting it as a real check.

## Hardening-commit tautology check (the decisive non-vacuity proof)
When a claim is "computed by comparing source and emitted token sequences, not
hard-coded constants", don't just read the current code — diff the metric
computation against its parent: `git show <audited-commit> -- <file>`. The
audited commit often turns out to have REPLACED a tautological detector in the
parent (hardcoded `refs_lost:0, refs_mutated:0`, self-referential
`preserved = input`, plus an "incorrectly_current" guard that is 0 by algebra
because it's computed after the set was already replaced) with a genuine
source-vs-emitted comparison (multiset intersection/difference + exact-sequence
equality). That diff is the strongest proof the committed 26943/26943/0/0/0
figures are real, not self-fulfilling. As a negative control, adversarially
feed the detector loss / replacement / reorder / duplicate-loss / extra
sequences and confirm it fires on each (identity→0 lost/0 mutated/exact; drop→
lost=1; replacement→lost=1 mutated=1; reorder→mutated=1 with lost=0 — order-only
loss is NOT counted as `lost`; extra→mutated=1). Non-vacuity = a detector that
CAN report loss/replacement/reorder, not one that echoes its input.

## Derived-metric cross-check — never ratio-of-percentiles
Percentiles of a ratio (e.g. reduction%) are NOT the ratio of percentiles —
recomputing reduction from raw/compact *percentiles* will (correctly) mismatch
and produce a false "inconsistent metric" finding. Instead pair the extreme
per-row values: the min-reduction row and max-reduction row must match the
corresponding min/max raw- and compact-char rows. e.g.
`(52436-2942)/52436 = 94.389%` (the min) and `(166580-2711)/166580 = 98.373%`
(the max) ⇔ per-row consistency holds even though ratio-of-percentiles fails.
Also assert count == declared runs and min≤p50≤p95≤max on EVERY stat block, and
token estimates are exactly `ceil(serialized_chars/4)`.

## Certified-runtime equivalence — prove the gateway execs the release
"Surfaces equal under the certified runtime" is only meaningful if the live
gateway actually RUNS that runtime. Check `ps aux | grep gateway` → the process
must exec the certified release path (e.g.
`/root/.hermes/releases/<name>/venv/bin/python -m hermes_cli.main gateway run`),
not an editable source checkout (`/root/.hermes/hermes-agent`) that unrelated
services (dashboard, memory) may use. Then run the equivalence probe under the
certified release using the DEPLOYED predecessor plugin at its install path
(e.g. `~/.hermes/plugins/<name>`, version pinned) as the baseline — NEVER the
editable checkout — and byte-compare probe output to the committed artifact
(modulo the version field) before trusting `surfaces_equal`.

## Interpreting large "stale churn" aggregates — check the raw field spread
A near-total cross-capture token-set churn (stale_refs 26402 vs input 26943)
looks impossible on a static window — and it is: it signals a NON-static
observed window. Confirm by checking the committed per-capture field spread
(raw_chars min 52,436 vs max 166,580 ≈ 3x variance ⇒ the captured content
changed during the run). Frame it honestly ("token-set churn, not a native
generation claim") and do not cite the figure as evidence of genuine AX-ref
replacement absent proof of element-token stability across captures.

## PII/secret sweep of sanitized artifacts
Grep the shipped JSON for: IPv4 octets, email regex, `sk-`/`pk-`/`ak-`/`rk-`
keys, `Bearer`, JWT triplets (`x.y.z`), `-----BEGIN ... PRIVATE KEY-----`, MAC
addresses, and LIVE NUMERIC `pid`/`window_id`/`session_id`/`device_id` values.
Explicit redaction markers like `<redacted-app>` / `<opaque-...>` are FINE and
expected — the sweep targets real identifiers/secrets leaking through, not
redaction placeholders.

## Re-audit of a hardening follow-up commit (second pass, same gate)

When a later commit claims to FIX the above (bounded telemetry, opt-in default
flipped to false, non-vacuous integrity, condition-flush), do NOT trust the new
in-repo guard tests — they assert their own claims. Verify each corrective
claim directly in code + config + a re-run:

- **Opt-in default false = two facts, both must hold.** (1) The default branch
  of the config reader returns False when the config key is absent
  (`_configured_observer_enabled` → `return False` / `enabled is True`, not
  `enabled is not False`). (2) The LIVE config actually lacks the enabling key
  (grep the deployed/live config yaml for the `observer` key). A code default
  that some other config block or env already turns on is not opt-in.
- **Bounded-retention audit (every historical container).** Enumerate ALL state
  containers in the async/telemetry module — `grep -nE "deque|maxlen|append\(|\.append\(|set\(|Counter"` — and classify each: it must be a bounded `deque(maxlen=N)` or an integer/`Counter` over a FINITE fixed key set (operation names, levels, presence keys). An unbounded `list`/`set` appended-to per event (e.g. `_seen: set`, `_compactions: list`) is the growth bug to catch. This session: event queuers/latency rings/compactions were `deque(maxlen=256)`, counters keyed on enums — all bounded.
- **Vacuous-metric fix = RESOLVED by removal, not kept.** Confirmed-by-contrast:
  the follow-up removed the `_seen` unbounded set and the algebraically-zero
  `incorrectly_current` counter, leaving `_current` + last `_stale` only, and
  replaced the dead metric with a real integrity computation — `_ref_integrity`
  digest-compares source-vs-emitted token sequences and reports
  preserved/lost/mutated. Assert the removed counter is GONE (`grep` it absent),
  not just bypassed.
- **Condition-flush not busy-poll.** `flush()` must wait on
  `queue.all_tasks_done.wait(timeout=...)` (a condition) — a `while`+`time.sleep`
  poll loop is the pre-fix pattern.
- **Seam still AFTER return.** Re-confirm `result = super()._action(...)` then
  `self._publish_action(result)`; `_finish_capture` publishes then returns the
  same object. Grep that no `_call_tool_async`/`_call_tool_via_cli`/`session.call_tool =`
  private-transport hook appeared.
- **Seam introduces no second device call.** Observer path may call
  `super().capture()`/`list_windows()` once (pre-existing) but must never
  re-invoke a device call itself — the publish fan-out only builds events from
  already-computed results and does `queue.put_nowait`. Grep the observer for
  `capture(`/`_action(`/backend calls: zero hits in the publish path = no second
  device call.
- **Fail-open + drop-on-full re-verify.** Publish uses `put_nowait` and on
  `queue.Full` records `dropped=True, accepted=False` (never blocks, never
  crashes); fan-out wrapped in try/except. Confirms telemetry can't perturb V1.
- **Dynamic surface re-probe, don't trust the committed artifact.** Re-run the
  surface-equivalence benchmark itself under an isolated `HERMES_HOME` against
  the certified release: assert `surfaces_equal=true`, `override_sha256` equal
  across baseline/candidate, AND `raw_schema_sha256 == certified baseline`
  (proves plugin load doesn't mutate the schema). The checked-in artifact is not
  evidence you ran it.
- **Test-count cross-check.** To confirm a documented total ("136 passed"),
  sum the disjoint subsets (`tests/` alone + plugin-side `test_*.py` — note
  pytest root discovery DOES recurse into `deploy/`-style subdirs, so a bare
  root `pytest -q` already includes both). If the document's command adds them
  explicitly, verify the subsets are disjoint and sum to the number.
- **Live/device benchmark is not CI-reproducible.** Absolute measured numbers
  (native-refs counts, latency percentiles) in a headless env are static
  artifact values — the *structure* (equal call counts both arms, drop/error==0,
  observer critical path) is auditable, the numbers are not. Say so rather than
  re-deriving them, and check the doc marks dynamic equality non-gating.
- **Doc-coherence check.** If README/deliverable instructs a step that can't be
  run in the audited tree (e.g. `sha256sum -c SHA256SUMS` when no `SHA256SUMS`
  manifest exists), that is a should_fix — the published verification path
  claims a step the reviewer cannot reproduce.
