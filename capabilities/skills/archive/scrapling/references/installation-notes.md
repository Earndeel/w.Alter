# Scrapling Installation — Session Notes

## Verified working install (2026-05-04)

System: Ubuntu 24.04, Python 3.12.3 (externally managed), aarch64 Oracle Cloud.

### CRITICAL: extras required
`pip install scrapling` → BROKEN. Missing `curl_cffi`, `playwright`, etc.
`pip install "scrapling[all]"` → WORKS. Installs all fetcher engines + MCP deps.

### Steps that succeeded
```bash
python3 -m venv ~/.venv/scrapling
~/.venv/scrapling/bin/pip install "scrapling[all]"
# Browser deps NOT run on this machine (headless ARM, no display)
# On a desktop: ~/.venv/scrapling/bin/scrapling install
```

### Test results
```
Fetcher.get('https://httpbin.org/html')
  → Status 200, CSS selectors work
  → Latency ~300ms

StealthyFetcher not tested (needs browser deps + display)
Spider not tested (needs full browser setup)
```

### MCP server path
Binary: `~/.venv/scrapling/bin/scrapling`
Command: `scrapling mcp` (stdio transport)

### Hermes config block
```yaml
mcp_servers:
  scrapling:
    command: "/root/.venv/scrapling/bin/scrapling"
    args: ["mcp"]
    timeout: 120
```

### Pitfall: externally-managed environment
On Ubuntu 24.04+ / Debian 12+ with PEP 668:
- `pip install` system-wide → `externally-managed-environment` error
- Fix: use venv or pipx (pipx not installed on this machine)
