# hermes-tui-customization — cmux launcher and shortcuts for parallel TUI sessions, cmux-notify filtering, clipboard over SSH, Cmd+C on remote Linux, the .bashrc auto-attach pitfall.

Moved verbatim from SKILL.md on 2026-11-01.

## cmux Launcher — Parallel TUI Sessions from macOS

When the user needs multiple Hermes TUI instances (one per project), a macOS desktop shortcut can launch new cmux panes with pre-configured TUI sessions.

### Architecture

```
macOS shortcut (.app) → AppleScript → shell script → cmux CLI → new split pane → SSH → VPS → tmux → hermes --tui
```

### macOS side: `~/bin/start-hermes-cmux`

```bash
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
LOG="/tmp/hermes-cmux.log"

exec >> "$LOG" 2>&1
echo "---- $(date) ----"

[ -x "$CMUX" ] || { echo "ERREUR: cmux CLI introuvable: $CMUX"; exit 1; }

open -a cmux

# Wait for cmux to be ready (max 15s)
i=0
while [ "$i" -lt 60 ]; do
  "$CMUX" list-workspaces >/dev/null 2>&1 && break
  sleep 0.25
  i=$((i+1))
done

CMD="ssh -tt -o ClearAllForwardings=yes walter-ts 'bash ~/bin/start-hermes-root-new'"

OUT=$("$CMUX" new-split right 2>&1)
echo "new-split output: $OUT"

SURFACE=$(echo "$OUT" | grep -o 'surface:[0-9]\+' | head -1)

if [ -z "$SURFACE" ]; then
  sleep 0.3
  SURFACE=$("$CMUX" identify 2>/dev/null | grep -o 'surface:[0-9]\+' | head -1)
fi

echo "target surface: $SURFACE"
echo "command: $CMD"

if [ -n "$SURFACE" ]; then
  "$CMUX" send --surface "$SURFACE" "$CMD\n"
else
  "$CMUX" send "$CMD\n"
fi
```

### VPS side: `~/bin/start-hermes-root-new` (runs as ubuntu via SSH)

```bash
#!/usr/bin/env bash
SESSION="hermes-$(date +%Y%m%d-%H%M%S)-$$"

tmux new-session -d -s "$SESSION" "sudo -i bash -lc 'cd /root && hermes --tui; exec bash'"
tmux set-option -t "$SESSION" allow-passthrough on
tmux set-option -t "$SESSION" set-clipboard on
tmux set-option -t "$SESSION" status off
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
tmux attach-session -t "$SESSION"
```

### AppleScript wrapper (save as Application via Script Editor)

```applescript
do shell script "zsh $HOME/bin/start-hermes-cmux >/tmp/hermes-cmux-app.log 2>&1 &"
```

Save as File → Export → Application → "Hermes cmux.app" on Desktop.

### Key design decisions

- **Unique session names** (`hermes-YYYYMMDD-HHMMSS-$$`): Each click creates a NEW tmux session. Old sessions stay alive. The user works on multiple projects in parallel — **never kill old sessions**.
- **`tmux set-option` per session**: Options (allow-passthrough, set-clipboard, mouse, update-environment) are set on each new session individually. The ubuntu user's `~/.tmux.conf` has global defaults, but per-session options ensure correctness even if tmux.conf is missing.
- **`exec bash`** after hermes exits: Keeps the tmux pane alive so the user can see output or restart manually.
- **SSH alias** `walter-ts`: Defined in `~/.ssh/config` on the Mac, points to `localhost:2222` (autossh reverse tunnel from VPS).

### Pitfall: Never kill old sessions

The user explicitly corrected this: do NOT use `tmux kill-session` or `tmux new-session -A`. Each shortcut click must create a fresh session without touching existing ones. If cleanup is needed (orphan sessions), the user will ask for it.

### Pitfall: `tmux set-option` AFTER `new-session`

The script sets tmux options AFTER creating the session. This works because `tmux set-option -t "$SESSION"` targets the specific session. However, the shell inside the session starts immediately — if hermes launches before `set-clipboard on` takes effect, the first clipboard operation might miss. In practice this is not an issue because hermes takes a few seconds to start up.

## Clipboard over SSH (cmux / tmux / remote sessions)

When the TUI runs on a headless VPS (no `$DISPLAY` / `$WAYLAND_DISPLAY`), native clipboard tools (xclip, wl-copy) fail silently. The correct path is **OSC 52** — an escape sequence that travels over SSH to the local terminal.

### The clipboard chain

```
hermes TUI → tmux load-buffer + OSC 52 passthrough → SSH → cmux → Mac terminal
```

### Required configuration

**1. tmux.conf** — must be edited for the **user who runs tmux** (usually `ubuntu`, NOT root):

