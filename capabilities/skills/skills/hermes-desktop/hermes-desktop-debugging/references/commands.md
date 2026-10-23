# Diagnostic Steps — Abstract Reference

## Environment Variables (Mac)

Use `launchctl getenv` to read and `launchctl setenv` to set the two required variables. Both must be present — if one is missing while the other exists, the app will fail silently with a white screen. After setting, the app must be fully quit and relaunched (Cmd+Q).

## Bundled Assets

The Electron app loads an HTML file from its own bundle inside the Applications directory. If this file is missing, the app cannot render anything. Rebuild the desktop app to regenerate it.

## Dashboard Health

The dashboard process runs under the user's systemd supervisor. It listens only on loopback. Verify it responds to authenticated requests before troubleshooting the Mac side.

## Protocol Gap

The Electron runtime enforces strict certificate validation with no bypass flags. If the connection path involves an intermediate HTTPS proxy that presents a non-public certificate, the app will reject the connection silently. The solution is to route through a plain connection layer that terminates before the final hop — preserving end-to-end loopback communication without TLS in the path.

## Loopback Binding

The dashboard refuses to expand its listening interface beyond loopback unless authentication providers are registered. This is by design. Do not attempt to broaden the bind — instead, bridge the gap with a forwarding mechanism that listens on the external interface and relays to the loopback port.
