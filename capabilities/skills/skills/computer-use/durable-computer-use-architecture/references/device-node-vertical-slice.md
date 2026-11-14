# Device Node vertical-slice guardrails

Use this reference when evolving a durable Computer Use backend into a local
Device Node with remote reachability and bounded administration. It captures
class-level lessons from a live macOS/Tailscale/CuaDriver slice; names,
addresses, versions, and credentials are intentionally omitted.

## 1. Audit both code and deployed reality

A repository audit and an operational-infrastructure audit answer different
questions. Before declaring a transport, gateway, or remote-control plane
absent:

1. Inspect the implementation boundary in the current repository/plugin.
2. Inspect the deployed route separately: live Tailscale peers, SSH reachability,
   wrapper/service configuration, and the target-side daemon.
3. State both conclusions explicitly.

A correct conclusion may be: **remote Tailscale/SSH connectivity already works
for one Mac, but it has not yet been productized as a generic Device Node
session gateway**. Never turn “not represented in this repo” into “does not
exist in the system.”

Safe read-only target preflight:

```bash
tailscale status --json
ssh -o BatchMode=yes -o ConnectTimeout=8 <mac-user>@<tailnet-ip> \
  'sw_vers; id -u; launchctl print gui/$(id -u) >/dev/null && echo GUI_LAUNCHD=ok'
```

Then validate the target-side driver without opening permission UI:

```bash
cua-driver status
cua-driver permissions status --json
cua-driver call health_report '{}'
cua-driver call list_windows '{}'
```

Tailscale authenticates network peers; it does not authorize actions. Keep
network identity, task capability grants, OS privilege, and UI permission
identity as separate verdicts.

## 2. Keep the control planes separate

```text
Hermes planner
  -> service-gated facade or CLI
  -> authenticated Node client
  -> local Node socket / named pipe
  -> capability registry + policy + operation journal
  -> user-scoped OS adapter OR separate privilege broker
  -> CuaDriver only for UI/AX/input/capture
```

The Node should bind locally. Remote access should forward or invoke that local
contract through Tailscale/SSH; do not expose a privileged daemon directly on
the LAN or tailnet merely because the overlay network is private.

Keep CuaDriver as the proven low-level UI adapter. Do not reimplement Hermes'
approvals, target normalization, multimodal payload shaping, or fresh-snapshot
rules in the Node.

## 3. Idempotency and restart safety

For every mutation:

- bind the idempotency key to session, task, capability, and canonical argument
  digest;
- reject reuse with different semantics as a collision;
- use restart-safe operation IDs (random/UUID or a counter initialized from the
  database), never an in-memory counter that resets;
- persist terminal status **and** the replayable result atomically;
- treat unknown completion as terminal and never replay automatically;
- reconcile queued/dispatching operations after restart before accepting a
  retry.

An audit chain records several lifecycle events for the same operation. Do not
make `operation_id` unique in the audit-event table. Secure SQLite databases and
HMAC keys with owner-only permissions; reject symbolic links and multiple hard
links; require a trusted, non-writable parent; and pre-create new databases with
mode `0600` before SQLite opens them. Revalidate the main file after opening and
lock down `-wal`/`-shm` sidecars as well — chmodding only the nominal `.db` file
leaves the live journal readable. Apply the same boundary to approval and
idempotency stores, not only the audit database. Document that HMAC evidence is
only as strong as protection of the signing key. A hash chain alone does not
prove that its tail was not truncated; use an external checkpoint/head when
that threat matters.

## 4. Privilege Broker means authority, not “run everything as root”

A one-shot grant should bind:

- grant ID;
- session ID;
- task ID;
- exact capability;
- canonical argument digest;
- expiry and consumed state.

Consume it atomically. A mismatch, replay, expiry, unknown capability, or policy
version mismatch fails closed.

Do not expose grant issuance on the same RPC socket the Node can call. Mint the
grant only through an out-of-band local operator path (for example, a Broker
CLI reading one private regular request file), audit approval intent before
issuance, and return the grant to the operator for one explicit submission.
Keep privileged Broker state in a root-owned `0700` directory, but place its
`0600` dispatch socket in a separate user-owned runtime directory and chown the
socket to the authorized Node UID. Socket reachability must not imply access to
the approval database or signing key.

Separate authorization from execution identity. Some elevated-risk actions are
still user-scoped: for example, Homebrew must not be run as root. The broker may
authorize a user-scoped action while reserving root execution for capabilities
that genuinely require it. A privileged executor must reject user-owned or
group/other-writable executables **and their parent directories**, even when the
path appears on an allow-list; otherwise a root broker merely blesses mutable
user code. Never accept arbitrary executable paths, argv, shell snippets, or
environment variables over the Node/Broker protocol.