```bash
# /home/ubuntu/.tmux.conf (NOT /root/.tmux.conf!)
set -g allow-passthrough on    # lets OSC 52 pass through tmux to outer terminal
set -g set-clipboard on         # tmux forwards OSC 52 to the outer terminal
set -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
```

**2. sudoers** — `sudo -i` strips `SSH_CONNECTION` by default. Add:

```bash
cat > /etc/sudoers.d/keep-ssh-env << 'EOF'
Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"
EOF
chmod 440 /etc/sudoers.d/keep-ssh-env
```

**3. Environment variable** — in root's `~/.bashrc`:

```bash
export HERMES_TUI_FORCE_OSC52=1
```

**4. Mac terminal** — must support OSC 52:
- **iTerm2**: Preferences → Profiles → Terminal → "Applications in terminal may access clipboard" → checked
- **Kitty / WezTerm / Ghostty**: works by default
- **Terminal.app**: does NOT support OSC 52 — switch to iTerm2

### How setClipboard() decides which path to take

`packages/hermes-ink/src/ink/termio/osc.ts` → `getClipboardPath()`:
- Local macOS (no SSH): `native` (pbcopy)
- Inside tmux: `tmux-buffer` (tmux load-buffer)
- Otherwise: `osc52` (raw escape sequence)

`shouldEmitClipboardSequence()` returns true when:
- `SSH_CONNECTION` is set, OR
- Not inside tmux/screen, OR
- `HERMES_TUI_FORCE_OSC52=1`

When `HERMES_TUI_FORCE_OSC52=1` inside tmux: both tmux load-buffer AND tmux-passthrough OSC 52 are emitted. The tmux passthrough carries the data through to the outer terminal.

### cmux Notifications (macOS native notifications)

The TUI sends macOS notifications via `/usr/local/bin/cmux-notify` when the run completes, errors, or needs user input.

**Architecture:** Backend (`tui_gateway/server.py`) → `cmux.notify` JSON-RPC event → Frontend (`createGatewayEventHandler.ts`) spawns `/usr/local/bin/cmux-notify` → writes DCS passthrough escape sequence to tmux pane pts → tmux forwards via `allow-passthrough` → SSH → cmux → macOS notification.

**Key fix (2026-05-18):** Writing directly to `/dev/pts/N` doesn't reach cmux because tmux captures pane output. The correct approach is to write a **DCS passthrough** sequence (`ESC P tmux ; <OSC> ESC \`) to the tmux client's pts — tmux's `allow-passthrough on` forwards the inner OSC to the outer terminal. Target pts devices running `tmux: client` (the SSH channel), not tmux pane pts.

**Triggers (backend patches via `apply-cmux-notify-patch.py`):**
- `message.complete` (status=complete) → "Hermes ✅ · Run terminée"
- `message.complete` (status=error) → "Hermes ❌ · Run échouée"
- `background.complete` → notification
- `clarify.request` → "Hermes ⏳ · Attend votre réponse"
- Tool completions intentionally excluded (too noisy)

**Payload:** `{success: boolean, reason: "complete" | "input"}` — reason field in `gatewayTypes.ts`.

**Pitfall:** After `hermes update`, re-run `python3 /root/.hermes/scripts/apply-cmux-notify-patch.py` to re-apply backend patches. Frontend changes in `tui-overrides/` restored automatically.

### Pitfalls

1. **tmux runs as ubuntu, not root!** On this VPS, tmux is started by the `ubuntu` user via cmux. The tmux.conf that matters is `/home/ubuntu/.tmux.conf`, NOT `/root/.tmux.conf`. Editing the wrong one has zero effect.

2. **`sudo -i` strips SSH_CONNECTION.** Even with `update-environment` in tmux.conf, `sudo -i` creates a fresh login shell that drops SSH env vars. The sudoers `env_keep` rule is required.

3. **Existing tmux sessions use old config.** After editing tmux.conf, `tmux kill-server` is required. Existing sessions won't pick up `set-clipboard` or `update-environment` changes.

4. **HERMES_TUI_FORCE_OSC52 must be in root's .bashrc**, not ubuntu's. The hermes process runs as root (via `sudo -i`), so it reads root's .bashrc.

## Cmd+C on remote Linux (SSH from Mac)

On macOS, `isActionMod()` accepts `key.meta` / `key.super` (Cmd). On Linux, it only accepts `key.ctrl`. When a Mac user connects via SSH/cmux, Cmd+C arrives with `key.meta=true` but the TUI ignores it because `isMac` is false on the server.

### Fix

In `lib/platform.ts`, extend `isActionMod` to accept `meta`/`super` on Linux when running over SSH:

```typescript
export const isActionMod = (key: { ctrl: boolean; meta: boolean; super?: boolean }): boolean =>
  isMac ? key.meta || key.super === true : key.ctrl || (isRemoteShell() && (key.meta || key.super === true))
```

