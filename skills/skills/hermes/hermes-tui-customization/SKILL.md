---
name: hermes-tui-customization
description: Customize the Hermes TUI (terminal UI) — colors, message formatting, user bubbles, skin theming. Covers the Ink/React TUI source architecture, theme system, and how skins map to UI elements.
version: 1.4.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, customization, theme, skin, ink, react]
---

# Hermes TUI Customization

The Hermes TUI is built with **Ink** (React for terminals), located at `hermes-agent/ui-tui/src/`. This skill covers how to customize its appearance: colors, message formatting, user bubbles, and skin theming.

## Architecture

```
ui-tui/src/
├── theme.ts              # Theme interface + fromSkin() mapping
├── domain/roles.ts       # Per-role glyph/color (user, assistant, tool, system)
├── components/
│   ├── messageLine.tsx   # Message rendering (bubbles, prefixes, content)
│   ├── markdown.tsx      # Markdown rendering for assistant responses
│   ├── thinking.tsx      # Tool trail / reasoning display
│   └── appChrome.tsx     # Status bar, faces, context bar
├── config/               # Limits, constants
├── types.ts              # Msg, Role, etc.
└── entry.tsx             # TUI entry point
```

**Backend:** `tui_gateway/` (Python JSON-RPC server) serves data to the Ink frontend.

## Skin System

Skins are YAML files at `~/.hermes/skins/<name>.yaml`. The `fromSkin()` function in `theme.ts` maps skin colors to the theme.

### Skin Structure

```yaml
name: my-skin
description: My custom theme

colors:
  # Banner (startup screen)
  banner_border: "#03DFE8"
  banner_title: "#03DFE8"
  banner_accent: "#03DFE8"
  banner_dim: "#029BA8"       # Darker variant for secondary elements
  banner_text: "#D0FBFE"      # Light variant for text on dark bg

  # UI elements
  ui_accent: "#03DFE8"
  ui_label: "#6DD8E0"         # User message color in roles.ts
  ui_ok: "#4caf50"
  ui_error: "#ef5350"
  ui_warn: "#ffa726"

  # Messages
  prompt: "#D0FBFE"           # Prompt symbol color
  response_border: "#03DFE8"  # (legacy CLI only, not used by TUI)
  session_label: "#6DD8E0"
  session_border: "#029BA8"

  # Status bar
  status_bar_bg: "#0a0a2e"
  status_bar_strong: "#03DFE8"
  status_bar_dim: "#029BA8"
  status_bar_good: "#8FBC8F"
  status_bar_warn: "#03DFE8"
  status_bar_bad: "#FF8C00"
  status_bar_critical: "#FF6B6B"

  # Completion menu
  completion_menu_bg: "#0a0a2e"
  completion_menu_current_bg: "#1a2a66"
  completion_menu_meta_bg: "#0a0a2e"
  completion_menu_meta_current_bg: "#1a2a66"

branding:
  agent_name: "W.Alter"
  welcome: "Bienvenue ⚡"
  goodbye: "À bientôt ⚡"
  response_label: " ⚡ W.Alter "    # Legacy CLI label
  prompt_symbol: "⚡ ❯ "             # User input prefix (brand.prompt in TUI)
  help_header: "(⚡) Commandes"

tool_prefix: "┃"                      # Assistant message prefix (brand.tool in TUI)

tool_emojis:
  terminal: "🔷"
  web_search: "🔮"
  read_file: "📄"
  write_file: "📝"
  delegate_task: "🤖"

spinner:
  waiting_faces: ["(⏳)", "(⏳)", "(⏳)"]
  thinking_faces: ["(💭)", "(💭)", "(💭)"]
  thinking_verbs: ["réfléchis", "analyse", "optimise"]
  wings: [["⟪", "⟫"]]
```

### Skin → Theme Mapping (fromSkin in theme.ts)

| Skin key | Theme field | Used for |
|----------|-------------|----------|
| `banner_title` | `color.gold` | Banner title |
| `banner_accent` / `ui_accent` | `color.amber` | Accent highlights |
| `banner_border` | `color.bronze` | User bubble border, response borders |
| `banner_text` | `color.cornsilk` | Assistant text body, user bubble text |
| `banner_dim` | `color.dim` | Tool results, dimmed text |
| `ui_label` | `color.label` | User role prefix color |
| `prompt` | `color.prompt` | Prompt symbol color |
| `session_label` | `color.sessionLabel` | Session title |
| `session_border` | `color.sessionBorder` | Session border |
| `branding.prompt_symbol` | `brand.prompt` | Glyph before user input |
| `tool_prefix` | `brand.tool` | Glyph before assistant messages |
| `branding.agent_name` | `brand.name` | Display name |

