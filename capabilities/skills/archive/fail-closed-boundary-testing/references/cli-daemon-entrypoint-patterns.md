# walter-device-node CLI / daemon entrypoint patterns

Session detail for the W.Alter Device Node (`/root/walter-computer-use`), a
pure-stdlib Python package whose `pyproject.toml` declares three console scripts
under `[project.scripts]`:

- `walter-node`   → `walter_device_node.cli:node_main`  (unprivileged Node daemon)
- `walter-broker` → `walter_device_node.cli:broker_main` (privilege Broker daemon)
- `walterctl`     → `walter_device_node.cli:client_main` (local JSON-RPC client)

The three entrypoints live in `src/walter_device_node/cli.py`; tests in
`tests/test_cli.py`.

## Module map (what the entrypoints wire together)

- `node.py` → `NodeService` — unprivileged request handler (health,
  capabilities.list, device.observe, audit.verify, operation.get/submit).
  Needs: device_id, platform, policy, store, audit, adapter, executor, optional
  broker + broker_peer. Its `.handle(method, params, *, peer)` is RpcHandler-
  compatible, so the NodeService instance IS the server handler.
- `broker.py` → `BrokerService` + `BrokerRpcHandler(service)` — elevated ops;
  `BrokerService` REQUIRES a non-None `peer_authorizer` (fail-closed startup).
- `client.py` → `UnixRpcClient` / `BrokerSocketClient` — sync client; validates
  socket owner (0o600), kernel peer creds, frame bounds.
- `server.py` → `UnixRpcServer` — owner-only Unix-socket JSON-RPC server. Its
  own fail-closed guards: socket path absolute + ≤100 bytes, socket parent a
  real dir owned by current user AND mode 0o700 (no group/other bits), refuses
  symlink/`replace non-socket` path, unlinks its own socket on `close()`.
- `executor.py` → `SubprocessExecutor` — takes `allowed_executables` (frozenset
  of absolute paths) and refuses anything not allow-listed. The CLI's
  `--allowed-executable` (repeatable) populates it; an empty set = execution
  denied (fail-closed).
- `policy.py` → `default_policy()`; `store.py` → `OperationStore` (node.db);
  `audit.py` → `AuditChain` (db + 0o600 key) — the CLI derives db/key paths from
  the state dir.
- `adapters/` → concrete `DeviceAdapter`s; the CLI registry only exposes the
  ones that exist (`macos` → `MacOSAdapter(brew_path=…)`, `linux` →
  `LinuxAdapter(package_manager, executable)`). Unknown platform = `ConfigError`.

## How cli.py is shaped (for consistency on future edits)

- Frozen dataclass configs `NodeConfig` / `BrokerConfig` with derived path
  properties (`store_db`, `audit_db`, `audit_key`, `approvals_db`).
- `ConfigError(ValueError)`; `validate_node_config` / `validate_broker_config`
  centralize all fail-closed checks.
- `build_node_handler(cfg) -> NodeService`, `build_broker_handler(cfg) ->
  BrokerRpcHandler`, `start_node_server(cfg) -> UnixRpcServer`,
  `start_broker_server(cfg) -> UnixRpcServer` (async, returns started server).
- `node_main`/`broker_main`: parse → build config → `build_*_handler` (catches
  ConfigError → stderr + return 1) → `--check` returns 0 → else `asyncio.run`
  of start + `serve_forever`.
- `client_main`: argparse subcommands (health, capabilities, observe,
  audit-verify, operation-get, operation-submit); wraps call in a broad
  fail-closed except; prints JSON result to stdout or `error:` to stderr + rc 1.

## Run / smoke-test commands (verified)

```sh
# validate wiring without binding (state dir should be 0o700)
venv/bin/walter-node --check --state-dir "$D" --device-id smoke-1 \
  --platform macos --allowed-executable /usr/bin/open
venv/bin/walter-broker --check --state-dir "$D" --platform macos \
  --allowed-executable /usr/bin/open

# live daemon + client round-trip
mkdir -p "$D" && chmod 700 "$D"   # 0o755 parent => daemon refuses
venv/bin/walter-node --state-dir "$D" --socket "$D/node.sock" \
  --device-id smoke-1 --platform macos --allowed-executable /usr/bin/open &
venv/bin/walterctl --socket "$D/node.sock" health
venv/bin/walterctl --socket "$D/node.sock" capabilities
```

End-to-end fail-closed demonstration (verified): submitting a prohibited
capability (`power.shutdown`) via `walterctl operation-submit` returns
`status: refused`, `code: prohibited_capability`, writes an audit entry, and is
retrievable via `operation-get` — the write/read path persists and fails closed
without executing anything.

## Test recipe (async daemon + sync client)

```python
@pytest.mark.asyncio
async def test_node_daemon_serves_health(tmp_path):
    cfg = _node(tmp_path)                      # socket inside state dir, short name
    server = await start_node_server(cfg)
    client = UnixRpcClient(str(cfg.socket_path), timeout_seconds=2)
    try:
        health = await asyncio.to_thread(client.call, "health", {})
        assert health["ok"] is True
    finally:
        await server.close()
    assert not cfg.socket_path.exists()
```

Notes: use `asyncio.to_thread` for the sync `client.call`. Keep the socket
filename short (server enforces ≤100 bytes and tmp_path can be long). Assert
the socket is unlinked after close.

## Environment note (transient — not a durable rule)

The user's repo may have more than one venv (a `.venv-harden` appeared then
vanished mid-task; the stable one was `.venv` with the installed
`walter-node`/`walter-broker`/`walterctl` console scripts and pytest 9.0.3 /
pytest-asyncio matching pyproject pins). Always re-verify which venv actually
runs the suite before trusting a lint/test result.