This makes Cmd+C work as copy (when there's a selection) over SSH, while Ctrl+C remains interrupt/clear/exit.

### Copy-on-select is macOS-only

`useMainApp.ts` line ~164: `if (!isMac) return` — copy-on-select only runs on macOS. On Linux (even remote), the user must select text THEN press Ctrl+C (or Cmd+C with the fix above).

## `.bashrc` Auto-Attach Pitfall (Multi-Instance TUI)

Root's `~/.bashrc` may contain an auto-attach block:
```bash
if [ -z "$TMUX" ] && [ -n "$SSH_TTY" ] && [ "$TERM" != "dumb" ]; then
    exec tmux attach -t hermes
fi
```

This **hijacks** any `sudo -i bash -lc 'hermes --tui'` — bash reads `.bashrc`, auto-attaches to the existing `hermes` session, and the `hermes --tui` command never runs. Every new cmux pane becomes a mirror of the same session.

**Fix:** Use `bash --norc` with `--preserve-env` to bypass `.bashrc`:
```bash
sudo --preserve-env=HERMES_HOME,HERMES_TUI_FORCE_OSC52,PATH,SSH_CONNECTION,DISPLAY,WAYLAND_DISPLAY \
  -u root bash --norc -c 'cd /root && hermes --tui; exec bash'
```

**Pitfall:** The SSH user is typically `ubuntu` (not root), so `~/bin/start-hermes-root-new` resolves to `/home/ubuntu/bin/`, NOT `/root/bin/`. Always write the script to the SSH user's home directory.

## cmux Shortcut: Independent TUI Panes

To launch independent `hermes --tui` instances from a Mac shortcut via cmux:

**Mac-side script** (`~/bin/start-hermes-cmux`):
```bash
#!/usr/bin/env bash
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
open -a cmux
# Wait for cmux to be ready
i=0; while [ "$i" -lt 60 ]; do "$CMUX" list-workspaces >/dev/null 2>&1 && break; sleep 0.25; i=$((i+1)); done
CMD="ssh -tt -o ClearAllForwardings=yes walter-ts 'bash ~/bin/start-hermes-root-new'"
OUT=$("$CMUX" new-split right --focus true 2>&1)
SURFACE=$(echo "$OUT" | grep -o "surface:[0-9]\\+" | head -1)
sleep 0.5  # let the new pane's shell start
if [ -n "$SURFACE" ]; then
  "$CMUX" send --surface "$SURFACE" "$CMD
"
else
  "$CMUX" send "$CMD
"
fi
```

**VPS-side script** (`/home/ubuntu/bin/start-hermes-root-new`):
```bash
#!/usr/bin/env bash
SESSION="hermes-$(cat /proc/sys/kernel/random/uuid | cut -d- -f1)"
tmux new-session -d -s "$SESSION" \
  "sudo --preserve-env=HERMES_HOME,HERMES_TUI_FORCE_OSC52,PATH,SSH_CONNECTION,DISPLAY,WAYLAND_DISPLAY \
  -u root bash --norc -c 'cd /root && hermes --tui; exec bash'"
tmux set-option -t "$SESSION" allow-passthrough on
tmux set-option -t "$SESSION" set-clipboard on
tmux set-option -t "$SESSION" status off
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
tmux attach-session -t "$SESSION"
```

**Key points:**
- UUID session names (`hermes-63b963e1`) guarantee uniqueness — no collisions
- `--norc` bypasses `.bashrc` auto-attach
- `--preserve-env` passes required env vars without sourcing `.bashrc`
- Each pane gets its own independent tmux session + hermes process
- `new-workspace --command` is an alternative but creates a separate workspace (not a split)

**Pitfall:** Do NOT use `date + $$` for session names — if two clicks happen in the same second, the sessions collide and share a tmux session (mirror effect).

## cmux-Notify: Event Filtering (No Per-Tool Spam)

The cmux-notify system sends macOS notifications when the TUI needs attention. By default, the patch fires on every tool completion — too noisy. Filter to only: `message.complete`, `error`, `background.complete`, `clarify.request`. Differentiate with a `reason` field (`"complete"` vs `"input"`).

For the full implementation (backend, frontend, types, apply script), see `references/cmux-notify-event-filtering.md`.

### cmux-notify: DCS Passthrough for tmux

When the TUI runs inside tmux, the `cmux-notify` binary must wrap its OSC escape sequence in tmux's **DCS passthrough** format. Without this, writing to `/dev/pts/N` goes into tmux's pane input buffer and never reaches the SSH client.

**The chain:** `cmux-notify` → write to tmux pane pts → tmux reads from pty master → DCS passthrough → ubuntu tmux → SSH → cmux → Mac terminal.

**Why direct pts writes fail:** Writing to `/dev/pts/N` where tmux is the server doesn't forward escape sequences to the SSH client. Tmux reads from the pty master side and processes output internally. Only DCS passthrough sequences (prefixed with `ESC P tmux ;`) are forwarded to the outer terminal.

**Correct `cmux-notify` implementation:**
```bash
#!/usr/bin/env bash
title="${1:-Hermes}"
body="${2:-Terminé}"

# Build raw OSC notification sequence
RAW_OSC=$(printf '\033]777;notify;%s;%s\007' "$title" "$body")

# Wrap in tmux DCS passthrough: ESC P tmux ; <data> ESC \
# This tells tmux to forward the inner sequence to the outer terminal
# Requires: tmux set-option -g allow-passthrough on (already set)
PASS_THROUGH=$(printf '\033Ptmux;%s\033\\' "$RAW_OSC")

# Write to tmux pane ptys (passthrough wrapper makes tmux forward to SSH client)
for session in $(tmux list-sessions -F '#{session_name}' 2>/dev/null); do
  pane_tty=$(tmux list-panes -t "$session" -F '#{pane_tty}' 2>/dev/null | head -1)
  if [ -n "$pane_tty" ] && [ -w "$pane_tty" ]; then
    printf '%s' "$PASS_THROUGH" > "$pane_tty" 2>/dev/null
  fi
done
```

**Pitfall: Two tmux servers.** Root has `/tmp/tmux-0/default`, ubuntu has `/tmp/tmux-1001/default`. When the TUI process runs as root (via `sudo`), `tmux` commands connect to root's server. The passthrough chain is: root tmux → ubuntu tmux → SSH → cmux → Mac terminal. Both must have `allow-passthrough on`.

**Pitfall: `printf` escaping.** The `\\` in `printf '\033Ptmux;%s\033\\'` produces a literal `\` (ESC backslash = ST). The `$RAW_OSC` variable already contains the processed escape characters from the earlier `printf`. Double-check with `printf ... | xxd` to verify the byte sequence: `1b 50 74 6d 75 78 3b ... 1b 5c`.

## Clipboard over SSH / cmux

When the TUI runs on a remote VPS accessed via cmux (or SSH), clipboard operations need special setup. cmux is a terminal multiplexer that runs on the Mac and connects to the VPS via SSH. The tmux on the VPS runs as the `ubuntu` user (NOT root).

### Chain: cmux (Mac) → SSH → tmux (VPS, ubuntu user) → sudo -i → hermes --tui

**Problem 1: `sudo -i` strips `SSH_CONNECTION`**
- tmux's `update-environment` only applies to NEW sessions from SSH, but `sudo -i` resets the environment
- Fix: Add sudoers rule `/etc/sudoers.d/keep-ssh-env`:
  ```
  Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"
  ```
- Also add fallback to root's `~/.bashrc`:
  ```bash
  export SSH_CONNECTION="${SSH_CONNECTION:-127.0.0.1 PORT 127.0.0.1 22}"
  ```

**Problem 2: tmux runs as ubuntu, reads ubuntu's `~/.tmux.conf`**
- Root's `~/.tmux.conf` is IGNORED by tmux running as ubuntu
- Fix `/home/ubuntu/.tmux.conf`:
  ```
  set -g allow-passthrough on
  set -g set-clipboard on
  set -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
  ```

**Problem 3: xclip needs DISPLAY (not available on headless VPS)**
- xclip/xsel fail silently without X11 server
- OSC 52 is the correct path for remote sessions
- Set `HERMES_TUI_FORCE_OSC52=1` in root's `~/.bashrc`

**Problem 4: `isActionMod()` only accepts Cmd (meta/super) on macOS**
- On Linux, `key.meta` from Cmd+C is ignored
- Fix in `platform.ts`: also accept `key.meta` when `isRemoteShell()` is true:
  ```typescript
  export const isActionMod = (key: { ctrl: boolean; meta: boolean; super?: boolean }): boolean =>
    isMac ? key.meta || key.super === true : key.ctrl || (isRemoteShell() && (key.meta || key.super === true))
  ```

**Problem 5: Links don't open (xdg-open missing on headless VPS)**
- `openExternalUrl()` tries xdg-open which doesn't exist
- Fix: copy URL to clipboard via OSC 52 as fallback when open command fails

**Launcher script must set tmux options BEFORE creating session:**
```bash
#!/usr/bin/env bash
SESSION="hermes-$(date +%Y%m%d-%H%M%S)-$$"
tmux set-option -g allow-passthrough on
tmux set-option -g set-clipboard on
tmux set-option -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
tmux new-session -d -s "$SESSION" "sudo -i bash -lc 'cd /root && hermes --tui; exec bash'"
tmux attach-session -t "$SESSION"
```

**Pitfall:** `tmux set-environment` after session creation does NOT affect existing panes. Environment must be set before spawning the shell, or injected via the command itself.

