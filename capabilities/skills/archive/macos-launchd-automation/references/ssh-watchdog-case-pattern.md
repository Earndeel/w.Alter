# LaunchAgent SSH Watchdog Case Pattern

## Symptom

A macOS watchdog repeatedly restarts or reconnects a terminal/session even though the remote service is reachable. The same SSH command may work from an interactive terminal but fail inside the LaunchAgent.

## Diagnosis Pattern

1. Confirm whether the failing alias depends on a local tunnel or forwarded port.
2. If a direct tailnet route exists, test that route directly and prefer it over the local tunnel.
3. Check whether the identity/config path lives in a TCC-protected folder such as Desktop or Documents.
4. Emulate launchd with a minimal environment and run the same script.
5. Patch the health check to verify the actual target route, not only a proxy symptom.
6. Wait for a real LaunchAgent tick and confirm no unnecessary reconnect occurs.

## Durable Fix Pattern

- Direct route beats local tunnel when available.
- Standard SSH/config directories beat Desktop/Documents for automation inputs.
- Health checks should be explicit, short-timeout, non-interactive, and route-specific.
- Do not kill broad process groups; update the watchdog and verify convergence.

## What Not to Preserve

Do not store host addresses, key names, usernames, ports, or one-off log lines here. Those age badly and can trip security scanners. Preserve the pattern only.
