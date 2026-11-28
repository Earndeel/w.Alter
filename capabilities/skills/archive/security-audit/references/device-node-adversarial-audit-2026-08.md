# Adversarial audit of a hardened Unix-socket control plane (W.Alter Device Node)

Companion to `device-node-e2e-review-2026-08.md` (deployability) and
`subprocess-executor-hardening.md` (implementation). This pass re-audits the
**final hardened state** after concurrent changes and asks "does the hardening
actually hold in the shipped wiring?" — read-only, adversarial. Result: every
security control held; one regression surfaced via the test suite.

Reusable proof checklist — for each control, state the *specific* code evidence
that it holds (not "looks ok"):

## 1. Grant/approval binding — verify the digest is RECOMPUTED, not client-supplied
The one-shot grant is bound to `(session_id, task_id, capability, arguments_digest)`.
The classic flaw is trusting a client-supplied digest, letting the caller swap
actual arguments under a grant approved for a different digest. Proof:
- The request contract has NO client-supplied `arguments_digest` field — unknown
  fields are rejected (`OperationRequest.from_dict`, unknown-field check). The
  digest is a **property computed over `self.arguments`** (canonical sorted JSON
  → sha256). At consumption the broker compares the *recomputed* digest of the
  *actual* arguments against the stored grant. Different args ⇒ different digest ⇒
  `approval_denied`.
- Confirm there is **no grant-issuance RPC** on any socket (issuance is a local
  CLI only) — otherwise a reachable peer could mint its own grants.

## 2. Peer identity — kernel, never the request body
- Authoritative server derives uid/gid/pid from `SO_PEERCRED` / `getpeereid()` at
  the socket layer (`server.py`), then applies the peer authorizer.
- Client facades must NOT forward a `peer` param to the wire. Here
  `BrokerSocketClient.execute(peer=...)` accepts the arg but never uses it
  (`client.py` ~:171) — the broker re-derives the peer from the socket. A spoofing
  attempt is dead on arrival; that's what you want to see.

## 3. Unix socket ownership
Verify the server: binds first, then `chown(path, peer_uid, peer_gid)`, then
`chmod 0600`, `O_NOFOLLOW`, refuses symlink/stale non-socket, and validates the
parent (real dir, owner in `{server euid, owner_uid}`, no group/other bits, must
not traverse symlinks). Stale-socket unlink only when `(st_dev, st_ino)` matches
the bound socket (avoids unlinking a replaced path). For a root broker exposing a
dispatch socket to an unprivileged node: socket chowned to the node UID + 0600 in a
node-owned 0700 runtime dir — correct, since only the authorized node peer connects.

## 4. RPC error sanitization — check BOTH channels
- **Error channel** (JSON-RPC error): generic handler emits only
  `str(getattr(exc, "code", "internal_error"))` — a fixed safe code string, never
  `str(exc)`. Protocol/parse errors use fixed messages. No path/exception text.
- **Result channel** (the trap): on dispatch denial (`ExecutionDenied`/`OSError`)
  the code sets `ExecutionResult.stderr = str(exc)[:500]` — reflecting local paths
  and raw exception text back to the caller in the **result**, not the error.
  Same-trust-domain so P2/info-leak, not exploitable, but exceeds the stated "no
  paths or exception text" control. Fix: return a fixed message on the denial path.
  Audit both channels, not just the error response.

## 5. Subprocess TOCTOU / env — hold, don't re-derive
Already hardened (see subprocess-executor-hardening.md); re-check the shipped
executor instance: O_NOFOLLOW fd-pin + identity re-check before `subprocess.run`,
refusal of privilege-escalation bitfiles, refusal of group/other-writable file AND
parent, owner in `{0, euid}`, forced safe fixed PATH (never inherited), env
restricted to an allowlist, plan env restricted to a telemetry key. Confirm the
residual pre-`execve` race (between the final re-stat and the kernel's own open of
the path) is explicitly documented as irreducible from Python — an accepted
residual, not a bug.

## 6. SSH remote-driver manifest rewrite
Confirm: manifest size/shape validated; `command` cleared (so the local host never
executes the remote absolute binary path); `args` preserved but bounded (≤N args,
each ≤N bytes, no control chars); and the assembled remote argv is `shlex.quote`d on
a FIXED ssh argv (identity, BatchMode, StrictHostKeyChecking=yes, pinned known-hosts,
bounded ConnectTimeout) so manifest args can never be interpreted as ssh options.

## 7. Fail-closed-unavailable vs vulnerability — the classification rule
- A capability that exists in policy but is **refused at runtime for a reason**
  (e.g. a root broker refusing a user-owned Homebrew binary) is an **intended
  fail-closed unavailable feature**, not a vuln. Report as intended.
- A documented/tested feature that is **entirely absent from source** is a
  **regression**. Signal: run the test suite — if exactly one test fails and it
  asserts a CLI subcommand + RPC method absent from the tree while the README still
  advertises the feature, and the CLI subcommand list was NOT updated, that is a
  dropped-feature/stale-test regression (P1, production blocking), not a flaky test.
  mtime across the change window helps: a test file written AFTER the parser that
  still references a removed subcommand confirms the drift. Note argparse raises an
  uncaught `SystemExit(2)` on the invalid choice (nice-to-fix: catch it for a clean
  error).

## Practical flow that worked
1. `ls -la && find src tests` to map modules; read `docs/security.md` (the project's
   own threat model) FIRST — audit against its stated controls.
2. Read core modules in dependency order (protocol/server, contracts/policy,
   broker/approvals, executor, remote_driver, ssh_tunnel, cli) — grants and peer
   identity span several files; trace them together.
3. Run the suite early: `.venv/bin/pytest -q` — the 1 failing test is the highest
   signal-to-noise finding in the whole audit and drives the P1.
4. Re-verify each of the 6 controls with concrete file:line evidence; report each as
   verified-solid, so the report is a *proof* audit, not a suspicion sweep.
