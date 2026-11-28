---
name: mac-remote-access-operations
description: Use for secure third-party Mac remote-access packages.
tags: [macos, ssh, vnc, tailscale, remote-access, acl]
metadata:
  hermes:
    tags: [macos, ssh, vnc, tailscale, remote-access, acl]
---

# Third-Party Mac Remote Access Operations

Use this umbrella for packaging and operating one-direction remote access to a friend's or client's Mac through Tailscale, SSH, and Screen Sharing.

## Security architecture

Make the operator initiate every connection. Apply a deny-by-default ACL so the client Mac can reach nothing in the operator's tailnet except the explicitly allowed SSH/VNC destinations. Apply and verify the ACL before sending a package. Do not use reverse tunnels, autossh, cron, or persistent phone-home processes for this third-party pattern; older archived package recipes may describe them, but they conflict with the current isolation contract.

## Package contract

Prefer a transparent `.command`/zip package when a notarized installer is not required. Use state detection rather than flag files, batch privileged commands into one sudo prompt, append the SSH key idempotently, provide an explicit ON/OFF switch, and explain Gatekeeper and the one manual Screen Sharing permission step. SSH supplies shell/file operations; VNC supplies visual control and is not interchangeable with either.

Use reusable versus ephemeral Tailscale keys deliberately and document their lifecycle. Keep secrets out of reports and do not automate credential extraction from the recipient's browser.

## Operational verification

Before deployment, verify the target Mac, user, interactive session, SSH reachability, and Tailscale tag. After enabling access, verify SSH and VNC independently, confirm the client cannot initiate unauthorized tailnet traffic, and test the OFF switch. For an already configured Mac, treat file transfer as a separate operation: hash and count the archive locally, use a direct online tailnet peer, transfer, then hash, size-check, and test the archive remotely.

Keep launchd/TCC automation as a separate class unless the package explicitly needs a user-session helper; do not reintroduce persistence merely because an old package used it.

Exact historical package, ACL, technical-decision, and transfer recipes are routed in `references/curator-mac-remote-archive-routes.md`.
