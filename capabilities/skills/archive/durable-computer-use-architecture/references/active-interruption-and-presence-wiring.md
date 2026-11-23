# Active interruption policy + presence TTL wiring (shadow → active)

How the passive/shadow contracts become **enforcing** runtime policy in the
Walter Operator plugin, and the pitfalls hit while making them active.
Derived from the Lot 2.3 "active wiring" pass over
`deploy/walter-computer-use-lot23/` and `adaptive_operator/`.

## The core architectural split (why it matters)

`adaptive_operator/` holds the *shadow* contracts — `device_context.py`
(`DeviceActivity`, `DeviceContextStore`, `DeviceContextResolver`),
`macos_shadow.py` (`MacPresenceProbe`, `CachedMacPresence`,
`FixedSshMacProbeRunner`), `interruption.py` (`InterruptionGate`,
`RuntimeEvidenceLedger`, `ActionEffects`, `InterruptionLevel`). These are
non-enforcing: they classify/observe but never block or authorize.

The *active* runtime lives in the deployable plugin as a **self-contained**
module (`deploy/walter-computer-use-lot23/runtime.py`) that deliberately does
**not** `import adaptive_operator`. Reason: the plugin is loaded from
`HERMES_HOME` via `importlib` at Hermes runtime, where the repo root is **not**
on `sys.path`. Depending on repo modules from the plugin would break in
production even though `tests/` can import them (pytest puts the repo root on
`sys.path`). The active adapter is a small copy of the effect/level logic +
a dedicated presence + policy implementation. Keep these two copies in sync
deliberately, and keep the active one self-contained.

The plugin mounts the runtime via a loader identical to the observer's
(`_load_runtime_module()`, cached in `sys.modules` under
`_walter_operator_macos_runtime`), so the same `runtime.py` is shared across
all plugin module aliases in tests.

## Presence TTL wiring

- `UserPresence.from_mapping(raw, *, observed_at, source, confidence)`
  normalises `screen_locked`, `desktop_unlocked` (inferred as `not
  screen_locked` when absent), `foreground_app`, `foreground_window`,
  `idle_duration` (from `idle_ns`/1e9 or `idle_duration`), recent input
  flags, and derives `user_active` (locked→False; explicit→that; recent
  input→True; else `idle < threshold` default 30s; else None). `compact()`
  emits the 7 presence keys + `observation_timestamp`, `confidence`, `source`
  — this is what the router attaches to results as `user_presence`.
- `UserPresenceCache(probe=..., ttl_seconds=...)` is the TTL: `resolve(now)`
  returns the cached object when `now - cached.observation_timestamp <= ttl`,
  else calls `probe()`; **any probe exception → `UserPresence.unknown()`**
  (source `"unavailable"`, all-None → never blocks the caller).
- `FixedSshMacPresenceProbe` runs one constant read-only SSH batch (idle,
  `lsappinfo front`, screen-locked via
  `ioreg -n Root ... CGSSessionScreenIsLocked`). The plugin backend builds
  `self.presence = UserPresenceCache(FixedSshMacPresenceProbe(config_path=
  os.environ.get("WALTER_REMOTE_CUA_CONFIG", "/root/.config/.../remote-cua.json"),
  now=time.time, foreground_window=self._foreground_window_title), ttl_seconds=
  15.0)`.
- Router resolves presence once per `execute`: `resolver = self.presence or
  getattr(backend, "presence", None)`; wrapped in try/except → unknown on
  failure. Verify with a test that two `execute` calls within TTL run the
  probe exactly once and return byte-identical `compact()` dicts.

## Interruption policy matrix (`InterruptionPolicy.evaluate(effects, *, presence, origin, confirmation_granted)`)

`ActionEffects.level` → "L2" if destructive/unsaved/sensitive/irreversible/
restart, "L1" if visible_ui/focus_change/pointer/keyboard/desktop_change,
else "L0". `origin ∈ {FOREGROUND_USER, AUTONOMOUS}` (StrEnum).

| Origin | Level | Presence | Outcome |
|---|---|---|---|
| either | L0 | any | allowed, no warn/confirm |
| either | L2 | any | **needs_confirmation** unless `confirmation_granted`; reason `l2_confirmation_required` |
| any | L1 | locked / desktop locked | refused, `screen_locked_visible_action_refused` |
| AUTONOMOUS | L1 | user_active True | **defer** (`allowed=False`, `defer=True`), `user_active_interference` |
| FOREGROUND_USER | L1 | any | **allowed** (no confirmation); `warning_required=user_active` |
| AUTONOMOUS | L1 | presence None / unknown | **allowed** (fail-open — see pitfall) |

