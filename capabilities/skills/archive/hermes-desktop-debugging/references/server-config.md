# Server Configuration — Abstract Reference

## Dashboard Process

Runs under user systemd supervision. The unit file specifies the loopback bind address, the port, and the session token via environment variable. After any edit, reload the supervisor daemon and restart the unit.

## Auth Mechanism

One shared token. The server stores it as an environment variable in the unit file. The Mac stores it via launchctl. Every API request from the Electron app includes this token in a custom header. The server validates the header against its stored value.

## Host Header

When an intermediate proxy changes the Host header (e.g., adding a DNS name), the dashboard may reject the request. The web server module has host validation logic that may need adjustment to accept the proxy's hostname.

## Port Layout

| Port | Role | Listens On |
|------|------|-----------|
| Gateway port | Internal agent gateway | Varies |
| Dashboard port | Web UI + API | Loopback only |
| Forwarder port | External-facing relay | Network interface IP |

## External Access

The recommended pattern for exposing the loopback-bound dashboard: establish a relay process on the network interface that forwards to the loopback port. This avoids TLS complications because the relay can operate without encryption while the dashboard remains loopback-only.