## 5. CuaDriver integration lessons

- Force telemetry off unless the user explicitly opted in.
- CuaDriver may intentionally refuse operations against its own authorization
  process. Treat that as a safety boundary and choose another exact window.
- `permissions status` proves TCC state, not capture integrity.
- CLI/MCP response envelopes vary. Raw `get_window_state` output through a
  bridge may not behave like a strict standalone JSON document. Reuse Hermes'
  existing long-lived MCP/stdio bridge and response normalizer instead of
  adding an ad-hoc parser or one SSH process per action.
- Validate a harmless exact target with fresh `(pid, window_id)`, AX state, and
  capture-integrity fields before any mutation. Do not persist private window
  titles or screenshots in test artifacts.

## 6. Promotion gates

Promote a macOS slice only after all of these are real:

1. deterministic unit tests for contracts, policy, adapters, idempotency,
   approvals, and audit tamper detection;
2. a local socket integration test with restrictive permissions;
3. restart/replay and unknown-completion tests;
4. direct Tailscale/SSH target preflight;
5. target-side Cua health, AX read, and valid capture evidence;
6. one harmless idempotent action with a domain postcondition;
7. tunnel-loss and daemon-restart behavior;
8. audit verification after the final action;
9. no automatic retry through a second driver after uncertain mutation.

Label untested adapters as contract-tested, not live-supported. Cross-platform
class names are not evidence of cross-platform behavior — an old favorite of
software architecture, along with diagrams that compile flawlessly.

## 7. Separate contract support from live authorization

A typed adapter and green contract tests are not enough to authorize execution
on that platform. Keep two explicit platform sets per capability:

- **contract support** — argument validation and command compilation are tested;
- **live support** — the complete deployed path, privilege identity, policy,
  execution, and postcondition verification have passed on a real device.

The policy engine must receive the current platform and reject a capability
whose platform is not in `live_support`, even if an adapter class exists. The
capability registry should expose both sets plus current availability so the
planner cannot infer production support from a module name. High/prohibited
risk checks remain fail-closed independently of platform support.

Bound every untrusted request before hashing or persistence: reject unknown
fields, control characters, non-finite numbers, excessive nesting/node counts,
oversized strings/JSON, and mutable non-JSON values. Reparse even an internal
dataclass at the Broker boundary; frozen Python objects are not a protocol
security boundary.

## 8. Harden local IPC as a security boundary

The Node and Broker should expose bounded JSON-RPC over Unix sockets (or the
native Windows equivalent), never a listening TCP port by default. Required
properties:

- validate the parent and socket path with `lstat`; reject symlinks and regular
  files rather than unlinking them;
- create owner-only directories and socket mode `0600`;
- authenticate peers from kernel credentials (`SO_PEERCRED`/`getpeereid`), not
  `uid` fields supplied in JSON;
- cap frame size and connection concurrency, process blocking work off the
  event loop, and return no traceback;
- validate response IDs and exactly-one-of `result`/`error` on clients;
- when a root Broker serves a user Node, distinguish socket-file ownership from
  connected-server UID: a user-owned `0600` socket can still terminate in a
  root-owned Broker process whose peer identity the client verifies.

On shutdown, unlink only the same owned socket inode; never remove a path that
was replaced while the daemon was running. On startup, verify the audit chain
before recovering operations or accepting requests.

## 9. Preserve uncertainty across Broker and audit failures

The safe lifecycle is:

```text
QUEUED -> DISPATCHING -> SUCCEEDED | FAILED | REFUSED | UNKNOWN
```

`QUEUED` means no adapter command was handed off and may be claimed safely.
A process restart with `DISPATCHING` must become terminal `UNKNOWN`; it must not
be replayed automatically. Persist the terminal result atomically with status
so idempotent callers receive the same evidence after restart.

Consume the one-shot approval only after peer, schema, policy, platform, and
adapter-plan validation. Append a dispatch audit entry before execution. If
that pre-dispatch audit fails, deny without executing. If the final audit write
fails **after** the executor was called, never translate the error into
`REFUSED`, `audit_unavailable`, or `suspected_noop`: dispatch occurred. Preserve
the real executor outcome when completion is known, return the partial dispatch
audit IDs, and mark `audit_complete=false`. Use terminal `UNKNOWN` only when the
transport/executor genuinely cannot prove completion. This distinction avoids
both false no-op replay and destruction of a known execution result.

Audit events are append-only lifecycle records; several rows may share one
operation ID. Keep raw arguments, stdout/stderr, screenshots, window titles,
and secrets out of the chain. Record normalized capability, request/task
identity, argument digest, delivery/completion flags, verifier verdict, and
bounded codes.

