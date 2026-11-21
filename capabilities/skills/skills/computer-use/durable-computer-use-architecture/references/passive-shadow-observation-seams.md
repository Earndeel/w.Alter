# Passive shadow-observation seams for the active computer_use path

Goal: instrument the V1 `computer_use` path (LLM → tool → plugin backend → CuaDriver)
with a **read-only shadow / passive telemetry** recorder that (a) never issues a
second backend/RPC call, (b) makes no schema/prompt/response change, (c) swallows
and isolates every shadow exception so a shadow fault is impact-0 on V1, and
(d) leaves production source intact (new plugin/version/config only — never edit
the release or the active plugin).

This is the Lot 2.1 pattern (V2 shadow on the V1 CLOSED path). File:line anchors
are against the active release tree.

## The active V1 chain (so you know where data already exists in memory)

```
LLM
 └─ computer_use           tools/computer_use_tool.py:21-35 (registry)
     → handle_computer_use(args, **kw)      tools/computer_use/tool.py:492
     → approval gate (destructive)          tool.py:531-563
     → _get_backend(session_id)             tool.py:232
     → _configured_backend_name()           tool.py:477-489  (+ config.yaml computer_use.backend)
     → get_backend_factory(name)            tool.py:263      (plugin-selected backend)
     → <plugin backend factory>             hermes_cli/plugins.py:1486 (register_computer_use_backend)
     → _dispatch(backend, action, args)     tool.py:658
     → backend.capture/click/…              cua_backend.py:2337/2907…
     → self._session.call_tool(name,args)   cua_backend.py:1711  (single RPC choke point)
     → MCP stdio → remote shim → SSH/Tailscale → cua-driver
```

Key: the active backend is often ALREADY a wrapper (e.g. `WalterCuaBackend(CuaDriverBackend)`),
so every V1 request and result (including the full AX tree) exists in-process at the
backend layer. A shadow never needs its own `list_windows`/`get_window_state`/`verify_state`.

## Four seams, ranked by coupling to the active process

### 0. Persisted-event sidecar — strongest process isolation, delayed/truncated evidence

Use an out-of-process reader when the priority is **zero runtime coupling** rather
than synchronous access to the exact model-facing payload. Read the existing
Hermes event store with SQLite URI `mode=ro`; add `PRAGMA query_only=ON` as a
second logical guard and test that a write probe fails. This seam:

- changes no plugin, backend selection, prompt, schema, response, or V1 process;
- cannot propagate an exception into V1 because it runs after persistence in a
  different process;
- performs no device/backend call and can be disabled independently;
- sees only what was persisted, possibly after delay and after AX truncation;
- does **not** provide the hook's authoritative `duration_ms`; an assistant-message
  timestamp to tool-result timestamp is only a **persisted interval estimate**.

Correlate each tool result by `(session_id, tool_call_id)` with the earlier
assistant `tool_calls`, and advance a cursor by the **result message id**, never
by the call row. Make the replay fail-safe and observable:

1. A completed pair whose arguments/result are permanently malformed may be
   quarantined and skipped; record its result id and continue.
2. A result with no matching call is potentially a persistence race: do not
   advance past it.
3. Distinguish quarantine warnings from blocking replay errors. The one-shot CLI
   must exit non-zero on a blocking error so a timer cannot remain green while
   the cursor is stuck.
4. Catch conversion/classification failures per event and persist an error
   record; do not let one bad capture discard later valid records.

For an idempotent spool, write one private file per result message id with
exclusive creation, then atomically replace the cursor only after record writes.
Never overwrite an existing event during replay. Use private directories/files
(`0700`/`0600`), and run the poller as a separate constrained `Type=oneshot`
service or equivalent scheduler. A no-restart oneshot plus a timer makes each
failure visible without creating an internal retry loop.