Requirement mapping: "L1 explicit foreground user goal acts without
confirmation" = FOREGROUND_USER row; "active user only warns/defer for
autonomous background" = AUTONOMOUS+active row; "L2 always needs
confirmation" = L2 row. Router default `origin=FOREGROUND_USER` (the single
`goal` action is a user goal), so AUTONOMOUS is only reachable via an
explicit origin injection today.

Router gating: `execute()` first handles an L2 path, else resolves presence
+ effects (visible_ui for any app goal, read_only for no-app), runs the
policy, and **if `not decision.allowed` returns before any device RPC** with
status `deferred`/`refused`/`needs_confirmation` and `metrics.device_rpc=0`.
It always stamps `result["user_presence"]` and `result["interruption"]`
(`InterruptionDecision.compact()`).

## TDD technique: the failing test IS the spec

Before designing, run the suite and look for a committed test that already
fails — it pins the intended API. Here `tests/test_macos_completion_presence.py`
specified the entire `runtime.py` contract (method names, field names,
`compact()` dict shape, decision fields `.level/.allowed/.warning_required/
.defer/.needs_confirmation/.reason`) before any of it was wired. When a new
feature has a red test, read it first; it is the acceptance contract the
implementation must satisfy, often more precisely than prose requirements.

## Pitfalls (verified)

1. **Actively-mutated shared worktree.** The working tree was untracked
   (`?? deploy/...`) and being written concurrently: `__init__.py` changed
   length between reads (1233→1372 lines), and the full suite oscillated
   `158 passed` → `7 failed` across runs with no edits from this session.
   Root-cause by **file version skew**, not by assuming your own logic broke:
   a fresh `read_file` of the current content resolves it. Before declaring a
   lot "active/closed", commit the deploy dir to freeze a canonical version
   and re-run `pytest` from a clean interpreter several times.
2. **Presence probe sits on the goal hot path.** `resolve()` runs a
   synchronous SSH subprocess (`connect_timeout+4`) on TTL expiry, so the
   first goal after idle can stall seconds. Exceptions are caught → unknown,
   but slow *successes* still block. Keep the probe low-frequency and bounded;
   don't promise zero-latency goals once TTL lapses.
3. **Screen-locked guard is only as reliable as the probe.** Probe failure →
   `unknown()` with `screen_locked=None` → FOREGROUND L1 is **not** blocked
   (fail-open). The policy ignores the `confidence` field. If a locked-but-
   unknown screen must refuse visible foreground actions, add that branch or
   surface low confidence; today the guard silently allows through on probe
   outage. Decide and document the intended fail-open/fail-closed contract.
4. **AUTONOMOUS + unknown presence is fail-open.** `collision = active is
   True`; `user_active=None` → autonomous L1 proceeds. The shadow
   `InterruptionGate` instead requires a warning receipt (fail-closed). Pick
   one intent: if "defer autonomous while the user may be active", unknown
   must defer for AUTONOMOUS.
5. **L2 is still prose-derived, not route-derived.** `execute` gates L2 via
   the `_is_l2_goal` regex building `ActionEffects(destructive=True)`. Because
   prose here only ever *escalates* (blocks), it is fail-safe and does not
   violate the no-prose-authorization invariant — but it misses unlisted
   destructive wording (e.g. `close`/`quit`/`ferme`), which then runs as an
   allowed FOREGROUND L1. This is an explicit backlog item; do not silently
   "fix" it while the lot is closed.
6. **TTL hardcoded** at 15.0s in the backend constructor (not env/config-
   tunable) while the probe path is env-tunable. Make TTL tunable
   (`WALTER_PRESENCE_TTL` or `computer_use.walter.presence.ttl`) for
   production.
7. **Metrics undercount.** The probe SSH call and `_foreground_window_title`'s
   `list_windows()` are not counted in the goal `metrics.device_rpc`; the
   `user_presence` payload carries no probe-cost field. If device-call
   accounting matters (it does, per the lot-2.2 benchmarks), attribute these.
8. **Test-coverage gap.** Presence tests inject `presence=cache` directly.
   Add production-wiring tests: construct a real `WalterCuaBackend()` and
   assert it builds a presence probe against a canned config (monkeypatched
   env), and that a missing-default-config path degrades to unknown without
   raising. New backend-instantiation tests must supply a config because
   `__init__` unconditionally builds the probe (existing tests use
   `object.__new__(...)` to bypass, or monkeypatch `__init__`).
