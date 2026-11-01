# Remote configuration and renderer recovery — verified recipe

Session-specific reference for a Hermes V2 Mac app that reports `Gateway needs setup` after an update while the Oracle VM appears healthy.

## What was actually wrong

The VM dashboard and gateway were healthy, but the Mac client had:

- `~/Library/Application Support/Hermes/connection.json` with `mode: "local"`;
- a stale remote token value (`no-auth`), not the live dashboard session token;
- unset `launchctl` fallback variables;
- more than one Hermes bundle registered, so `open -a "Hermes V2"` could launch the development copy instead of `/Applications/Hermes V2.app`.

The dashboard REST and WebSocket paths were independently reachable from the Mac, proving the remaining failure was client configuration/state rather than the gateway process.

## Safe repair sequence

1. Over Tailscale SSH, inspect without printing secrets:
   - `launchctl getenv HERMES_DESKTOP_REMOTE_URL`
   - whether `HERMES_DESKTOP_REMOTE_TOKEN` is set and its length/hash only
   - `~/Library/Application Support/Hermes/connection.json`
2. Back up `connection.json`, then set the current schema:

```json
{
  "mode": "remote",
  "remote": {
    "url": "http://127.0.0.1:9119",
    "authMode": "token",
    "token": {"value": "<live-dashboard-session-token>"}
  }
}
```

Preserve unrelated keys. Set the same URL and token using `launchctl setenv` so GUI launches inherit them. Never print or commit the token.

3. Gracefully quit Hermes, then launch the intended bundle by absolute path:

```sh
open "/Applications/Hermes V2.app"
```

Verify the running main process contains `/Applications/Hermes V2.app/Contents/MacOS/Hermes`; do not rely on `open -a` when a dev copy exists.

4. If the log shows `Remote Hermes backend is ready` but the UI loops or remains black, move these directories into a timestamped backup rather than deleting them:

```text
~/Library/Application Support/Hermes/Local Storage
~/Library/Application Support/Hermes/Session Storage
~/Library/Application Support/Hermes/Cache
~/Library/Application Support/Hermes/GPUCache
~/Library/Application Support/Hermes/Code Cache
```

Keep Cookies, session databases, `connection.json`, and the backup. Relaunch normally.

## Verification probes

From the Mac, test the configured URL with the `X-Hermes-Session-Token` header. At minimum, verify REST status and the WebSocket URL:

```text
http://127.0.0.1:9119/api/status
ws://127.0.0.1:9119/api/ws?token=<live-token>
```

The WebSocket should open and emit a `gateway.ready` event. The dashboard status should report the gateway as running. A bad Host header must still be rejected; do not disable the auth gate.

The desktop log is `~/.hermes/logs/desktop.log`. Healthy final lines look like:

```text
[hermes] [boot] Connecting to remote Hermes backend at http://100.91.35.121:8788
[hermes] [boot] Remote Hermes backend is ready
```

A native `screencapture` can show a black Electron window on this build even while the DOM is fully rendered. If needed, launch temporarily with `--remote-debugging-port=9223` and `--remote-allow-origins=*`, inspect `Runtime.evaluate` / `document.body.innerText`, or use `Page.captureScreenshot`. Close and relaunch without those flags; never leave the diagnostic port exposed.

## Relay contract

Use the validated local relay procedure from the main skill. After an upstream socket is established, clear any connect timeout before relaying traffic; otherwise an idle authenticated WebSocket can be reset and the Desktop can enter a false reconnect cycle. Do not use a public-URL setting as a Host-header workaround.

## Reusable pitfalls

- `Gateway needs setup` is not proof that the remote gateway is stopped; check remote status first.
- A mode-local connection file can make the app start local `hermes serve` processes and then report a generic gateway/setup state.
- A generic app name can select the wrong Hermes bundle.
- Keep renderer cleanup reversible; do not erase cookies or all user data as a first response.
- Do not use blanket `pkill`/kill commands. Inspect ownership and stop only the known forward or app gracefully.