Lock the continuous poller's dependency graph with an AST/import-closure test
starting at its CLI. Refuse imports of the live Mac probe, `subprocess`, network
clients/sockets, `CuaDriver`, or `call_tool`; otherwise a future refactor can
silently invalidate the zero-backend-call claim. Pair this with service
confinement: empty capability set, `NoNewPrivileges`, strict read-only system and
home paths, one writable spool directory, private devices, `AF_UNIX` only, and
`UMask=0077`. Keep live discovery/probing as a separate explicit operation that
populates a TTL cache; the timer must only consume persisted V1 data and cache.

#### Evidence and reporting discipline for persisted sidecars

- Report `critical_path_overhead=0` as a topology invariant of the out-of-process
  seam, separately from measured sidecar CPU/compaction latency.
- Treat zero backend/device calls as a structural claim backed by the closed
  import graph, not merely a counter initialized to zero.
- Name `(tool-result timestamp - assistant timestamp)` a **persisted interval**;
  it is neither backend latency nor the hook's authoritative `duration_ms`.
- Use warmups that are excluded from measured samples, and state the percentile
  convention (for example nearest-rank p50/p95 plus min/max).
- Keep unavailable presence/lock/foreground scenarios as `unknown`; never count
  them as passes or satisfied postconditions.
- Report source truncation, compact-output information loss, and ref integrity.
  Refs reconstructed from persisted AX indices are synthetic and non-actionable;
  their native-ref freshness is `unknown`, never `0 loss`. Assess freshness only
  when native `element_token` values were actually persisted and checked.
- Keep raw character counts beside token estimates. A value such as
  `ceil(serialized_chars/4)` is an estimate, not tokenizer output.
- Keep one canonical machine-readable verdict (`passed` plus `failures`, or an
  explicitly documented `gates` object) and verify prose against the **latest**
  generated report after the final run. Do not copy numbers from an earlier run.
- Build shareable evidence through a top-level whitelist so future private fields
  are excluded by default. Strip source call ids, replay ids, probe/context
  objects, local paths, hostnames, IPs, and tailnet identity. Use documentation-
  reserved addresses in fixtures rather than copying a live route.
- Recheck frozen-baseline hashes/tree/plugin files after the benchmark. Exclude
  raw state DBs, AX spools, device caches, hostnames, IPs, tailnet identifiers,
  bytecode, and test caches from the shareable archive.
- Seal only after the final code/doc change: regenerate the manifest from the
  exact bundle, create a deterministic archive, extract it to a clean directory,
  verify every manifest entry, run the full suite from that extraction, and scan
  for exact private markers. Any later edit revokes the candidate hash and
  requires resealing.

#### Independent closure protocol for a sealed shadow artifact

Certification is a separate gate from implementation and local testing. Apply
these rules when declaring a shadow lot CLOSED:

1. **Review the sealed object, not the mutable workspace.** Give the independent
   reviewer the expected archive SHA-256 and the exact clean extraction path.
   Restrict its scope to the machine-readable report, the metric functions, and
   the focused tests needed to recompute the claims. The parent should then
   re-check the archive hash, manifest, full suite, and runtime service state.
2. **Require a terminal structured verdict.** A timeout, iteration-budget exit,
   truncated answer, or transcript containing only partial calculations is not a
   pass. Treat it fail-closed even when no discrepancy was observed. Re-run a
   smaller audit whose mandatory output includes `passed` and `must_fix`; close
   only on `passed=true` and `must_fix=[]`.
3. **Constrain the reviewer by evidence surface, not by optimism.** Prefer a
   compact sanitized report and a deterministic verification script or a few
   bounded commands over asking a reviewer to reread a large state database or
   long documentation. It must not inspect private raw sources when the sealed
   artifact is what is being certified.
4. **Keep denominators explicit.** Distinguish tool actions from usable evidence
   records—for example, `capture` actions, capture results containing an
   `elements` list, and non-empty AX captures are three different counts. Verify
   each against the read-only source and prove the source database's size, mtime,
   and digest are unchanged. Never collapse these counts in prose.
