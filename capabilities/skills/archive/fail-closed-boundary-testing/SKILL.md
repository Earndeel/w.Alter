---
name: fail-closed-boundary-testing
description: Test fail-closed authorization/audit boundaries.
---

# Fail-Closed Boundary Testing

For services that enforce a security boundary (privilege broker, one-shot
approval store, hash-chained audit trail). The core correctness property is
fail-safe: **an operation must never run (or be reported) in a way the
enforcement layer cannot account for.** The common bug class: a failure on a
*post-execution* side channel (writing the closing audit entry, confirming
telemetry) gets surfaced with the same "denied BEFORE dispatch" error the layer
uses for genuine pre-dispatch refusals — misreporting work that actually ran.

## The two-phase boundary model

Model every enforced operation as two phases with different failure semantics:

1. **Pre-dispatch phase** (validation: peer, policy, schema, approval grant,
   adapter plan, recording the *dispatch*/intent audit entry). Fail-closed here
   is correct: raise the denial exception, do NOT run anything. State
   mutations made before the denial point (e.g. consuming a one-shot grant) are
   intentional and should be asserted, not "rolled back".
2. **Post-dispatch phase** (the adapter/executor ran, then a *closing* entry is
   recorded). Fail-closed here is WRONG. The side effect already happened (or
   was attempted). The correct semantics: return the real execution outcome
   (succeeded / failed / unknown) so the caller is never told a
   pre-dispatch denial occurred, and signal the audit gap separately.

Design rule that makes this testable: keep the two audit/telemetry writes on
opposite sides of the executor call, and give pre-dispatch writes their own
fail-closed path while post-dispatch writes are wrapped to degrade to
"outcome + `audit_complete=False` + partial trail" instead of re-raising the
denial exception.

## Test-double pattern: fail-after-N-calls

To exercise *exactly* the post-dispatch branch you need an audit/telemetry
writer that succeeds for the dispatch write but fails on the closing write. A
simple `BrokenAudit` that fails every call only proves the pre-dispatch gate.
Use a counter wrapper:

```python
class FlakyAudit:
    def __init__(self, chain, *, fail_after):
        self._chain = chain          # real AuditChain so valid entries return
        self._fail_after = fail_after
        self.count = 0
    def append(self, operation_id, payload):
        self.count += 1
        if self.count > self._fail_after:
            raise RuntimeError("audit write failed after dispatch")
        return self._chain.append(operation_id, payload)
```

`fail_after=1` → first (dispatch) write lands, second (closing) write raises →
you genuinely reached the post-dispatch path. Assert the real outcome is
returned (status, returncode), `audit_complete is False`, the audit trail
contains only the dispatched entry, the executor DID run, and the grant is
consumed.

## Staying in scope: optional-field-on-dataclass

When a task constrains you to modify only a subset of files (e.g. impl + its
test) but the returned object type is constructed elsewhere, add any new field
with a default:

```python
@dataclass(frozen=True)
class BrokerExecution:
    status: OperationStatus
    execution: ExecutionResult
    audit_ids: tuple[str, ...]
    audit_complete: bool = True   # default → other construction sites keep working
```

Never add a required positional/keyword field to a shared result type you are
forbidden from updating at all call sites — it will break import/collection.
A defaulted field is backward compatible.

## Strict TDD sequence for this class

1. Write the failing post-dispatch test FIRST (real chain + `fail_after=1`).
2. Run it against current code — confirm it fails by raising the pre-dispatch
   denial exception (RED).
3. Fix: wrap only the post-dispatch write; keep the pre-dispatch write fail-closed.
4. Run the new test (GREEN), then the FULL suite — guard against the defaulted
   field or behavior change silently breaking other construction/consumption sites.
5. Also write the inverse pair for the *failed* and *uncertain/unknown* execution
   outcomes (returncode nonzero → FAILED, timed_out/unknown → UNKNOWN), all with
   the closing entry failing, so every status path preserves its true outcome.

## Fail-closed CLI / daemon entrypoints

