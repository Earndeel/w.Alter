# Wiring-vs-seam audit: W.Alter Device Node (/root/walter-computer-use)

Third pass in the device-node series, after `device-node-e2e-review-2026-08.md`
(deployability) and `device-node-adversarial-audit-2026-08.md` (hardening holds?).
This pass ran **after** the previous P1 regression was fixed: suite is now
**335 items green / 297 test functions** (verified read-only:
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider`; no `.git` in tree).

The audit's highest-value output was the **executable vs. interface/source-seam vs.
dead-end-wiring** classification. All security controls held; the findings that
mattered were about *reachability*, not *correctness*.

## The three buckets (reusable classification)

1. **Executable** — reachable from a console entrypoint. Here: `walter-node`
   (`cli.py:437`), `walter-broker` (`cli.py:566`), `walterctl` (`cli.py:687`),
   `walter-cua-remote` (`remote_driver.py:266`) — wired via `pyproject.toml:11-15`,
   no runtime deps (`pyproject.toml:9`). The live remote-Computer-Use route is the
   shim (`execv`-to-ssh, `remote_driver.py:302` + manifest rewrite `229-263`).
2. **Interface/source seam** — defined + unit-tested, but *never constructed by any
   daemon/CLI*. Evidence: `grep -rn "<ClassName>" src` shows only the definition and
   cross-imports; construction happens only in `tests/`.
   - `cua_transport.McpStdioSession`/`SshMcpConfig` — second, parallel SSH/MCP design;
     only import is `macos_verifier.py:10` (for `normalize_cua_result`). Not the live path.
   - `ssh_tunnel.SshUnixTunnel/SshTunnelConfig` — no production caller; StreamLocal
     Unix-socket forwarding is NOT how Hermes reaches the Mac.
   - `adapters/cua.py`, `adapters/windows.py`, `adapters/android.py` — not in
     `_SUPPORTED_ADAPTERS` (`cli.py:151-154`), so unselectable.
   - `store.recover_dispatching` (`store.py:473`) — tests only; Node inlines its own
     equivalent (`node.py:391-414`).
3. **Dead-end wiring** — reachable but authorizer-denied:
   - **Linux node**: `LinuxAdapter` implements only `app.install` (`adapters/linux.py:21-33`)
     but policy marks `app.install` live only on macOS (`policy.py:126-131`) and the live
     check precedes the broker-grant check (`policy.py:73-85`) ⇒ `platform_not_live` always.
   - **`app.remove` / `service.manage`**: empty `live_support` tuples (`policy.py:133-134`)
     ⇒ not live on any platform. Effective live mutation set is macOS `app.launch` +
     `app.install` only.

## Silently-disabled seam (the headline finding)

`NodeService` accepts `verifier: Verifier | None = None` (`node.py:83`) and returns
UNVERIFIABLE whenever it is None (`node.py:442-447`). `cli.py` wiring passes **no
verifier** (zero `verifier` refs in `cli.py`), so `macos_verifier.MacOSVerifier`
(`macos_verifier.py:25`, thoroughly unit-tested) is dead in production: the shipped
daemon never does postcondition verification even though README/architecture claim it.
Lesson: grep *wiring constructors* for optional `= None` hooks, not just the class.
A documented capability that is implemented+tests-green but never passed at the wiring
call site is a silent production gap, not a config option.

## Other findings

- **`--check` writes state**: `node_main` (`cli.py:454`) and `broker_main` (`cli.py:598`)
  construct real SQLite DBs + audit keys before returning. "Check" = no socket, not
  no state.
- **Cross-store hardening asymmetry**: `AuditChain` DB *parent* is not ownership/mode
  hardened (`audit.py:266-269`, only the file chmod'd `audit.py:286`), while
  `OperationStore` (`store.py:145-155`) and `ApprovalStore` (`approvals.py:88-100`)
  require safe owner + non-group/other-writable parent.
- **Inert wiring**: `build_node_handler` fabricates a `broker_peer` UID (`cli.py:294-298`)
  that `BrokerSocketClient.execute` ignores (`client.py:165-172`); the authoritative
  identity is the kernel peer cred at the socket (`server.py:206-223`). Harmless but
  misleading — worth flagging so future readers don't think payload peer is trusted.
- Verified-solid (held, cite to prior references): TOCTOU pin + identity re-check
  (`executor.py:182-249`; adversarial test `test_executor.py:101-121`), broker
  consume-then-audit-gate ordering (`test_broker.py:309-427`), approval one-shot binding
  (`approvals.py:174-377`), HMAC chain + redaction (`audit.py:365-491`), no issuance RPC.

## Missing production pieces (roadmap claims vs tree)

No `deploy/`, no `.plist`, no `.service` anywhere (plan `docs/plans/2026-08-06-device-node-v1.md:67-71`
references a `deploy/macos/` that doesn't exist); no privilege-drop helper, no approval
UI/Touch ID (file-CLI approval only), no log rotation/backup tool, no external audit
anchoring — all honestly listed unshipped in `roadmap.md:16-23` and `security.md:50-51`.

## Technique notes that transferred well

- Verify docs-as-claims: treat README/roadmap/architecture/security as a hypothesis set
  and cite the code that proves or disproves each line.
- Run the suite read-only (flags above) so the "no files modified" report stays honest on a
  non-git tree; use `grep -cE '^def test_'` for per-file counts without a second run.
- Grep patterns that carried the audit: `grep -rn "<Class>" src` (find seams),
  `grep -rn "manifest|plist|systemd"` (find missing deploys), `--check` side-effect check.
