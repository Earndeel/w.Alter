---
name: ssh-resilient-mac-vps
description: "SSH resilience for Mac ↔ VPS connections — autossh auto-reconnect, keepalive tuning, Tailscale transport, tmux session survival. Use when Lucas's Mac drops SSH due to WiFi/network interruptions."
tags: [ssh, autossh, tailscale, tmux, mac, keepalive, reconnect]
triggers:
  - "SSH broken pipe on Mac"
  - "tmux dies when network drops"
  - "autossh reconnect Mac"
  - "keepalive SSH Mac"
  - "cmux broken pipe"
  - "SSH timeout Mac"
---

# SSH Resilience: Mac ↔ VPS via Tailscale

## Problem
Lucas's MacBook Pro loses SSH connections when WiFi/network drops. All multiplexed SSH channels die instantly — even with no active requests. tmux sessions on the VPS survive (they run server-side), but the terminal display is lost and requires manual reconnection.

## Architecture
- **Mac**: lucass-macbook-pro-15, Tailscale IP `100.127.150.1`, user `lucasjouvencon`
- **Mac SSH from VPS**: `ssh lucasjouvencon@100.127.150.1` (authorized via VPS ed25519 key)
- **VPS**: w-alter, Tailscale IP `100.91.35.121`, user `root`
- **Transport**: Tailscale mesh VPN (preferred over direct IP — survives NAT changes, mobile hotspots)
- **Session layer**: tmux on VPS (session name: `hermes`)

## SSH Config (Mac side)

Multiple host aliases for the same VPS — pick the right one per context:

```
Host *
    ServerAliveInterval 10
    ServerAliveCountMax 3
    TCPKeepAlive yes
    Compression yes

Host w-alter
    HostName 100.91.35.121
    User root
    ServerAliveInterval 10
    ServerAliveCountMax 3
    TCPKeepAlive yes
    ExitOnForwardFailure yes
    IdentityFile ~/.ssh/id_ed25519

Host walter-ts
    HostName localhost
    Port 2222
    User ubuntu
    IdentityFile ~/Desktop/Keys/ssh-key-2025-12-10.key
    LocalForward 18789 127.0.0.1:18789
    LocalForward 18792 127.0.0.1:18792
    ServerAliveInterval 10
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

- `w-alter` — direct Tailscale IP, root user, used by autossh/launchd
- `walter-ts` — routed through autossh tunnel (localhost:2222), ubuntu user, with port forwarding — survives network drops
- Global `ServerAliveInterval 10` — aggressive keepalive for all hosts

## Step 2: autossh (Mac side)

```bash
/usr/local/bin/brew install autossh   # Intel Mac
# or /opt/homebrew/bin/brew install autossh  # Apple Silicon
```

autossh monitors the SSH connection and auto-recreates it when the network returns.

### Option A: launchd daemon (recommended — survives reboot, no terminal needed)

Create `~/Library/LaunchAgents/com.walter.autossh.plist` on the Mac:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.walter.autossh</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/autossh</string>
        <string>-M</string><string>0</string>
        <string>-N</string>
        <string>-o</string><string>ServerAliveInterval=10</string>
        <string>-o</string><string>ServerAliveCountMax=3</string>
        <string>-o</string><string>ExitOnForwardFailure=yes</string>
        <string>-o</string><string>StrictHostKeyChecking=no</string>
        <string>-o</string><string>UserKnownHostsFile=/dev/null</string>
        <string>-o</string><string>TCPKeepAlive=yes</string>
        <string>-o</string><string>IdentitiesOnly=yes</string>
        <string>-L</string><string>2222:localhost:22</string>
        <string>w-alter</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AUTOSSH_GATETIME</key><string>0</string>
        <key>AUTOSSH_POLL</key><string>15</string>
        <key>AUTOSSH_LOGFILE</key><string>/tmp/autossh-walter.log</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <true/>
    <key>StartInterval</key><integer>60</integer>
    <key>StandardOutPath</key><string>/tmp/autossh-walter-stdout.log</string>
    <key>StandardErrorPath</key><string>/tmp/autossh-walter-stderr.log</string>
    <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.walter.autossh.plist
```