## Role Rendering (domain/roles.ts)

```typescript
ROLE = {
  assistant: t => ({ body: t.color.cornsilk, glyph: t.brand.tool, prefix: t.color.bronze }),
  system:    t => ({ body: '', glyph: '·', prefix: t.color.dim }),
  tool:      t => ({ body: t.color.dim, glyph: '⚡', prefix: t.color.dim }),
  user:      t => ({ body: t.color.label, glyph: t.brand.prompt, prefix: t.color.label })
}
```

- `body` = text color
- `glyph` = symbol shown before the message
- `prefix` = color of the glyph

## User Message Bubbles

Default TUI shows all messages as flat lines with a prefix glyph. To add chat-style bubbles for user messages, modify `components/messageLine.tsx`:

```tsx
// User messages get a bubble with rounded borders, right-aligned
if (msg.role === 'user') {
  const bubbleWidth = Math.min(Math.max(20, msg.text.length + 4), cols - 8)

  return (
    <Box flexDirection="column" alignItems="flex-end" marginBottom={1} marginTop={1}>
      <Box
        borderStyle="round"
        borderColor={t.color.bronze}    // Uses banner_border from skin
        paddingX={1}
        paddingY={0}
        width={bubbleWidth}
        flexDirection="column"
      >
        <Text color={t.color.cornsilk} wrap="wrap">{msg.text}</Text>
      </Box>
    </Box>
  )
}
```

This creates a right-aligned bubble with rounded borders:
```
              ╭──────────────────╮
              │ ton message ici  │
              ╰──────────────────╯
┃ assistant response here...
```

## Config Files (`config/`)

```
config/
├── limits.ts     # Hard limits — LARGE_PASTE, LONG_MSG, MAX_HISTORY, THINKING_COT_MAX, WHEEL_SCROLL_STEP
├── env.ts        # Env var controls — HERMES_TUI_RESUME, HERMES_TUI_DISABLE_MOUSE, HERMES_TUI_NO_CONFIRM
└── timing.ts     # STREAM_BATCH_MS (16), REASONING_PULSE_MS (700)
```

## Content Files (`content/`)

```
content/
├── faces.ts        # Spinner faces (⏳, 💭, etc.)
├── verbs.ts        # Spinner verbs ("réfléchis", "analyse", etc.)
├── placeholders.ts # Input placeholder text
├── fortunes.ts     # Random welcome messages
├── hotkeys.ts      # Keyboard shortcuts
├── charms.ts       # Small animations
└── setup.ts        # Setup wizard text
```

## config.yaml → `display:` Section

```yaml
display:
  compact: false                  # Less spacing
  personality: kawaii             # Affects faces/spinner
  resume_display: full            # full | compact | minimal
  busy_input_mode: interrupt      # interrupt | queue | disabled
  bell_on_complete: false
  show_reasoning: true
  streaming: true
  final_response_markdown: strip  # strip | keep | render
  inline_diffs: true
  show_cost: false                # $ in status bar
  skin: walter-blue               # Skin file in ~/.hermes/skins/
  tool_progress: new              # new | all | none
  tool_preview_length: 0          # 0 = auto
  sections:                       # Override per-section defaults from here
    thinking: collapsed
    tools: collapsed
    activity: hidden
  details_mode: collapsed         # Global fallback mode
```

## Environment Variables

| Variable | Effect |
|----------|--------|
| `HERMES_TUI_FORCE_OSC52=1` | Force OSC 52 clipboard emission (required on headless VPS) |
| `HERMES_TUI_LIGHT=1` | Force light mode |
| `HERMES_TUI_DISABLE_MOUSE=1` | Disable mouse tracking |
| `HERMES_TUI_NO_CONFIRM=1` | Skip destructive confirmations |
| `HERMES_TUI_RESUME=<id>` | Resume session on startup |

## Native Features (no code needed)

- **Shift+Enter** — already inserts `\\n` in `textInput.tsx` line ~642. Plain `Enter` submits. Also supports Alt+Enter / Ctrl+Enter (depending on OS).
- **Mouse click** — already positions cursor via `offsetFromPosition()` in `textInput.tsx` line ~804. Enabled by default (disable with `HERMES_TUI_DISABLE_MOUSE=1`).
- **Wheel scroll** — `wheelUp`/`wheelDown` events scroll the transcript by `WHEEL_SCROLL_STEP` (3 lines, config/limits.ts). Properly handled in `useInputHandlers.ts` lines 267-273.

### Mouse Tracking Details

The TUI enables full SGR mouse tracking via `AlternateScreen` component (`@hermes/ink`):
- DEC 1000 (button press/release + wheel)
- DEC 1002 (button-motion / drag)
- DEC 1003 (all-motion / hover)
- DEC 1006 (SGR coordinate format)

