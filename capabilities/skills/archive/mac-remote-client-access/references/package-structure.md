# Package Structure — `walter-access.zip`

## Files

```
walter-access/
├── walter-access.command   ← Double-click to toggle ON/OFF
├── walter_key.pub          ← w-alter's SSH public key (Ed25519)
├── README.txt              ← End-user instructions (for the friend)
└── TAILSCALE_ACL.md        ← ACL instructions (for Lucas, the user)
```

## Script Behavior (walter-access.command)

**ON state:** activates Remote Login (SSH) + Screen Sharing (VNC), adds SSH key,
installs/connects Tailscale, displays connection info.

**OFF state:** deactivates SSH + VNC. No uninstall, no key removal.
Friend can re-enable instantly by double-clicking again.

**Design decisions:**
- Single `sudo` prompt — all privileged commands batched
- State detection via `systemsetup -getremotelogin`, not flag files
- SSH key append is idempotent (skips if already present)
- No LaunchAgent, no crontab, no autossh, no background processes
- Works with or without Tailscale auth key (prompts if needed)

## SSH Key Format

Ed25519 public key, one line. Comment field: `root@w-alter` (used for idempotent check).

## README.txt Tone

Friendly, reassuring, non-technical. French by default. Explains:
- What it is (one-button remote help from Lucas)
- How to use (double-click, press Enter)
- Reassurances (no spyware, standard macOS tools, can cut anytime)
