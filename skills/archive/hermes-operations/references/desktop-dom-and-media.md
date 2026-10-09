# Desktop DOM and media delivery branch

## Live desktop DOM inspection

Use CDP only against a development desktop instance. Check the configured loopback port before acting; do not relaunch or kill the user's app to obtain a port. Prefer stable `data-slot` selectors, project evaluated values down to a small JSON result, and pass a target match so the main window is not confused with overlays or DevTools. CDP proves computed facts and console output, not visual quality; use a screenshot or human review for aesthetics.

If isolation is needed, launch a separate instance with its own temporary `HERMES_HOME`, user-data directory, and CDP port, then poll until the port is live and clean the instance up afterward.

## Desktop media regression

Trace media in order: backend bytes and headers, gateway access log, client reference resolution, renderer, and recipient-visible playback/download. A healthy file server with zero client requests localizes the failure to client-side reference resolution; in local mode, a gateway path may be read from the desktop's own disk instead of the gateway.

Verify MIME, `inline` versus `attachment`, and Range/206 slices. Keep listing and text routes header-only when query-token media routes are required. Check the actual data-URL cap before blaming file size, and deliver a playable master plus a compatible fallback when codec support differs. A server or renderer change needs its owner restarted or rebuilt before it can be visible.
