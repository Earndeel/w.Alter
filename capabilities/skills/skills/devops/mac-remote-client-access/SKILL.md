---
name: mac-remote-client-access
description: "Remote Mac access setup for third-party clients — SSH and VNC via Tailscale with one-direction ACL isolation and single-button ON/OFF toggle. w-alter initiates all connections; client Mac is fully locked down within the tailnet."
---

# Mac Remote Client Access

## Trigger

User asks to give w-alter remote access (SSH + VNC/GUI) to a friend's Mac, with:
- One-click ON/OFF toggle for the friend
- User's tailnet protected from the client Mac
- No reverse tunnels, no persistence, no autossh

## Architecture Rule (NON-NEGOTIABLE)

**w-alter always initiates connections → Mac ami. Never the reverse.**

```
User's Mac ──→ W.Alter (VPS) ──→ Mac ami (SSH:22, VNC:5900)
                                  │
                                  └── Cannot initiate ANYTHING in tailnet
```

Rationale: if the client Mac is compromised, it must not be able to scan or attack the user's network. With w-alter-initiated connections + deny-all ACL, the client can only respond to established connections.

**Forbidden patterns:**
- `autossh`, `ssh -R`, reverse tunnels
- LaunchAgents/crontabs that phone home
- Any outbound connection from Mac ami → w-alter

## Package Output

Deliverable is a `.zip` with four files — see `references/package-structure.md` for the file layout.
The toggle script is available at `templates/walter-access.command` — copy it and customize the SSH key.

The script is a state-detecting toggle:
- **ON:** activates Remote Login (SSH) + Screen Sharing (VNC), adds w-alter's SSH key, installs/connects Tailscale
- **OFF:** deactivates SSH + VNC
- Single `sudo` prompt (all privileged commands batched)
- No persistence, no background processes, no flag files

## Tailscale ACL (apply BEFORE deployment)

See `references/tailscale-acl.jsonc` for the ACL snippet. Key constraints:
- `tag:w-alter` can reach `tag:w-alter-clients:22` and `tag:w-alter-clients:5900`
- `tag:w-alter-clients` has NO outbound rules → deny-all by default
- Auth keys: ephemeral, tagged `tag:w-alter-clients`

## Artifact transfer

For depositing a user-requested archive on an already configured Mac, use the verified SSH/Tailscale workflow in `references/file-transfer-verification.md`; do not turn a file copy into a GUI-control task.

## Deployment Checklist

1. Generate SSH keypair for w-alter
2. Apply ACL in admin.tailscale.com
3. Generate ephemeral auth key with `tag:w-alter-clients`
4. Package the four files into `.zip`
5. Send zip + auth key to friend
6. Friend double-clicks `.command`, pastes auth key, shares Tailscale IP
7. Connect from w-alter via `ssh` and macOS Screen Sharing app
8. Friend double-clicks again to disable access
