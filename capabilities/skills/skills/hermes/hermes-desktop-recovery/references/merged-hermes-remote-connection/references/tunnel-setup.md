# Tunnel Setup

## Standard case

When the remote dashboard runs on its default port 9119, create an SSH local forward from the client machine mapping its local 9119 to the server's 9119.

Then launch the desktop app — it will see the dashboard on localhost and connect normally. Alternatively, open a browser to localhost:9119 for the same web interface.

## Non-standard dashboard port

When the dashboard was started with a custom port (check the server's listening ports), map the client's local 9119 to that custom port instead.

## Verification

After the tunnel is up, verify the tunneled port responds to health checks and API routes. A working tunnel returns HTTP 200 for the health endpoint and valid JSON for the status endpoint.

## Wrong-port pitfall

Do not tunnel to the gateway port (8642). The gateway only responds to health checks — the desktop app needs the full API surface (status, models, WebSocket) which only the dashboard provides. Tunneling to the gateway gives a false positive (health passes) followed by silent failure when the app tries to call API routes.