The same boundary concept applies one layer up: the console-script entrypoints
(`node_main` / `broker_main` daemons, `client_main` CLI) that wire the enforced
services. Their correctness property: an unsafe configuration must be rejected
**before any socket is bound or any execution is possible**. Reusable patterns:

- **Centralize validation.** One `validate_<x>_config(cfg)` raising a single
  `ConfigError`; every `*_main` wraps it in `try/except ConfigError` and returns
  exit code 1 (message to stderr) instead of raising. Tests assert the validator
  directly **and** the exit-code contract through the entrypoint.
- **Do NOT put `choices=` on argparse options when you need custom fail-closed
  handling.** argparse validates choices and calls `sys.exit(2)` (`SystemExit`)
  *before* your `ConfigError` path runs, breaking the "return 1 + message"
  contract and any test that asserts on it. Validate the value (e.g. platform)
  inside `validate_<x>_config` instead, so the unknown value reaches your
  handler and the exit code/message is under your control.
- **`--check` mode proves startup wiring without binding a long-running
  server.** Have it build the FULL service graph (store, audit chain, policy,
  adapter, executor, peer authorizer) but not bind the socket. Tests assert
  `--check` → 0 for valid config, 1 + message for invalid. This surfaces
  fail-closed wiring errors in CI without hanging on `serve_forever`.
- **Validate before bind, matching the underlying server's own guards.** The
  Unix-socket server fails closed on: socket path must be absolute and ≤100
  bytes; socket parent must be a real dir owned by the current user and be
  **0o700** (a `mkdir -p`-created dir is 0o755 → daemon refuses with "socket
  parent permissions are too broad"); socket path must not be a symlink / must
  not replace a non-socket. Mirror these in the validator so daemons fail fast
  and tests cover them. Note tmp_path can exceed 100 bytes — keep socket
  filenames short in tests, and `chmod 700` the state dir.
- **Test the daemon without a blocking loop.** Expose
  `async def start_<x>_server(config) -> UnixRpcServer`; an async test does
  `server = await start_*_server(cfg)` then drives the SYNC client via
  `await asyncio.to_thread(client.call, method, params)` (the server handler
  runs in a thread). Assert the socket is unlinked after `await server.close()`.
- **Client entrypoint fails closed too.** Wrap the RPC call in
  `except (ClientProtocolError, RpcRemoteError, ConnectionError, ValueError, OSError)`,
  print `error: …` to stderr, return 1 — never a traceback. Tests assert rc==1
  on an unreachable daemon and on a remote error (`invalid_params` etc.).

Pitfalls specific to this layer:

- **Dataclass-kwargs config build.** Building a frozen `@dataclass` config from
  an argparse Namespace: every required field (e.g. `device_id`) must actually
  be present in the kwargs dict. A missing key surfaces as a confusing
  "<Config>.__init__() missing N required positional argument" at *construction*
  time, not in validation — easy to misdiagnose. Add the key unconditionally and
  pop it only for the config class that doesn't have it.
- **Server fail-closed guards bite the smoke test too.** When you start the real
  daemon to demo, create the state dir with the correct owner-only mode; a
  permissive parent makes the daemon refuse at startup (correctly), which reads
  like a daemon bug if you don't recognise the guard.
- **`--check` should still build the service graph**, not just validate the
  flat config — that catches adapter/platform mismatch and audit/store init
  problems that pure validation misses. See
  `references/cli-daemon-entrypoint-patterns.md` for the walter-device-node
  specifics (module map, console scripts, run commands).

## Pitfalls

- Confusing "pre-dispatch denial" with "post-dispatch failure". Test the exact
  boundary with a fail-after-N double; don't rely on a universally-broken fake.
- Forgetting the pre-dispatch failure test still exists and must keep failing
  closed (grant consumed, no dispatch) — don't weaken it while softening the
  post-dispatch path.
- Adding a required field to a shared result type under a constrained-modify
  scope. Default it.
- Not asserting the executor actually ran in the post-dispatch test — that's
  what proves the outcome is real, not a denial.