Escape sequences are defined in `packages/hermes-ink/src/ink/termio/dec.ts`.

### Trackpad Scroll Acts Like Arrow Keys

**Symptom:** Scrolling with trackpad cycles through history instead of scrolling the transcript.

**First check — `tui_mouse` config:** If `tui_mouse: false` in `config.yaml`, mouse tracking is disabled entirely and all scroll events arrive as arrow keys. This is the #1 cause of "scroll cycles through history instead of scrolling conversation". Fix: `sed -i 's/tui_mouse: false/tui_mouse: true/' ~/.hermes/config.yaml`. Users can also toggle at runtime with `/mouse on` or `/scroll on`.

**Other root cause:** Some terminals convert trackpad scroll into up/down arrow keypresses instead of sending proper mouse wheel escape sequences, even when mouse tracking mode is active. The TUI receives `upArrow`/`downArrow` instead of `wheelUp`/`wheelDown`, which triggers history cycling (useInputHandlers.ts lines 294+).

**Terminal-specific fixes:**

| Terminal | Problem | Fix |
|----------|---------|-----|
| **iTerm2** | "Scroll wheel sends arrow keys in alternate screen" | Preferences → Profiles → Advanced → "Scroll wheel sends arrow keys when in alternate screen" → **No** |
| **Terminal.app** | No proper SGR mouse support | Switch to iTerm2 or kitty |
| **Alacritty** | Scroll interpreted as ↑↓ in alt screen | Check `mouse:` config section |
| **tmux** (local or remote) | Intercepts scroll events | `set -g mouse on` in tmux.conf |
| **VS Code terminal** | Scroll = ↑↓ by default | No direct fix; TUI has special keybinding setup for VS Code/Cursor/Windsurf |

**Diagnosis:** Run `cat -v` in the terminal, scroll, and check output. Proper mouse wheel sends `\e[<64;X;YM` / `\e[<65;X;YM` (SGR) or `\eMa` / `\eMb` (X10). Arrow keys send `\e[A` / `\e[B`.

## Build & Apply

After modifying TUI source:

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build              # Compiles TypeScript + bundles Ink

# Reinstall the package so changes take effect:
cd ~/.hermes/hermes-agent
./venv/bin/python -m pip install -e .   # Use venv python directly (see pitfall #3)
```

## Current System Values (W.Alter)

These are the tuned values on this system as of 2026-04-26:

| Setting | File | Value | Reason |
|---------|------|-------|--------|
| `WHEEL_SCROLL_STEP` | `config/limits.ts` | `1` | Smoother trackpad scroll (was 3) |
| `FREEZE_RENDERS` | `hooks/useVirtualHistory.ts` | `4` | Better resize stability (was 2) |
| `AUTO_COLLAPSE_DONE_MS` | `components/thinking.tsx` | removed | Sticky thinking — no auto-collapse, content stays visible until next cycle |
| Rolling window | `components/thinking.tsx` | Last 2 | Tool sub-accordions expanded (rolling) |
| `tui_mouse` | `~/.hermes/config.yaml` | `true` | Mouse tracking ON — required for wheel scroll |
| `HERMES_TUI_FORCE_OSC52` | `/root/.bashrc` | `1` | Force OSC 52 clipboard emission over SSH |
| `set-clipboard` | `/home/ubuntu/.tmux.conf` | `on` | tmux forwards OSC 52 to outer terminal |
| `allow-passthrough` | `/home/ubuntu/.tmux.conf` | `on` | tmux passes OSC 52 escape sequences through |
| `update-environment` | `/home/ubuntu/.tmux.conf` | `SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY` | tmux preserves SSH env vars |
| `env_keep` | `/etc/sudoers.d/keep-ssh-env` | `SSH_CONNECTION SSH_CLIENT SSH_TTY` | sudo -i preserves SSH env vars |

## Pitfalls

On a headless Linux VPS without X11/Wayland (`$DISPLAY` and `$WAYLAND_DISPLAY` both empty), the TUI's clipboard tools (xclip, xsel, wl-copy) all fail silently. Copy-paste between the remote TUI and the user's local Mac requires **OSC 52** — an escape sequence that tells the local terminal emulator to write to its clipboard.

### The Full Chain

```
hermes TUI → tmux passthrough → SSH → local terminal (iTerm2/Kitty/etc.)
```

Every link in this chain must be configured:

### 1. `HERMES_TUI_FORCE_OSC52=1` in root's `.bashrc`

Without this, `shouldEmitClipboardSequence()` in `hermes-ink/termio/osc.ts` checks `SSH_CONNECTION` first. If `SSH_CONNECTION` is missing (common — see below), OSC 52 emission is suppressed.

```bash
echo 'export HERMES_TUI_FORCE_OSC52=1' >> /root/.bashrc
```

### 2. tmux config — must match the USER running tmux, NOT root

**Pitfall:** On multi-user VPS setups, tmux often runs as a non-root user (e.g. `ubuntu`). The tmux config that matters is **that user's** `~/.tmux.conf`, not `/root/.tmux.conf`. Check with `ps aux | grep tmux` to see which user owns the tmux server process.

Required in the tmux-user's `~/.tmux.conf`:
```tmux
set -g allow-passthrough on
set -g set-clipboard on
set -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
```

- `allow-passthrough` — lets tmux forward OSC 52 escape sequences from inner panes to the outer terminal
- `set-clipboard` — enables tmux's clipboard integration with the outer terminal
- `update-environment` — preserves SSH env vars into new tmux sessions (they're lost by default if not in this list)

### 3. `sudo -i` strips SSH_CONNECTION

If hermes is launched via `sudo -i bash -lc 'hermes --tui'` (common pattern for running as root from a non-root tmux session), `sudo -i` strips `SSH_CONNECTION`. Fix with a sudoers drop-in:

```bash
cat > /etc/sudoers.d/keep-ssh-env << 'EOF'
Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"
EOF
chmod 440 /etc/sudoers.d/keep-ssh-env
visudo -c  # verify syntax
```

### 4. cmux considerations

cmux (terminal multiplexer) runs on the VPS as a non-root user. It has its own tmux environment sync (`_CMUX_TMUX_SYNC_KEYS`) but **does NOT sync `SSH_CONNECTION`** — only cmux-internal variables. The `update-environment` tmux setting is the correct path for SSH vars.

cmux itself should pass through OSC 52 sequences if the local terminal supports it.

### 5. Local terminal must support OSC 52

| Terminal | OSC 52 support |
|----------|---------------|
| iTerm2 | Yes, but disabled by default — enable in Preferences → Profiles → Terminal → "Applications in terminal may access clipboard" |
| Kitty | Yes (default) |
| WezTerm | Yes (default) |
| Ghostty | Yes (default) |
| VS Code terminal | Yes (default) |
| Terminal.app | **No** — does not support OSC 52 |

### Diagnosis checklist

```bash
# 1. Which user runs tmux?
ps aux | grep tmux | grep -v grep

