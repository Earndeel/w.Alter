# cmux + tmux + SSH Clipboard Setup (OSC 52)

Complete walkthrough of fixing clipboard copy-paste for Hermes TUI running on a headless VPS, accessed from Mac via cmux.

## Architecture

```
Mac (cmux client) → SSH → VPS (ubuntu user, tmux) → sudo -i → hermes --tui (root)
```

Key facts:
- tmux runs as `ubuntu` user (NOT root)
- hermes runs as `root` via `sudo -i`
- No X11/Wayland on VPS (`$DISPLAY` and `$WAYLAND_DISPLAY` empty)
- cmux connects from Mac via SSH through Tailscale tunnel

## Files Modified

| File | Owner | Purpose |
|------|-------|---------|
| `/home/ubuntu/.tmux.conf` | ubuntu | tmux config: set-clipboard, allow-passthrough, update-environment |
| `/etc/sudoers.d/keep-ssh-env` | root | Preserve SSH_CONNECTION through sudo -i |
| `/root/.bashrc` | root | HERMES_TUI_FORCE_OSC52=1 + SSH_CONNECTION fallback |
| `/home/ubuntu/bin/start-hermes-root-new` | ubuntu | Launcher script with tmux options |
| `ui-tui/src/lib/platform.ts` | root (hermes repo) | Cmd+C over SSH (isActionMod accepts meta) |
| `ui-tui/src/lib/openExternalUrl.ts` | root (hermes repo) | Link click → clipboard via OSC 52 |

## Step-by-step

### 1. tmux.conf (ubuntu user)

```bash
# /home/ubuntu/.tmux.conf
set -g status off
set -g history-limit 100000
set -g mouse on
set -g allow-passthrough on
set -g set-clipboard on
set -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
```

**Pitfall:** Must be ubuntu's tmux.conf, not root's. Check: `ps aux | grep tmux | grep -v grep` to see which user owns tmux.

### 2. sudoers rule

```bash
cat > /etc/sudoers.d/keep-ssh-env << 'EOF'
Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"
EOF
chmod 440 /etc/sudoers.d/keep-ssh-env
visudo -c  # verify
```

### 3. Root's .bashrc

```bash
export HERMES_TUI_FORCE_OSC52=1
# Fallback SSH_CONNECTION for when tmux was started from non-SSH context
export SSH_CONNECTION="${SSH_CONNECTION:-127.0.0.1 PORT 127.0.0.1 22}"
```

The `${SSH_CONNECTION:-default}` syntax uses the real value if available, falls back to the tunnel address otherwise.

### 4. Launcher script

```bash
#!/usr/bin/env bash
SESSION="hermes-$(date +%Y%m%d-%H%M%S)-$$"
tmux set-option -g allow-passthrough on
tmux set-option -g set-clipboard on
tmux set-option -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
tmux new-session -d -s "$SESSION" "sudo -i bash -lc 'cd /root && hermes --tui; exec bash'"
tmux attach-session -t "$SESSION"
```

**Pitfall:** `set-option` must come BEFORE `new-session`. Setting environment after session creation doesn't propagate to existing panes.

### 5. TUI source patches

See `platform.ts` (isActionMod) and `openExternalUrl.ts` (OSC 52 fallback) patches in the main SKILL.md.

## Diagnosis

```bash
# Which user runs tmux?
ps aux | grep tmux | grep -v grep

# tmux config correct?
cat /home/ubuntu/.tmux.conf

# tmux has set-clipboard?
sudo -u ubuntu tmux show-option -g set-clipboard

# SSH_CONNECTION in tmux global env?
sudo -u ubuntu tmux show-environment -g | grep SSH_CONNECTION

# SSH_CONNECTION in hermes process?
HERMES_PID=$(pgrep -f "python.*hermes.*tui" | tail -1)
cat /proc/$HERMES_PID/environ | tr '\0' '\n' | grep SSH_CONNECTION

# FORCE_OSC52 in hermes process?
cat /proc/$HERMES_PID/environ | tr '\0' '\n' | grep FORCE_OSC

# sudo -i preserves SSH_CONNECTION?
SSH_CONNECTION="test" sudo -i bash -c 'echo $SSH_CONNECTION'
```

## Common Pitfalls

1. **Editing root's tmux.conf instead of ubuntu's** — tmux runs as ubuntu, reads ubuntu's config
2. **tmux set-environment after session creation** — doesn't affect existing panes, only new ones
3. **`update-environment` explicitly UNSETs vars** — if SSH_CONNECTION isn't in the calling env when tmux creates a session, it gets a `-` prefix (explicitly unset) that overrides the global setting
4. **iTerm2 disables OSC 52 by default** — must enable in Preferences → Profiles → Terminal
5. **Terminal.app doesn't support OSC 52** — user must switch to iTerm2/Kitty/WezTerm

## Mac Terminal OSC 52 Support

| Terminal | Support | Notes |
|----------|---------|-------|
| iTerm2 | Yes | Disabled by default — enable in Preferences → Profiles → Terminal |
| Kitty | Yes | Default |
| WezTerm | Yes | Default |
| Ghostty | Yes | Default |
| VS Code | Yes | Default |
| Terminal.app | **No** | Cannot work — must switch terminal |