Key settings:
- `KeepAlive: true` → launchd ALWAYS restarts autossh (regardless of exit code — critical for tunnels where SSH can exit 0)
- `StartInterval: 60` → checks every 60s as fallback
- `AUTOSSH_GATETIME=0` → no grace period, reconnect immediately
- `-N` → no shell, tunnel-only (the shell comes from tmux auto-attach below)
- `-L 2222:localhost:22` → local port forward so cmux can route through the tunnel

### Option B: Shell alias (interactive sessions)

Add to `~/.zshrc` on Mac:
```bash
alias walter='autossh -M 0 -o "ServerAliveInterval 15" -o "ServerAliveCountMax 3" -t w-alter "tmux attach -t hermes || tmux new -s hermes"'
```

- `-M 0`: disable autossh monitoring port (rely on SSH keepalive instead)
- `-t`: force TTY allocation for tmux
- Uses SSH config host alias `w-alter` (clean, no raw IP)

### tmux auto-attach (companion to launchd daemon)

When using the launchd daemon (Option A), add this to `~/.zshrc` so new terminals auto-attach:
```bash
# tmux auto-attach — se rattache automatiquement à la session existante
if command -v tmux &>/dev/null && [ -n "$PS1" ] && [[ ! "$TERM" =~ screen ]] && [[ ! "$TERM" =~ tmux ]] && [ -z "$TMUX" ]; then
  if tmux has-session -t hermes 2>/dev/null; then
    exec tmux attach -t hermes
  fi
fi
```

This way: launchd maintains the SSH tunnel, and any new terminal auto-attaches to tmux.

## Step 2b: cmux Tunnel Routing (critical for cmux survival)

**Problem**: cmux runs `ssh -tt walter-ts` — a direct SSH connection to the VPS. When WiFi drops, this connection dies and cmux gets a broken pipe. The autossh tunnel is separate and doesn't protect cmux's connection.

**Solution**: Route cmux traffic THROUGH the autossh tunnel.

### 1. Add local port forwarding to autossh

Update the autossh launchd plist to forward `localhost:2222 → VPS:22`:

```xml
<string>-L</string>
<string>2222:localhost:22</string>
```

Add this pair before `<string>w-alter</string>` in ProgramArguments.

### 2. Modify `walter-ts` SSH host to use the tunnel

```
Host walter-ts
    HostName localhost
    Port 2222
    User ubuntu
    IdentityFile ~/Desktop/Keys/ssh-key-2025-12-10.key
    LocalForward 18789 127.0.0.1:18789
    LocalForward 18792 127.0.0.1:18792
    ServerAliveInterval 10
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

Now cmux connects to `localhost:2222` → autossh tunnel → VPS SSH. When the network drops, autossh reconnects the tunnel, and cmux's next connection attempt succeeds.

### 3. Network watcher for cmux multi-session reconnection

Create `~/bin/cmux-reconnect.sh` on Mac. This script scans ALL workspaces/panes/surfaces and reconnects each broken one:

```bash
#!/bin/bash
# cmux-reconnect.sh — reconnect ALL broken cmux sessions transparently
LOG="/tmp/cmux-reconnect.log"
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
CTRL_C=$(printf "\x03")
LOCAL_USER="lucasjouvencon"

echo "$(date): Network change detected, scanning sessions..." >> "$LOG"

# Wait for tunnel (max 60s)
for i in $(seq 1 60); do
    if nc -z localhost 2222 2>/dev/null; then
        echo "$(date): Tunnel up after ${i}s" >> "$LOG"
        sleep 2
        break
    fi
    sleep 1
done

if ! nc -z localhost 2222 2>/dev/null; then
    echo "$(date): Tunnel never came back, aborting" >> "$LOG"
    exit 1
fi

# Kill dead SSH processes
pkill -f "ssh.*walter-ts" 2>/dev/null
sleep 1

RECONNECTED=0

