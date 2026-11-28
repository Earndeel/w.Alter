---
name: remote-systems-operations
description: Use for remote hosts, services, tunnels, and exit routing.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [remote-systems, ssh, macos, services, tailscale, vpn, recovery]
---

# Remote Systems Operations

Use this class-level skill for remote Mac access, SSH tunnels, self-hosted services, launch agents, Tailscale policy, VPN exits, and host recovery. Prove target identity and the administrative path before any mutation, because a reachable port is not proof that the intended host or layer is under control.

## Always-on rules

- Separate client, application, and infrastructure layers; a client error is not data loss, and a healthy public endpoint is not administrative access.
- Resolve hostname, DNS/IP, cloud project or tailnet identity, service/version endpoint, and host process before changing the first matching machine.
- Use the least invasive authorized path: existing SSH/tunnel, authenticated console, provider-native recovery, then a planned reversible recovery.
- Create and verify an application export and infrastructure snapshot before host or data changes; never prune volumes or overwrite the only backup.
- Keep credentials in the approved secret store, use mode-0700/0600 temporary paths, and never print keys, tokens, passwords, or secret-bearing metadata.
- Verify every external side effect by reading back the exact service, ACL, process, tunnel, archive, or client result.

## Remote Mac access

- Make the operator initiate connections and apply deny-by-default ACLs limited to the explicitly allowed SSH/VNC destinations.
- Do not add reverse tunnels, autossh, cron, or phone-home persistence merely because an old package used them.
- Treat SSH as shell/file access and VNC/Screen Sharing as visual control; they are separate capabilities and need independent verification.
- Use state detection rather than flag files, batch privileged commands into one prompt, append keys idempotently, and provide an explicit ON/OFF path.
- Before deployment verify target Mac, user session, SSH reachability, and tailnet tag; afterward verify SSH, VNC, the OFF switch, and that unauthorized tailnet traffic is denied.

## SSH tunnels and local HTTP APIs

- Bind a local desktop API through an explicit loopback SSH tunnel and verify the API root before calling application endpoints.
- Cache a remote token once per session in a protected temporary file; use Python `urllib.request` for nested JSON rather than fragile shell interpolation across SSH and command substitution.
- Treat stale `.json`/`.pid` state as a hypothesis: check whether the recorded process exists before removing the file, then restart and read back state.
- If TCP connects but the app returns no bytes, check macOS App Nap/background state and activate the app only when the user-approved operation requires it.
- Never expose a credential-bearing proxy beyond loopback or guess an API contract from a successful TCP connection.

## Self-hosted service repair

1. Define the repair gate: endpoint reachability, compatible server/client versions, preserved volumes, and a real login/sync/decryption/display check.
2. Prove the public service maps to the intended cloud project/VM/zone and guest host; a public key in cloud metadata does not prove guest acceptance. Stop blind retries after a persistent access denial.
3. Inspect deployment read-only: container names, image tags/digests, compose files, bind mounts, named volumes, ports, healthchecks, and recent redacted logs.
4. Separate configuration repair from version upgrade. For a healthcheck or proxy fix, retain image and volumes; for an upgrade, use a pinned compatible release and recreate only the relevant service.
5. Verify external HTTPS/TLS, application identity/version, health body, logs, client authentication, sync, and existing-record display. Keep rollback material until client verification passes.
6. For scheduled jobs, compare effective connection endpoints with the running container network and exercise real read-only queries with bounded timeouts; a successful query is not proof the scheduled job completed.

## LaunchAgent and watchdog reliability

- Reproduce the exact script under a minimal `launchd`-like environment with absolute paths, standard config locations outside TCC-protected Desktop/Documents/Downloads, explicit SSH config, `BatchMode`, and bounded connect timeouts.
- Check syntax, one real launch interval, and logs for a healthy no-op before increasing restart behavior.
- A blank tmux/cmux pane is not proof of a dead session; inspect process/session state before restarting. Reconnect loops usually indicate a bad health check.
- Separate observation from foreground control. Cursor/focus/screen input needs a short native approval lease; refusal or timeout returns before invoking input, while invisible health checks remain prompt-free.
- After targeted changes, recheck sibling jobs and listeners instead of trusting `launchctl` output alone.

## Tailscale ACL and exit routing

- Declare tags in `tagOwners` before using them in grants, add declarations first, tag devices second, and tighten grants last so devices do not temporarily lose connectivity.
- Keep grant fields valid and use host firewall/node attributes for protocol/port filtering; duplicate keys or undeclared tags invalidate the policy.
- For geo-blocked portals, verify exit geography before cookies or authentication. Check each hop's public IP and portal response, then change only the browser/container route.
- Never connect a VPN on the host when it would rewrite the Tailscale route; confine the exit to a dedicated browser proxy/container or an explicitly approved Mac exit path and verify host IP unchanged versus proxy IP changed.
- Treat anti-bot/fingerprint failures as distinct from geo-blocking, keep persistent profiles for fingerprint-bound challenges, and do not inject cookies from another exit.

## Recovery stop conditions

Stop and report a blocker when target identity, admin access, backup, deployment layout, data volume, or rollback cannot be verified. A recovery console, startup script, disk attachment, ACL tightening, VPN route, or VM restart is a separate high-impact action and requires an explicit reversible gate.