# 2. Does the tmux-user's tmux.conf have set-clipboard?
cat /home/<user>/.tmux.conf

# 3. Is SSH_CONNECTION in tmux's environment?
sudo -u <user> tmux show-environment -g | grep SSH_CONNECTION

# 4. Does the hermes process have SSH_CONNECTION?
cat /proc/<hermes-pid>/environ | tr '\0' '\n' | grep SSH_CONNECTION

# 5. Does the hermes process have FORCE_OSC52?
cat /proc/<hermes-pid>/environ | tr '\0' '\n' | grep FORCE_OSC

# 6. Does sudo -i preserve SSH_CONNECTION?
SSH_CONNECTION="test" sudo -i bash -c 'echo $SSH_CONNECTION'
```

### How setClipboard() works (hermes-ink/termio/osc.ts)

The `setClipboard()` function tries **multiple paths simultaneously**:
1. **Native tools** (xclip/pbcopy) — skipped over SSH when `SSH_CONNECTION` is set
2. **tmux load-buffer** — loads into tmux paste buffer (paste with prefix+])
3. **OSC 52 escape sequence** — emitted via tmux passthrough if `allow-passthrough on`

With `HERMES_TUI_FORCE_OSC52=1`, path 3 always fires. With `set-clipboard on`, tmux forwards it to the outer terminal. With a terminal that supports OSC 52, the text lands in the local clipboard.

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/section-defaults-and-rolling-window.md` — Thinking / Tools / Activity section defaults, the rolling window (compact live view of tool calls and thinking), tool emojis in headers, the legacy spinner prop.
- `references/welcome-box-and-banner.md` — Welcome box / SessionPanel, two-column and responsive ASCII art, the CLI compact banner, logo pitfalls.
- `references/links-and-markdown.md` — Link rendering (raw/full URLs), markdown styling, clicking links on headless servers.
- `references/composer-and-layout.md` — Bordered input area and composer frame, scroll and resize tuning, live todo panel updates, the session orchestrator (Ctrl+X).
- `references/cmux-and-clipboard.md` — cmux launcher and shortcuts for parallel TUI sessions, cmux-notify filtering, clipboard over SSH, Cmd+C on remote Linux, the .bashrc auto-attach pitfall.
- `references/post-update-design-recovery.md` — Restoring the customised TUI design after a Hermes update.