is_broken() {
    local screen="$1"
    echo "$screen" | grep -qi "broken pipe\|Connection.*closed\|connection reset" && return 0
    echo "$screen" | grep -q "^${LOCAL_USER}@.*~ %" && return 0
    echo "$screen" | grep -q "^${LOCAL_USER}@.*\$ $" && return 0
    echo "$screen" | grep -qi "No such file\|command not found" && return 0
    return 1
}

for ws in $($CMUX list-workspaces 2>/dev/null | grep -o "workspace:[0-9]*"); do
    for pane in $($CMUX list-panes --workspace "$ws" 2>/dev/null | grep -o "pane:[0-9]*"); do
        for surface in $($CMUX list-pane-surfaces --workspace "$ws" --pane "$pane" 2>/dev/null | grep -o "surface:[0-9]*"); do
            SCREEN=$($CMUX read-screen --workspace "$ws" --surface "$surface" --lines 5 2>/dev/null)

            if is_broken "$SCREEN"; then
                echo "$(date): $ws/$pane/$surface is broken, reconnecting..." >> "$LOG"

                # Workspace 1 = hermes, others = plain shell
                if [ "$ws" = "workspace:1" ]; then
                    CMD="ssh -tt -o ClearAllForwardings=yes walter-ts \"bash ~/bin/start-hermes-root-new\""
                else
                    CMD="ssh -tt -o ClearAllForwardings=yes walter-ts"
                fi

                $CMUX send --workspace "$ws" --surface "$surface" "$CTRL_C" 2>/dev/null
                sleep 0.3
                $CMUX send --workspace "$ws" --surface "$surface" "clear" 2>/dev/null
                $CMUX send-key --workspace "$ws" --surface "$surface" "enter" 2>/dev/null
                sleep 0.3
                $CMUX send --workspace "$ws" --surface "$surface" "$CMD" 2>/dev/null
                $CMUX send-key --workspace "$ws" --surface "$surface" "enter" 2>/dev/null

                RECONNECTED=$((RECONNECTED + 1))
                echo "$(date): Reconnected $ws/$pane/$surface" >> "$LOG"
                sleep 1
            fi
        done
    done
done

echo "$(date): Done. Reconnected $RECONNECTED sessions." >> "$LOG"
```

Key design choices:
- **`is_broken()` detection**: catches broken pipe, connection closed, dead local prompts (`user@host ~ %`), and command-not-found errors
- **Per-surface reconnection**: each surface gets its own Ctrl+C + clear + reconnect command
- **Workspace-aware**: workspace:1 runs hermes startup, others run plain SSH
- **`CTRL_C=$(printf "\x03")`**: must use `printf` — zsh interprets `\003` literally
- **Quoted remote command**: `ssh walter-ts "bash ~/bin/start-hermes-root-new"` — quotes prevent local `~` expansion (without quotes, `~` expands to Mac home dir, not VPS home dir)

Create `~/Library/LaunchAgents/com.walter.cmux-reconnect.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.walter.cmux-reconnect</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/lucasjouvencon/bin/cmux-reconnect.sh</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <dict>
        <key>NetworkState</key>
        <true/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/cmux-reconnect-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/cmux-reconnect-stderr.log</string>
    <key>ThrottleInterval</key>
    <integer>15</integer>
</dict>
</plist>
```

Load: `launchctl load ~/Library/LaunchAgents/com.walter.cmux-reconnect.plist`

## Step 3: Remote Configuration via Tailscale SSH

W.Alter can configure the Mac remotely from the VPS via Tailscale SSH.

### Setup (one-time)
1. **Generate SSH key on VPS** (if not exists):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -q
   ```

