# Remote Mac Browser via SSH Tunnel — CDP Performance

## Benchmarked Performance (Brave on Mac via Tailscale, May 2026)

| Metric | Value |
|---|---|
| CDP connect (first, via tunnel) | ~0.8s |
| JS evaluate (persistent connection, avg) | ~156ms |
| JS evaluate (persistent connection, min) | ~59ms |
| 10x sequential CDP calls | ~1.55s total |
| Same 10x without persistent connection | ~28s (estimated) |
| Page load (YouTube @hardisk) | ~7.2s (network-bound, unchanged) |

## Key Clarification: "180x Faster"

The v0.14.0 improvement is about **CDP connection overhead** (WebSocket handshake reuse), NOT page load speed.

- **What improved**: Each CDP call (JS eval, DOM query, click, screenshot) goes from ~2800ms (new WebSocket each time) to ~100-150ms (persistent connection). This is the "180x" figure.
- **What did NOT change**: Page load time (network-bound), rendering speed, initial connection time.
- **Impact**: Multi-step browser automation (inspect → click → read → screenshot) is dramatically faster. Single page loads are unchanged.

## Pitfall: macOS Browser CDP Launch

macOS ignores `--remote-debugging-port` if the browser is already running. Must:
1. Quit browser completely: `osascript -e 'tell application "Brave Browser" to quit'`
2. Relaunch via binary path (NOT `open -a`): `"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222`

`open -a` silently drops args on already-running apps.
