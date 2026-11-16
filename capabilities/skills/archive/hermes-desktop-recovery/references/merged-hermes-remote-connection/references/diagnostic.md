# Diagnosing Port Layout

## Step 1: List listening ports on the server

Use the system's socket inspection tool to find what is bound in the Hermes port range (8600-9200).

Interpretation:
- Port 8642 bound to localhost: the gateway is running. This is the internal messaging bus and only serves a health check — no API routes.
- Port 8787 bound to localhost: the dashboard was started with a non-default port flag. This IS the service the desktop app needs.
- Port 9120 bound: the API server platform is configured. May or may not be active.
- Nothing on 9119: either the dashboard is not running at all, or it is running on a different port.

## Step 2: Check the dashboard configuration

The Hermes config may specify a non-default dashboard port under the dashboard section.

## Step 3: Probe the dashboard candidate

Once a candidate port is identified, verify it serves the full API: health, status, and models endpoints should all return HTTP 200.

## Step 4: Confirm the gateway is NOT the dashboard

Port 8642 responds to health checks but returns errors on any API route. This confirms it is the gateway, not the dashboard — explaining why tunneling to it fails silently.