5. **Revoke candidate hashes after any fix.** If a secret scan finds even a live
   route copied into a test fixture, replace it with a documentation-reserved
   value, rerun the full suite, rebuild from the whitelist, extract, verify, and
   publish only the new hash. The earlier candidate hash is no longer final.
6. **Keep certification outside the frozen archive unless resealing is intended.**
   An external certificate can record verdict, architecture, metrics, integrity,
   runtime state, and deferred gaps without changing the certified archive. Hash
   the certificate separately and state explicitly that it is external.
7. **Separate artifact truth from runtime truth.** Archive hash, manifest, tests,
   and sanitized evidence certify the bundle; timer/service health certifies the
   deployed sidecar. Report both, but do not use a healthy timer as evidence that
   the archive is correct—or vice versa.

A useful final certificate records: exact archive hash; manifest/test counts;
independent verdict; V1 and prior-lot integrity; event/quarantine/evidence
counts with definitions; topology and zero-call/zero-mutation gates; percentile
basis; A–H unknowns; policy L0/L1/L2/unknown totals; private-data scan; and the
next lot's explicitly deferred capabilities.

## Three in-process seams, ranked by impact (smallest first)

### 1. `post_tool_call` observer hook — SMALLEST, impact-0, model-facing payload
- Emitted by `_emit_post_tool_call_hook` (model_tools.py:1116-1167, fired ~:1512).
- Payload: `tool_name` (="computer_use"), `args` (request args: action/mode/element/…),
  `result` (**exactly what the model sees**: JSON string with `effect`/`verified`/
  `escalation`, or the AX text payload / `_multimodal` dict with base64 PNG),
  plus `task_id / session_id / tool_call_id / turn_id / api_request_id /
  duration_ms / status / error_type / error_message / middleware_trace`.
- Isolation (double): `invoke_hook` wraps each callback in its own try/except
  (hermes_cli/plugins.py:4619-4662), and `_emit_post_tool_call_hook` wraps the whole
  emit (model_tools.py:1166-1167).
- Zero-cost when off: `has_hook("post_tool_call")` gate skips everything (model_tools.py:1143).
- Proven production surface: the langfuse observability plugin uses exactly this
  (`plugins/observability/langfuse/__init__.py:1074,1136-1137`).
- Register: plugin `ctx.register_hook("post_tool_call", cb)` (hermes_cli/plugins.py:2833).
- **Limitation:** `result` is the serialized / truncated model-facing form (AX `elements`
  capped at `max_elements`, labels capped at 120 chars, tool.py:1058-1062,1596). Good for
  token/effect/outcome metrics; NOT enough if you need the full AX tree.

### 2. `tool_execution` middleware — near-0 impact, in-process, request + raw result
- `run_tool_execution_middleware` (hermes_cli/middleware.py:206-224); payload
  `tool_name / args / original_args / next_call`; `next_call(args)` → raw tool result.
- Fail-open: a middleware callback that raises is logged and the next middleware /
  base path continues (middleware.py:303-314). Different from fail-closed hooks.
- `next_call` is single-use per frame (middleware.py:276-294); a second call is a
  contract violation that raises — never call it twice.
- Register: `ctx.register_middleware("tool_execution", cb)` (plugins.py:3013;
  kinds in middleware.py:29-34). Runs after approval, before post_tool_call.
- **Limitation:** same as hook — sees the serialized result, not internal objects.

### 3. Backend factory wrapper — highest impact, ONLY source of full untruncated AX
- Register a new backend (e.g. `v2shadow`) wrapping the active backend:
  `ctx.register_computer_use_backend("v2shadow", factory)` (plugins.py:1486;
  reserved names `cua|cua-driver|noop`, backend.py:48). Select via
  `computer_use.backend: v2shadow` (read tool.py:477-489).