## 10. Long-lived stdio and StreamLocal transports

For remote CuaDriver, keep one MCP stdio process and one SSH channel alive.
Serialize requests, correlate JSON-RPC IDs, drain stderr, cap frames, and mark
the session tainted when the channel dies after a request was sent. Do not
restart and replay a mutation automatically; require an explicit restart and a
fresh state/idempotency decision. Normalize direct and `structuredContent`
response envelopes while preserving explicit empty AX lists and capture-error
fields.

A local executable shim can let Hermes' existing CuaDriver backend spawn the
remote stdio process without adding another model tool. Treat its discovery
contract carefully:

- the remote `manifest` may publish an absolute `mcp_invocation.command` that is
  valid only on the target OS; if relayed unchanged, the host may try to execute
  that macOS/Windows path locally;
- rewrite only `mcp_invocation.command` to an empty or generic command so the
  host retains the already-validated local shim, while preserving the remote
  manifest's authoritative `args`;
- keep the user-facing shim path in plugin `config.yaml`; translating it to an
  internal compatibility environment variable inside the plugin is acceptable,
  but do not make the environment variable the public configuration surface;
- validate the shim and SSH config as single-link regular files with trusted
  owners and non-writable parents; bound config and argv before spawning;
- remember that OpenSSH serializes the remote command through a remote shell
  even when the local subprocess uses `shell=False`: allowlist subcommands and
  shell-quote every remote argument, including CLI-fallback JSON;
- test three layers: rewritten manifest behavior, plugin/backend resolution,
  and a real `start()` plus harmless remote `list_windows()` call. A wrapper
  that can run `manifest` alone is not yet an end-to-end transport proof.

For remote Node access, prefer persistent OpenSSH StreamLocal forwarding:

```text
local owner-only Unix socket -> SSH over tailnet -> remote owner-only Node socket
```

Use strict host-key checking, an explicit identity, `BatchMode=yes`,
`ExitOnForwardFailure=yes`, a private StreamLocal bind mask, and `-F /dev/null`
when user SSH configuration must not inject forwards or commands. Sanitize the
child environment and never bind `0.0.0.0`. Be cautious with
`ClearAllForwardings=yes`: depending on option processing it can also cancel the
intentional `-L` forward; ignoring ambient config and declaring the single
forward explicitly is easier to verify.

## 11. Verify the shipped artifact, not only imported modules

A green library suite does not prove that declared daemons or clients are
runnable. For every console script declared by the package manifest:

1. write a behavior test that imports its production entrypoint;
2. build both wheel and source distribution;
3. install the wheel into a fresh virtual environment;
4. run `--help` (or an equivalent local no-config probe) on every command;
5. start the packaged Node against a temporary owner-only socket and make one
   real client RPC such as capability enumeration;
6. exercise every advertised lifecycle feature through the packaged client and
   daemon, especially session recovery/resume rather than only its storage
   helper;
7. compare README/runbook command names and flags against the actual parser;
8. when development tools live in a package dependency group, use the package
   manager's group-aware sync/install command before claiming the documented
   test commands work in a clean checkout.

Do not stop at “the function exists.” A remote compatibility shim also needs a
local help path that does not require credentials, while operational verbs stay
allow-listed. When two agents edit the same tree concurrently, rerun the full
suite and re-read modified files before accepting an audit conclusion; a
read-only reviewer may otherwise report a file as missing while another worker
is creating it.

## 12. Audit complete lifecycle and disclosure paths

A feature advertised as durable or resumable is one end-to-end contract, not a
set of suggestive nouns. For session resume, verify all of these layers:

```text
installed client parser
  -> exact bounded session.resume request
  -> daemon method dispatch
  -> durable session-scoped store query
  -> stable replayable operation payloads
```

Test an existing session, an absent session (empty result), malformed/control
character IDs, and unknown extra fields. A client-only test can pass while the
live daemon returns `method_not_found`; a store helper can exist while no RPC
exposes it. Include one real Unix-socket round trip from a freshly installed
wheel so these partial implementations cannot masquerade as recovery support.

Error sanitization also has more than one channel. Sanitizing JSON-RPC error
objects is insufficient when expected executor failures are converted into a
nominal result envelope whose `stderr` still contains `str(exc)`. Audit both:

- protocol errors and unexpected exceptions returned by the RPC server;
- execution/result payloads returned after `ExecutionDenied`, `OSError`, or a
  broker boundary failure.

Use fixed bounded machine codes/messages such as `dispatch_denied`; keep local
paths and raw exception text in local logs only. Add a behavior test whose fake
executor raises an exception containing a sentinel private path, then assert the
public result contains neither the sentinel nor the original exception text.
