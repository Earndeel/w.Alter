---
name: remote-support-access
description: One-click access package for third-party Macs — Tailscale + SSH + screen sharing with ON/OFF toggle, ACL isolation, and hardcoded auth keys. For friends, family, clients. NOT for the user's own machines (see ssh-mac-remote-control for persistent self-access).
triggers:
  - "accès à distance pour un ami"
  - "package exécutable Mac"
  - "bouton ON/OFF accès"
  - "donner accès à mon Mac"
  - "contrôler le Mac de quelqu'un"
tags:
  - mac
  - tailscale
  - ssh
  - remote-access
  - third-party
---

# Remote Support Access — Third-Party Mac

## What this skill covers
Creating a one-click access package that lets W.Alter SSH into a **third party's** Mac
(friend, family, client) via Tailscale. The recipient does NOTHING except double-click and
enter their admin password once.

This is a different architecture from self-owned Mac control (which uses reverse SSH tunnels
and persistent LaunchAgents). Third-party access is **W.Alter-initiated**, with no persistent
processes on the target Mac.

## When to use
- User asks to set up remote access for "un ami", "un collègue", "ma mère", etc.
- User says "package exécutable", "bouton ON/OFF", "un seul sudo"
- User wants the recipient to have ZERO manual configuration

## Architecture

```
┌─────────┐  SSH (w-alter → Mac)   ┌──────────────────┐
│ w-alter │ ──────────────────────→ │ Mac ami          │
│ (VPS)   │   via Tailscale IP     │ SSH + screen     │
└─────────┘                         │ sharing ON/OFF   │
                                    └──────────────────┘
```

Key principle: **W.Alter initiates**. The friend's Mac is a plain SSH server.
No reverse tunnels, no autossh, no LaunchAgents, no cron jobs. The friend
closes the Terminal window and access stops.

## Package structure

Single folder → zipped → sent:

```
walter-access/
├── walter-access.command   ← THE button (double-click to toggle ON/OFF)
├── walter_key.pub          ← W.Alter's public SSH key
├── TAILSCALE_ACL.md        ← ACL for user to apply on admin.tailscale.com
└── README.txt              ← Human instructions for the friend
```

### walter-access.command
- Detects current state (ON = SSH running + VNC active; else OFF)
- Shows status and offers toggle
- **ON**: installs Tailscale (if missing), connects with hardcoded auth key,
  enables SSH + Screen Sharing, adds public key
- **OFF**: disables SSH + VNC
- **Single sudo prompt** — all privileged commands batched at the start

## Tailscale auth key generation

The auth key should be **hardcoded** in the .command so the friend never
needs to paste anything.

Generate via Tailscale API (requires an API access token from the user):

```bash
curl -s -X POST "https://api.tailscale.com/api/v2/tailnet/-/keys" \
  -u "tskey-api-XXXXX:" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "devices": {
        "create": {
          "reusable": true,
          "ephemeral": false,
          "preauthorized": true
        }
      }
    }
  }'
```

The returned `tskey-auth-...` goes directly into the script:
```bash
sudo tailscale up --auth-key="tskey-auth-XXXXX" --hostname="ami-walter"
```

**Key type: REUSABLE, not ephemeral.** Ephemeral makes the node disappear on
disconnect. Reusable means it survives ON/OFF cycles.

## ACL isolation — mandatory before sending

The user MUST apply an ACL that prevents the friend's Mac from accessing
anything on the user's tailnet. Add to `admin.tailscale.com → Access Controls`:

```jsonc
"acls": [
  {
    "action": "accept",
    "src":    ["tag:w-alter"],
    "dst":    ["tag:w-alter-clients:*"],
    "proto":  ["tcp"],
    "dstPort": [22, 5900]
  }
]
```

This means:
- `tag:w-alter` (W.Alter's server) can reach `tag:w-alter-clients` on SSH+VNC only
- `tag:w-alter-clients` can initiate NOTHING to anyone
- Friend's Mac is blind to the rest of the tailnet

## Workflow

1. User provides Tailscale API access token (or generates auth key manually on admin.tailscale.com)
2. Generate reusable auth key via API
3. Write `walter-access.command` with hardcoded key
4. Write `TAILSCALE_ACL.md` with ACL snippet
5. Write `README.txt` with friend instructions
6. Zip → send
7. **User applies ACL** on admin.tailscale.com (before friend runs the package)

## Pitfalls

- **No reverse tunnel for third-party access.** The friend doesn't own the
  tunnel, won't know how to restart it, and shouldn't have persistent
  outbound connections to W.Alter.
- **No browser automation to extract Tailscale credentials.** AppleScript/UI
  scripting against Brave/Chrome on Mac is too fragile for auth workflows.
  Ask the user for the API token or key manually.
- **Auth key must be reusable, not ephemeral.** Ephemeral = node vanishes on
  disconnect, breaks ON/OFF toggle.
- **ACL before sending.** Without ACL, the friend's Mac can scan the user's
  entire tailnet.
- **Sensitive key in script.** The auth key is in plaintext in the .command.
  This is acceptable because: (a) it only works for this specific tailnet,
  (b) it's tagged and ACL-restricted, (c) the package is sent directly to a
  trusted recipient.

## Companion skills
- `ssh-mac-remote-control` — for controlling the user's **own** Mac via
  persistent reverse tunnels and LaunchAgents. That's the pattern for
  self-owned machines; this skill is for third-party ones.