2. **Send public key to Lucas via Telegram** (NOT terminal — he's on Mac, not VPS):
   ```bash
   curl -s -X POST "https://api.telegram.org/bot<BOT_TOKEN>/sendMessage" \
     -d chat_id=<CHAT_ID> \
     --data-urlencode "text=ssh-ed25519 <PUBKEY> root@w-alter

Commande:
echo 'ssh-ed25519 <PUBKEY> root@w-alter' >> ~/.ssh/authorized_keys"
   ```

3. **Lucas adds key on Mac**:
   ```bash
   echo 'ssh-ed25519 <PUBKEY> root@w-alter' >> ~/.ssh/authorized_keys
   ```

4. **Also generate key on Mac** and add to VPS authorized_keys (for passwordless Mac→VPS):
   ```bash
   ssh lucasjouvencon@100.127.150.1 'ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -q && cat ~/.ssh/id_ed25519.pub'
   # Then add that pubkey to VPS ~/.ssh/authorized_keys
   ```

5. **Test from VPS**:
   ```bash
   ssh -o ConnectTimeout=5 lucasjouvencon@100.127.150.1 "whoami"
   ```

### Remote commands from VPS
Once authorized, W.Alter can run anything on the Mac:
```bash
ssh lucasjouvencon@100.127.150.1 "<command>"
```

## cmux CLI Patterns

See `references/cmux-cli-patterns.md` for full cmux CLI discovery, read/send, and scripted scanning patterns. Key commands: `list-workspaces`, `list-panes`, `list-pane-surfaces`, `read-screen`, `send`, `send-key`.

## Pitfalls

- **Username on Mac**: `lucasjouvencon` (not `lucas`, not `root`). Verify with `whoami` on Mac.
- **SSH Remote Login must be enabled on Mac**: System Settings → General → Sharing → Remote Login → ON. If auth fails silently, this is usually the cause.
- **authorized_keys permissions**: Must be `600`, `~/.ssh` must be `700`. Mac SSH is strict about this.
- **Tailscale must be active on both devices**: Check with `tailscale status` on VPS. Mac shows as `active` in the peers list.
- **autossh `-M 0` is critical**: Without it, autossh tries to use a monitoring port that conflicts with SSH. Use SSH keepalive instead.
- **tmux session must exist**: `tmux attach -t hermes || tmux new -s hermes` handles both cases (attach existing or create new).
- **Power Nap / sleep**: Mac sleep kills all connections. `caffeinate -s` prevents sleep, or configure Energy Saver to prevent sleep on AC power.
- **SSH key copy-paste corruption**: When sending keys via Telegram/messaging, base64 characters like `+` can get corrupted or split during copy-paste. Always verify the key matches exactly after pasting: `cat ~/.ssh/authorized_keys` and compare character-by-character if auth fails.
- **brew not in PATH for non-interactive SSH**: `ssh mac "brew install X"` fails with `brew not found`. Use full path: `ssh mac "/usr/local/bin/brew install X"` (Intel Mac) or `/opt/homebrew/bin/brew` (Apple Silicon).
- **SSH key generation on Mac for reverse auth**: The Mac also needs an ed25519 key and its pubkey added to VPS `authorized_keys` for passwordless Mac→VPS (required by autossh/alias). Don't forget this step.
- **autossh `-N` flag is mandatory for tunnels**: Without `-N`, SSH opens a shell and immediately exits (status 0). autossh sees exit 0 = success and also exits. launchd's `SuccessfulExit: false` won't restart it because 0 is a "successful" exit. Always use `-N` for tunnel-only autossh.
- **launchd `KeepAlive` behavior**: `SuccessfulExit: false` only restarts on NON-ZERO exit. For autossh tunnels where SSH can exit cleanly (status 0), use `KeepAlive: true` (boolean) instead of a dict — it always restarts regardless of exit code.
- **cmux bypasses autossh tunnel**: cmux runs its own `ssh -tt walter-ts` connection. This is SEPARATE from the autossh tunnel. If `walter-ts` points to a Tailscale hostname directly, cmux's connection dies on network drop and autossh doesn't protect it. Fix: route `walter-ts` through `localhost:2222` (autossh tunnel port). See Step 2b.
- **cmux-reconnect `pkill` causes reconnect storm (CRITICAL)**: The `pkill -f "ssh.*walter-ts"` in `cmux-reconnect.sh` kills ALL SSH connections to the VPS on every network state change. Combined with `KeepAlive: NetworkState: true` in the launchd plist, this fires every time macOS detects a network change (WiFi roaming, VPN toggle, sleep/wake), creating a kill-reconnect SIGHUP cycle every 2-3 minutes. Each kill sends SIGHUP to VPS-side sessions (TUI, gateway, tmux). **Fix**: Disable the cmux-reconnect launchd agent (`launchctl unload ~/Library/LaunchAgents/com.walter.cmux-reconnect.plist`) and rely on autossh alone — the autossh tunnel already handles reconnection transparently. If keeping cmux-reconnect for session-level reconnection, patch the script: (1) remove the blanket `pkill -f "ssh.*walter-ts"`, (2) only reconnect surfaces that `is_broken()` returns true for, (3) change launchd `KeepAlive` from `NetworkState: true` to `SuccessfulExit: false`, (4) set `ThrottleInterval` to 60+ seconds.
- **`from=` restriction in authorized_keys**: Use `from="<tailscale-ip>"` to lock keys to specific IPs. Prevents any other Tailscale device from using the key. Do NOT use `restrict` — it blocks PTY allocation needed for shell access.
- **macOS sshd changes require sudo**: Cannot modify sshd_config or reload sshd remotely. System blocks piping passwords to `sudo -S` over SSH (security policy). Send commands via Telegram for Lucas to run locally. Mac password stored in vault (`macos/lucas_password`) for reference but cannot be used programmatically for sudo over SSH.
- **launchd vs shell alias**: Use BOTH. launchd for the persistent tunnel (survives reboot, no terminal needed). Shell alias for interactive `walter` command. They complement each other — launchd keeps the tunnel alive, alias connects tmux through it.

## Step 4: SSH Hardening

See `references/ssh-hardening-tailscale.md` for full details. Summary:

- **authorized_keys**: `from="<tailscale-ip>",no-agent-forwarding,no-x11-forwarding` on both sides
- **sshd_config.d**: Disable password auth, max 3 tries, AllowUsers restriction
- **Tailscale ACLs**: Restrict SSH to Mac ↔ VPS only (no other Tailscale devices)

Lucas must run the Mac sshd changes manually (requires sudo — system blocks sudo-over-SSH). Send via Telegram. Mac password: `vault get macos/lucas_password`.

## Step 5: Backup SSH Key (disaster recovery)

If Lucas loses his Mac or phone, he still needs access to W.Alter. A passphrase-protected backup SSH key provides access from any device.

### Setup (already done)

1. **Generate backup key** (on VPS):
   ```bash
   ssh-keygen -t ed25519 -f /tmp/ssh-backup-key -C "backup@w-alter" -N "<passphrase>"
   ```

2. **Add public key to VPS authorized_keys** (NO `from=` restriction — must work from any IP):
   ```bash
   echo '<pubkey> backup@w-alter' >> ~/.ssh/authorized_keys
   ```

3. **Store private key + passphrase** in two places:
   - **Vault**: `vault add ssh backup_private_key` and `vault add ssh backup_passphrase`
   - **Bitwarden**: Create a Secure Note named "W.Alter SSH Backup Key" with the private key, passphrase, and instructions

4. **Clean up temp files**: `rm -f /tmp/ssh-backup-key /tmp/ssh-backup-key.pub`

### Recovery procedure (from any device)

1. Log into Bitwarden from any browser
2. Get the backup private key + passphrase
3. Install Tailscale, join Lucas's tailnet
4. Save key as `~/.ssh/id_ed25519_backup`, `chmod 600`
5. `ssh -i ~/.ssh/id_ed25519_backup root@100.91.35.121`

The key is passphrase-protected — even if stolen, unusable without the passphrase.

## Verification

After setup:
1. Connect from Mac: `walter` alias
2. Kill WiFi on Mac
3. Wait 60s
4. Re-enable WiFi
5. autossh should auto-reconnect within ~10-30s
6. tmux session should be intact with all panes/windows