- Your wrapper's `capture()` → delegate to inner backend → returns `CaptureResult` with
  `elements` (FULL tree: index/role/label/bounds/app/`element_token`) BEFORE
  `_capture_response` truncates. Actions return `ActionResult` with
  `effect/verified/escalation/path/degraded/delivery_mode/code/meta`
  (backend.py:195-233; built by `_action_result_from` cua_backend.py:69-129).
- Record in `try/except` around delegate; never let recording interfere with the return.
- **Pitfall:** backend selection has a hard fail: if the config names `v2shadow` but the
  plugin isn't loaded, `_get_backend` raises `Unknown …BACKEND` (tool.py:278) → V1 BRIEFLY
  BROKEN until rollback config to the old name. This is the only non-zero-impact seam.
  Add a fallback: wrapper factory that lazily constructs the inner backend and, on shadow
  failure, still delegates (so callers get results) — but the config pointer itself is the
  residual risk. Only choose this when you need full AX / uncapped payload.

## Guaranteeing "shadow failure impact on V1 = 0"
- For hooks/middleware: rely on the built-in per-callback try/except + fail-open; do NOT
  add your own try/except that could catch and return wrong, just record inside the
  callback defensively (guard `result` shape, handle non-dict, never raise).
- Never call any cua-driver RPC from the shadow — import only `backend.py` dataclasses, not
  `CuaDriverBackend` (avoid accidental `call_tool`). That's your "no second backend call" proof.
- Do NOT modify `result`, `args`, or return anything from the hook (hooks are observers).

## Available counters / refs / effects you can record without new work
- Effects already normalized on every result: `confirmed|unverifiable|suspected_noop`,
  `verified` bool, `escalation.recommended=px|page|foreground`, `path`, `degraded`,
  `delivery_mode`, `code` (tool.py:870-916). `duration_ms` provided by the hook.
- Snapshot/ref identity: `element_token` per snapshot index (cua_backend.py:2051,
  2654-2663), invalidated on each new capture/window (2467-69, 3171); typed-browser refs
  are latest-snapshot (cua_backend.py:3262). Record them if you re-verify staleness.
- Do NOT repurpose the observability relay counters (hermes_cli/observability/
  shared_metrics_contract.py — `TOOL_CALL_METRIC`, `computer_use` in TOOL_CATEGORIES):
  they are **opt-in outbound telemetry with a FIXED allowlisted schema**; a shadow recorder
  should be its own store keyed by run/session id.
- Do NOT confuse cua-driver's own upstream telemetry knob
  (`CUA_DRIVER_RS_TELEMETRY_ENABLED`, computer_use.cua_telemetry, config_defaults.py:3124-3147)
  with action-level counters — that's a privacy opt-in for the driver binary, unrelated.

## Exact proofs to collect
1. No mutation from the shadow: hook is read-only (observer), no `call_tool`/`_bridge.run`
   anywhere in the shadow plugin.
2. No second backend observation: shadow imports only `tools.computer_use.backend` dataclasses;
   `result`/`CaptureResult` come from V1's own execution.
3. V1 byte-identical: hook never alters `result`; config/backend name unchanged (unless using
   seam 3).
4. Schema/prompt/response unchanged: shadow registers no action
   (`register_computer_use_action`), no `register_system_prompt_section`, no `transform_tool_result`.
5. For capture modes, extract `mode/width/height/total_elements/elements` (AX) or PNG bytes
   (multimodal) straight from `result`; for actions parse `effect/verified/escalation` from the JSON.
6. Pseudonymized run/device id + `session_id` (present in hook payload) → correlate to cache-hit
   / warmup metrics.

Recommendation: hook (1) for the model-facing flow; add wrapper (3) ONLY when a gate needs the
untruncated AX tree (e.g. AX-chars p95 or "0 screenshot/vision in inspect-only" thresholds).
Never combine (1)+(3) redundantly for the same metric — deduplicate.
