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

## Section Defaults (Thinking / Tools / Activity)

File: `domain/details.ts` → `SECTION_DEFAULTS`

Controls whether the thinking reasoning and tool call accordions are open or closed by default. Users must click to expand/collapse at runtime.

### Auto-Collapse Timer (Deprecated — use Rolling Window instead)

The old auto-collapse timer used `setTimeout` + `busy` dependency to collapse everything after 4s. This fought with the `visible` sync effect and collapsed too aggressively. **Replaced by the Rolling Window pattern below.**

### Per-Tool Sub-Accordions

To make EACH tool call individually collapsible within the "Tool calls" parent accordion (instead of a flat `●` list), wrap each `Group` in a `TreeNode` with its own chevron header:

```tsx
// Track per-tool open state
const [openToolCalls, setOpenToolCalls] = useState<Set<string>>(new Set())

// In the tools panel render:
render: rails => (
  <Box flexDirection="column">
    {groups.map((group, index) => {
      const branch: TreeBranch = index === groups.length - 1 ? 'last' : 'mid'
      const isOpen = openToolCalls.has(group.key)

      const toggleTool = () => {
        setOpenToolCalls(prev => {
          const next = new Set(prev)
          if (next.has(group.key)) next.delete(group.key)
          else next.add(group.key)
          return next
        })
      }

      return (
        <TreeNode
          branch={branch}
          header={
            <Box onClick={toggleTool}>
              <Text color={group.color} wrap="truncate-end">
                <Text color={t.color.accent}>{isOpen ? '▾ ' : '▸ '}</Text>
                {group.emoji ? <Text color={t.color.accent}>{group.emoji} </Text> : null}
                {isOpen ? group.content : compactPreview(group.label, 60)}
              </Text>
            </Box>
          }
          key={group.key}
          open={isOpen}
          rails={rails}
          t={t}
        >
          {childRails => (
            <Box flexDirection="column">
              {group.details.map((detail, detailIndex) => (
                <Detail {...detail} branch={...} key={detail.key} rails={childRails} t={t} />
              ))}
            </Box>
          )}
        </TreeNode>
      )
    })}
  </Box>
)
```

**Update `expandAll`** to also open all individual tool calls:
```tsx
if (visible.tools !== 'hidden') {
  setOpenTools(true)
  setOpenToolCalls(new Set(groups.map(g => g.key)))
}
```

### Two-Line Reasoning Limit

To cap reasoning display at ~2 lines, change the `cot` computation in `ToolTrail` and the `Thinking` component mode:

```tsx
const THINKING_2LINE_MAX = 140  // ~2 lines on typical terminal
const cot = useMemo(() => thinkingPreview(reasoning, 'truncated', THINKING_2LINE_MAX), [reasoning])

// In the Thinking component call:
<Thinking mode="truncated" ... />
```

Also update `SubagentAccordion` thinking calls to use `mode="truncated"` for consistency.

### Tool Emojis in the TUI Header

The `ToolTrail` component renders active tools with their per-tool emoji (`💻 terminal`, `📖 read_file`, etc.). To also show tool emojis in the collapsed "Tool calls" section header (the `Chevron`), add emoji collection logic before the `panels.push()` in `thinking.tsx`:

```tsx
if (hasTools && visible.tools !== 'hidden') {
    const toolEmojis = [...new Set(groups.map(g => g.emoji).filter(Boolean))]
    const emojiPrefix = toolEmojis.length > 0 ? toolEmojis.slice(0, 3).join('') + ' ' : ''
    panels.push({
      header: (
        <Chevron
          // ...existing props...
          title={`${emojiPrefix}Tool calls`}
        />
      ),
```

This shows up to 3 unique tool emojis as a prefix on the section header: `▸ 💻📖🔧 Tool calls (3)` instead of `▸ Tool calls (3)`.

**Pitfall:** the restore script copies `thinking.tsx` from `~/.hermes/tui-overrides/`. After making this change, snapshot it with:
```bash
cp ~/.hermes/hermes-agent/ui-tui/src/components/thinking.tsx ~/.hermes/tui-overrides/thinking.tsx
```

### Tool Emojis in the TUI (active tools during execution)

The TUI shows per-tool emojis for active (in-progress) tools. The full pipeline is implemented:

**Backend** (`tui_gateway/server.py` — `_on_tool_start`):
```python
from agent.display import get_tool_emoji
payload["emoji"] = get_tool_emoji(name)
```

**TypeScript types** — `emoji?: string` on `ActiveTool` in `types.ts` and on the `tool.start` payload in `gatewayTypes.ts`.

**Event handler** (`createGatewayEventHandler.ts`):
```tsx
turnController.recordToolStart(ev.payload.tool_id, ev.payload.name ?? 'tool', ev.payload.context ?? '', ev.payload.emoji)
```

**Turn controller** (`turnController.ts`):
```tsx
recordToolStart(toolId: string, name: string, context: string, emoji?: string) {
  this.activeTools = [...this.activeTools, { context, emoji, id: toolId, name, startedAt: Date.now() }]
}
```

**ToolTrail rendering** (`thinking.tsx`):
```tsx
const emoji = tool.emoji || '⚡'
// renders: {emoji} {spinner} {label} ({elapsed})
```

**Emoji source:** `get_tool_emoji()` in `agent/display.py` checks:
1. Active skin's `tool_emojis` overrides
2. Tool registry's per-tool `emoji` field (set in `registry.register(..., emoji="💻")`)
3. Default `"⚡"` fallback

Most built-in tools have emojis registered: `💻` terminal, `📖` read_file, `✍️` write_file, `🔧` patch, `🔎` search_files, `🔀` delegate_task, `🌐` browser, `🐍` code_execution, `🧠` memory, `📚` skills, `📨` send_message, `❓` clarify, `📋` kanban.

**Pitfall:** the restore script (`~/.hermes/scripts/restore-tui-design.sh`) copies `types.ts` from `~/.hermes/tui-overrides/`, which may be stale and strip the `emoji` field. After restore, re-check `types.ts` for all custom fields.

```typescript
// Built-in defaults — override with `display.sections.<name>` in config.yaml
const SECTION_DEFAULTS: SectionVisibility = {
  thinking: 'collapsed',   // 'expanded' | 'collapsed' | 'hidden'
  tools: 'collapsed',      // 'expanded' | 'collapsed' | 'hidden'
  activity: 'hidden'       // ambient meta — usually noise
  // subagents: not set → falls through to global details_mode
}
```

**Resolution order:** explicit `display.sections.<name>` in config.yaml → `SECTION_DEFAULTS` → global `details_mode`.

Users can also toggle at runtime with `/details <section> expanded|collapsed|hidden`.

To change defaults, edit `SECTION_DEFAULTS` in `domain/details.ts` and rebuild.

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

## Link Rendering — Show Raw URLs (components/markdown.tsx)

By default, the TUI renders links as underlined text with a slugified title (via `urlSlugTitleLabel` or `useLinkTitle` page-title fetch). The user sees underlined text like "Docs" but not the actual URL. This is frustrating when trying to copy or verify links.

**Fix:** In `markdown.tsx`, change `defaultLinkLabel` to return the raw URL, and disable `useLinkTitle` fetching:

```tsx
// Before: slugified title
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : /^https?:\/\//i.test(url) ? urlSlugTitleLabel(url) : url

// After: raw URL
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

In `ResolvedLink`, remove the `useLinkTitle` hook:

```tsx
// Before
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const fetched = useLinkTitle(url)
  const display = fetched || fallbackLabel || defaultLinkLabel(url)
  // ...

// After
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  // ...
```

Clean up unused imports: remove `urlSlugTitleLabel` and `useLinkTitle` from the `externalLink.js` import.

**Behavior after fix:**
- Bare URLs (`https://example.com/path`) → full URL shown, underlined, accent color
- Markdown links (`[click here](https://...)`) → "click here" shown (the link text is the `fallbackLabel`)
- Autolinks (`<https://...>`) → full URL shown

**Pitfall:** `useLinkTitle` fetches page titles via HTTP HEAD requests in the background. Removing it eliminates network calls for every link in the response — a minor performance win.

## Markdown Styling (components/markdown.tsx)

Inline bold (`**text**`) and headings (`# title`) can be styled for more contrast:

**Bold inline** (line ~158, MdInline function): change from bare `bold` to `bold` + color:
```tsx
// Before: <Text bold key={...}>
// After:  <Text bold color={t.color.gold} key={...}>
```

**Headings** (line ~387, HEADING_RE match + SETEXT_RE): add underline for extra distinction:
```tsx
// Before: <Text bold color={t.color.amber} key={...}>
// After:  <Text bold color={t.color.gold} underline key={...}>
```

Using `t.color.gold` (#FFD700) vs `t.color.cornsilk` (#D0FBFE body text) creates visible contrast on dark terminals. `amber` works too but `gold` is brighter.

## Bordered Input Area (components/appLayout.tsx)

The TextInput (line ~224) sits inside a bare `<Box position="relative">`. Wrap it with a border:

```tsx
<Box borderStyle="round" borderColor={ui.theme.color.bronze} flexDirection="column" paddingX={1} marginTop={1}>
  {/* existing prompt + TextInput here */}
</Box>
```

Subtract 2 extra columns from TextInput `columns` prop (was `cols - pw - 2`, becomes `cols - pw - 4`) to account for the border + paddingX.

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

## Welcome Box / SessionPanel

The startup welcome screen is composed of two parts rendered inside the intro row in `appLayout.tsx`:
- `Banner` — standalone title + subtitle (can be removed if SessionPanel handles it)
- `SessionPanel` — the bordered `╭──╮` box showing session info

**Key files:**
- `ui-tui/src/components/branding.tsx` — `Banner`, `SessionPanel`, `Panel` components
- `ui-tui/src/types.ts` — `SessionInfo` interface (data contract from backend)
- `tui_gateway/server.py` — `_session_info(agent)` function builds the dict sent to the TUI
- `ui-tui/src/components/appLayout.tsx` — renders intro row with `<Banner>` + `<SessionPanel>`

### Modifying the Welcome Box

To replace "Available Tools / Skills" with custom content (e.g. recent sessions):

1. **Extend `_session_info()` in `server.py`** — add new data to the dict (query `SessionDB`, etc.)
2. **Add type in `types.ts`** — extend `SessionInfo` interface with new optional fields
3. **Rewrite `SessionPanel` in `branding.tsx`** — replace `section()` calls with your custom JSX
4. **Remove `Banner` from `appLayout.tsx`** if the title/subtitle now live inside `SessionPanel`

The `SessionInfo` type is the data contract between Python backend and TypeScript frontend. All fields are optional — the backend wraps each section in `try/except`, so failures are graceful.

### Clickable Recent Sessions

To make session lines in the welcome box clickable (click to resume):

1. **Add `onResume` prop to `SessionPanel`** in `branding.tsx`:
   ```tsx
   interface SessionPanelProps {
     info: SessionInfo
     onResume?: (id: string) => void  // ← add this
     sid?: string | null
     t: Theme
   }
   ```

2. **Add `onClick` handler** on session `<Box>` elements (NOT `onMouseDown` on `<Text>` — use the same pattern as thinking/tool call triangles):
   ```tsx
   <Box key={s.id} justifyContent="center" onClick={() => onResume?.(s.id)}>
     <Text color={t.color.cornsilk} wrap="truncate">
       {label}
     </Text>
   </Box>
   ```

   **Pitfall:** Do NOT use `onMouseDown` on `<Text>` — it depends on mouse tracking and has
   reliability issues. `onClick` on `<Box>` is the standard pattern throughout the codebase
   (thinking.tsx, agentsOverlay.tsx) and works via Ink's native event system.

3. **Pass `actions.resumeById` from `appLayout.tsx`**:
   ```tsx
   <SessionPanel
     info={row.msg.info}
     onResume={actions.resumeById}   // ← add this
     sid={ui.sid}
     t={ui.theme}
   />
   ```

Works with or without mouse tracking enabled (onClick on Box uses Ink's native event system).

### Date/Time Display Preference

**User preference (Lucas):** Use the **fixed format** (`DD/MM HH:mm`). Relative/cron-style timestamps ("just now", "5m ago") are rejected.

When displaying timestamps (e.g. `last_active` from `list_sessions_rich()`), add a helper in the component file:

```tsx
function relativeTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${day}/${month} ${hour}:${minute}`
}
```

**Never** use relative time ("just now", "5m ago", "2h ago") — the user explicitly rejects cron-style timestamps.

### Recent Sessions Grid (2×3) in Welcome Box

To display recent sessions as a grid in `SessionPanel`, you need both frontend and backend changes:

**Backend (`tui_gateway/server.py`):** Extend `_session_info()` to query the session DB. Use `source="tui"` to show ONLY TUI sessions (not CLI, Telegram, cron, gateway, tool):
```python
try:
    db = _get_db()
    if db:
        current_sid = getattr(agent, "session_id", None)
        sessions = db.list_sessions_rich(
            source="tui",
            limit=7,  # fetch 7 to exclude current, show 6
        )
        recent = []
        for s in sessions:
            if s.get("id") == current_sid:
                continue
            if len(recent) >= 6:
                break
            recent.append({
                "id": s.get("id", ""),
                "title": s.get("title") or ((s.get("preview") or "")[:30] + "…") or "—",
                "preview": (s.get("preview") or "")[:50],
                "last_active": s.get("last_active") or s.get("started_at") or 0,
                "message_count": s.get("message_count") or 0,
                "source": s.get("source") or "",
            })
        info["recent_sessions"] = recent
except Exception:
    pass
```

**Source filter:** Use `source="tui"` (positive filter) — NOT `exclude_sources`. TUI sessions are created with `source="tui"` (see `server.py` line ~2808: `db.create_session(..., source="tui")`). This excludes CLI, Telegram, Discord, cron, gateway, and all other sources in one shot. The user explicitly rejected showing CLI or Telegram sessions.

**Title fallback chain:** The `title` field is often NULL (`title_generator` doesn't run on every session). The three-tier fallback ensures every card has readable text:
```python
"title": s.get("title") or ((s.get("preview") or "")[:30] + "…") or "—",
```
This ensures every card has readable text instead of bare "—". If the user explicitly sets titles (e.g. via `/title`), those are preserved. The fallback chain is: BDD title → first 30 chars of preview + "…" → "—".
2. First 30 chars of `preview` + `…` (most common case)
3. `"—"` only if preview is also empty (rare)

**Pitfall:** Don't use `s.get("title") or "—"` — this was the original code and produced cards with bare "—" when title was NULL but preview had content.

**Frontend card layout — exactly 2 lines, centered, no border:**
- Line 1: title (bold, accent color, centered, truncated)
- Line 2: `DD/MM HH:mm · N msg` (muted, dim, centered, truncated)
- No preview line (avoids repetition when title falls back to preview)
- No border around cards (user explicitly rejected borders)
- Each card wrapped in `<Box marginX={1}>` for spacing
- Each text line wrapped in `<Box justifyContent="center" width={cardWidth}>` for horizontal centering

**Types (`ui-tui/src/types.ts`):** Add the data contract:
```typescript
export interface RecentSession {
  id: string
  title: string
  preview: string
  last_active: number
  message_count: number
  source: string
}

export interface SessionInfo {
  // ... existing fields ...
  recent_sessions?: RecentSession[]
}
```

**Frontend (`components/branding.tsx`):** Render as 2×3 grid (2 columns, 3 rows):
```tsx
function SessionCard({ s, t, cardWidth, onResume }: { s: RecentSession; t: Theme; cardWidth: number; onResume?: (id: string) => void }) {
  const title = (s.title || '—').slice(0, Math.max(10, cardWidth - 2))
  const ago = relativeTime(s.last_active)  // "DD/MM HH:mm" — no relative/cron
  const msgs = s.message_count ? `${s.message_count} msg` : ''

  return (
    <Box flexDirection="column" width={cardWidth} onClick={() => onResume?.(s.id)}>
      <Box justifyContent="center" width={cardWidth}>
        <Text bold color={t.color.accent} wrap="truncate">{title}</Text>
      </Box>
      <Box justifyContent="center" width={cardWidth}>
        <Text color={t.color.muted} dimColor wrap="truncate">{ago}{msgs ? ` · ${msgs}` : ''}</Text>
      </Box>
    </Box>
  )
}

export function SessionPanel({ info, sid, t, onResume }: SessionPanelProps) {
  const cols = useStdout().stdout?.columns ?? 100
  const frameInnerWidth = Math.max(0, cols - 6) // 2 border + 4 padding
  const showLogo = frameInnerWidth >= LOGO_MAX_WIDTH
  const showSessions = cols >= 58

  const cardWidth = showSessions
    ? Math.min(36, Math.max(22, Math.floor((cols - 10) / 2)))
    : 28

  const recent = info.recent_sessions ?? []
  const rows: RecentSession[][] = []
  for (let i = 0; i < recent.length; i += 2) { rows.push(recent.slice(i, i + 2)) }

  return (
    <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" paddingX={2} paddingY={1}>
      {showLogo && WALTER_LOGO.map((line, i) => (
        <Box key={i} justifyContent="center" width={frameInnerWidth}>
          <Text color="#03DFE8" dimColor={i >= 4}>{line}</Text>
        </Box>
      ))}
      {!showLogo && (
        <Box justifyContent="center">
          <Text bold color="#03DFE8">W.Alter</Text>
        </Box>
      )}
      {/* top lines */}

      {showSessions && rows.length > 0 && (
        <>
          <Box justifyContent="center" marginTop={1}>
            <Text bold color={t.color.primary}>Recent Sessions</Text>
          </Box>
          {rows.map((row, ri) => (
            <Box key={`r${ri}`} flexDirection="row" justifyContent="center" marginTop={1}>
              {row.map(s => (
                <Box key={s.id} marginX={1}>
                  <SessionCard s={s} t={t} cardWidth={cardWidth} onResume={onResume} />
                </Box>
              ))}
            </Box>
          ))}
        </>
      )}
    </Box>
  )
}
```

**Key points:**
- Fetch 7 from DB to exclude the current session and still show 6
- 2 columns × 3 rows = better fit for narrow terminals
- Card width is calculated dynamically and capped: `Math.min(36, Math.max(22, Math.floor((cols - 10) / 2)))`
- **Only 2 lines per card** — title + date/msg. No preview line (avoids repetition when title falls back to preview).
- **No border on cards** — flat layout. The user explicitly rejected borders.
- Each card's text lines are wrapped in `<Box justifyContent="center" width={cardWidth}>` for proper horizontal centering.
- Cards are spaced with `<Box marginX={1}>` between them.
- `wrap="truncate"` everywhere to prevent overflow on resize
- Logo responsiveness: compute `frameInnerWidth = cols - 6` (accounts for border + padding) and compare against `LOGO_MAX_WIDTH` (the actual max line length of the ASCII art). Do NOT hardcode pixel thresholds like `cols >= 55`.
- Sessions hidden on terminals < 58 cols (`showSessions` flag)
- Logo hidden when `frameInnerWidth < LOGO_MAX_WIDTH`, replaced by plain "W.Alter" text
- **Logo alignment:** Each ASCII line must be rendered inside `<Box justifyContent="center" width={frameInnerWidth}>` to force centering within the rounded frame. Do NOT rely on bare `justifyContent="center"` without an explicit width — Ink may left-align long ASCII lines.
- **Character width:** Ensure the ASCII art has no leading/trailing spaces that break alignment. The 6th line of the W.Alter logo had a leading space that caused misalignment; it was removed.
### Cleanup When Removing Components

When removing `Banner` or `ArtLines`, also clean up:
- Unused imports in `branding.tsx` (e.g. `artWidth`, `logo`, `LOGO_WIDTH`, `caduceus`, `CADUCEUS_WIDTH`, `flat`)
- The `<Banner t={ui.theme} />` line in `appLayout.tsx`
- The `Banner` import in `appLayout.tsx`

## Two-Column ASCII Art Layout in Welcome Box

When combining a left-side graphic (e.g. caduceus) with right-side content (logo, text, sessions) in the `SessionPanel`, **don't** use `flexDirection="row"` with nested `<Box>` columns — Ink's layout engine doesn't reliably align ASCII art across separate boxes.

**Working pattern:** Build a flat `rows[]` array and render each row as a single `<Text>` with left (graphic) and right (content) segments joined by `padEnd()`:

```tsx
const CADUCEUS = ['line1', 'line2', ...]  // 15 lines
const LOGO = ['line1', 'line2', ...]      // 6 lines
const CW = 30  // fixed width for caduceus column

// Build content lines below the logo
const contentLines = [
  { text: '' },
  { text: 'subtitle', color: t.color.dim },
  // sessions, commits, footer...
]

const totalRows = Math.max(CADUCEUS.length, LOGO.length + contentLines.length)
const rows = []
for (let i = 0; i < totalRows; i++) {
  const left = (CADUCEUS[i] || '').padEnd(CW)
  if (i < LOGO.length) {
    rows.push({ left, right: LOGO[i], rColor: '#03DFE8', rDim: i >= 4 })
  } else {
    const cl = contentLines[i - LOGO.length]
    rows.push({ left, right: cl?.text || '', rColor: cl?.color, rBold: cl?.bold })
  }
}

// Render
{rows.map((r, i) => (
  <Text key={i}>
    <Text color={t.color.gold}>{r.left}</Text>
    <Text color={r.rColor} bold={r.rBold} dimColor={r.rDim}>{r.right}</Text>
  </Text>
))}
```

**Why this works:** Each row is a single `<Text>` element with inline `<Text>` children. Ink renders them left-to-right in the same row. `padEnd(CW)` ensures consistent column width regardless of braille character display width.

**Why `flexDirection="row"` fails:** Nested `<Box>` elements with ASCII art don't guarantee vertical alignment — Ink's flex layout may add unexpected spacing or misalign lines when the content heights differ.

## Responsive Welcome Box (narrow terminals)

The two-column caduceus + logo layout overflows on terminals < 95 columns. Use a responsive approach:

```tsx
const showLogo = cols >= 55     // show full ASCII logo
const showSessions = cols >= 70 // show recent sessions grid

if (showLogo) {
  // Full ASCII art logo centered
  return (
    <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" paddingX={2} paddingY={1}>
      {WALTER_LOGO.map((line, i) => (
        <Box key={i} justifyContent="center">
          <Text color="#03DFE8" dimColor={i >= 4}>{line}</Text>
        </Box>
      ))}
      {/* content... */}
    </Box>
  )
} else {
  // Very narrow: plain text logo, no sessions grid
  return (
    <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" paddingX={2} paddingY={1}>
      <Box justifyContent="center">
        <Text bold color="#03DFE8">W.Alter</Text>
      </Box>
      {/* content... */}
    </Box>
  )
}
```

**Breakpoints used in practice:**
- `< 55 cols` → ASCII logo hidden, plain text "W.Alter" shown
- `< 70 cols` → Recent sessions grid hidden entirely
- `>= 70 cols` → Full layout with logo + sessions grid

Card width is calculated dynamically: `Math.max(20, Math.floor((cols - 12) / 2))` for the 2×3 grid.

Always add `wrap="truncate"` on `<Text>` elements to prevent overflow on resize.

## Scroll & Resize Tuning

### Wheel scroll step (`config/limits.ts`)

`WHEEL_SCROLL_STEP` controls how many lines each wheel tick scrolls. Default is 3.
For smoother scrolling, reduce to 1:

```typescript
export const WHEEL_SCROLL_STEP = 1  // was 3 — smoother trackpad/wheel feel
```

### Resize stability (`hooks/useVirtualHistory.ts`)

`FREEZE_RENDERS` controls how many render cycles the virtual scroller freezes the mount
range after a column resize (to let Yoga reflow stabilize). Default is 2. If text disappears
or jumps after resize, increase to 4:

```typescript
const FREEZE_RENDERS = 4  // was 2 — better resize stability
```

The resize handler (useMainApp.ts) debounces `terminal.resize` RPC to gateway at 100ms.
The virtual history scales cached heights by `prevColumns / columns` ratio and skips one
measurement cycle to avoid poisoning the cache with pre-reflow Yoga heights.

## Backend: Live Todo Panel Updates

The TUI shows a live todo panel (`LiveTodoPanel` in `streamingAssistant.tsx`) that displays the agent's current task list. By default, it only updates when the agent explicitly calls the `todo` tool. After the initial plan is created, the agent executes steps (read_file, write_file, etc.) without calling `todo` again — the panel stays frozen.

**Fix:** Inject the current agent todo store into **every** `tool.complete` event, not just `todo` tool completions. In `tui_gateway/server.py`, `_on_tool_complete()`:

```python
if name == "todo":
    try:
        data = json.loads(result)
        if isinstance(data, dict) and isinstance(data.get("todos"), list):
            payload["todos"] = data.get("todos")
    except Exception:
        pass
else:
    # Always include current agent todos so the TUI live todo panel
    # stays fresh even when the agent does not explicitly call todo.
    agent = session.get("agent") if session else None
    if agent is not None:
        try:
            todo_store = getattr(agent, "_todo_store", None)
            if todo_store is not None:
                current_todos = todo_store.read()
                if current_todos:
                    payload["todos"] = current_todos
        except Exception:
            pass
```

**Why this works:** The frontend's `turnController.recordTodos()` is called on every `tool.complete` event (see `createGatewayEventHandler.ts`). By attaching the current todo list to every tool completion, the live panel refreshes after each step automatically — no frontend changes needed.

**Pitfall:** Do not emit empty `todos: []` — only include the field if `current_todos` is non-empty. This avoids clearing the panel when the agent has no active todos.

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

## Post-Update Design Recovery

Hermes updates run `git stash` automatically before pulling new code. If you modified TUI source files (e.g. `branding.tsx`, `banner.ts`, `messageLine.tsx`), they disappear after update because the working tree is reset to upstream.

For a detailed walkthrough of a real recovery session (v0.12.0, 2026-05-06), see `references/post-update-recovery-session-20260506.md`.

For the SSH clipboard fix walkthrough (cmux, tmux, sudo -i, OSC 52 chain), see `references/ssh-clipboard-fix-20260517.md`.

### 1. Find the autostash
```bash
cd ~/.hermes/hermes-agent
git stash list
# Pattern: stash@{N}: On main: hermes-update-autostash-YYYYMMDD-HHMMSS
# stash@{0} is always the most recent (the current update)
```

### 2. Inspect what the stash touched
```bash
# Show only TUI files
git stash show stash@{0} --name-only | grep ui-tui

# Diff a specific file against current HEAD
git diff HEAD stash@{0} -- ui-tui/src/components/branding.tsx
```
### 3. Extract selectively (preferred — avoids conflicts)
Do **not** run `git stash pop` blindly — it can fail on working-tree conflicts or untracked files, and the stash may be incompatible with the new version.

```bash
# Reset TUI to clean post-update state first
git checkout HEAD -- ui-tui/src/

# Extract only the files you want from the stash
git checkout stash@{0} -- ui-tui/src/components/branding.tsx
git checkout stash@{0} -- ui-tui/src/components/appLayout.tsx
git checkout stash@{0} -- ui-tui/src/components/messageLine.tsx
git checkout stash@{0} -- ui-tui/src/components/thinking.tsx
git checkout stash@{0} -- ui-tui/src/components/markdown.tsx
git checkout stash@{0} -- ui-tui/src/domain/details.ts
git checkout stash@{0} -- ui-tui/src/types.ts
git checkout stash@{0} -- ui-tui/src/app/createGatewayEventHandler.ts
git checkout stash@{0} -- ui-tui/src/gatewayTypes.ts
```

**Files commonly customized and worth checking:**
| File | What it controls |
|------|------------------|
| `components/branding.tsx` | `Banner`, `SessionPanel`, `Panel` — startup welcome box |
| `components/appLayout.tsx` | Layout of transcript, composer, overlays — whether `Banner` renders, composer borders |
| `components/messageLine.tsx` | Message bubbles, prefixes, role styling (user-right-align, assistant-left) |
| `domain/details.ts` | `SECTION_DEFAULTS` — whether thinking/tools are expanded/collapsed by default |
| `types.ts` | `SessionInfo`, `RecentSession`, `ActiveTool.emoji` — data contracts |
| `components/thinking.tsx` | Rolling window, emoji headers, sub-accordions, Spinner running prop |
| `components/markdown.tsx` | Link rendering (URL display, useLinkTitle), inline bold, headings |
| `components/markdown.tsx` | Link rendering (raw URLs vs slugified titles), bold/heading styling |
| `createGatewayEventHandler.ts` | Emoji passthrough to recordToolStart |
| `gatewayTypes.ts` | Emoji in tool.start payload type |
| `platform.ts` | `isActionMod`, `isCopyShortcut`, `isRemoteShell` — Cmd+C over SSH fix |
| `openExternalUrl.ts` | Link clicking — OSC 52 clipboard fallback for headless servers |
| `banner.ts` | `CADUCEUS_ART`, `LOGO_ART`, `colorize()` — ASCII art and color gradients |
| `banner.ts` | `CADUCEUS_ART`, `LOGO_ART`, `colorize()` — ASCII art and color gradients |
| `theme.ts` | `DARK_THEME` / `LIGHT_THEME` hardcoded defaults |
| `tui_gateway/server.py` | `_session_info()` — backend data sent to the TUI (recent sessions, etc.) |

**Backend files are NOT in the stash** — if you added `recent_sessions` or other backend-side data to `_session_info()`, those changes live in `tui_gateway/server.py` which is NOT captured by `git stash` (it's in the repo but the stash only captures the *pre-update* working tree). You must re-apply backend patches separately. The restore script handles this automatically — see `templates/restore-tui-design.sh`.

### 4. Verify compatibility immediately
```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
```

**If the build fails with type errors** (e.g. `Property 'X' does not exist on type 'Y'`, `Module has no exported member`), the stash is **incompatible** — the TUI internals changed between versions. In that case:
1. Reset the file(s): `git checkout HEAD -- ui-tui/src/`
2. Re-read the current source
3. Re-apply your design changes manually against the new API

**If the build fails with "No matching export in ... for import ...":** This means upstream **removed or renamed** an export that your override files still reference. The restore script blindly copies override files into the repo without checking compatibility. This is the #1 cause of broken restores after updates.

**Diagnosis + fix workflow:**
1. Read the error: `No matching export in "src/config/X.ts" for import "SYMBOL_NAME"` tells you exactly which symbol died
2. Find the upstream commit: `git log --all --oneline --diff-filter=M -- ui-tui/src/config/X.ts | head -5` then `git show <commit> -- ui-tui/src/config/X.ts` to see what changed
3. If the commit is a merge, check the PR message: `git show <commit>` — the PR description often explains the rationale (e.g. "no history truncation" = `FULL_RENDER_TAIL_ITEMS` removed because all messages now render full text)
4. Update the override files in `~/.hermes/tui-overrides/` (NOT the repo copies — those get overwritten each restore):
   - Remove the dead import
   - Update the usage to match the new API (e.g. `boundedHistoryRenderText(msg.text)` → `msg.text` when truncation is removed)
   - Remove any props that referenced the dead symbol from component interfaces
5. Re-run the restore script to copy + rebuild

**Pitfall:** The restore script's `npm run build` will report errors but the script itself exits 0 (because `npm run build` pipes through `tail -5` which swallows the exit code). Always check the build output visually — "Done" at the end does NOT mean the build succeeded.

For a concrete example (v0.14.0, 2026-05-21: `FULL_RENDER_TAIL_ITEMS` and `boundedHistoryRenderText` removed by PR #28829), see `references/override-compat-fix-20260521.md`.

### 5. What survives vs what doesn't

| Survives update? | Location | Why |
|------------------|----------|-----|
| ✅ Yes | `~/.hermes/skins/<name>.yaml` | Outside the git repo |
| ✅ Yes | `~/.hermes/config.yaml` `display:` section | Outside the git repo |
| ❌ No | `ui-tui/src/**/*.tsx` `ui-tui/src/**/*.ts` | Inside repo, reset on update |
| ❌ No | `cli.py`, `banner.py`, etc. | Inside repo, reset on update |
| ✅ Yes | `/etc/sudoers.d/keep-ssh-env` | Outside the repo — preserves SSH_CONNECTION through sudo |
| ✅ Yes | `/home/ubuntu/.tmux.conf` | Outside the repo — tmux config for ubuntu user |

### 6. Permanent workaround: backup dir + restoration script
For designs that require source modifications, maintain copies outside the repo and a rebuild script:

```bash
# 1. Create backup directory
mkdir -p ~/.hermes/tui-overrides

# 2. After each design change, snapshot the files
cp ui-tui/src/components/branding.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/appLayout.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/messageLine.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/thinking.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/markdown.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/markdown.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/domain/details.ts ~/.hermes/tui-overrides/
cp ui-tui/src/types.ts ~/.hermes/tui-overrides/
cp ui-tui/src/app/createGatewayEventHandler.ts ~/.hermes/tui-overrides/
cp ui-tui/src/gatewayTypes.ts ~/.hermes/tui-overrides/

# 3. Create restoration script at ~/.hermes/scripts/restore-tui-design.sh
#    (see templates/restore-tui-design.sh in this skill for a ready-to-use script)
```
```

**Usage after future updates:**
```bash
hermes update && bash ~/.hermes/scripts/restore-tui-design.sh
```

**Belt-and-suspenders guard (recommended):** add `/root/.hermes/scripts/ensure-tui-design.sh` and call it from `/root/bin/start-hermes-root-new` before launching `hermes --tui`. The guard compares `~/.hermes/tui-overrides/*` against the live repo files; if an update reset them, it runs `restore-tui-design.sh` automatically. This covers updates launched outside the `.bashrc` `hermes()` wrapper (for example from inside a TUI or a non-interactive shell).

Also set `set -euo pipefail` in `restore-tui-design.sh`; otherwise `npm run build 2>&1 | tail -5` can mask a failed build because `tail` exits 0. Tiny shell foot-gun, naturally.

This is more reliable than stash recovery because:
- It doesn't depend on the stash still existing (stashes can be dropped)
- It handles API changes gracefully — if a file no longer exists, the `cp` fails early and you know manual porting is needed
- It rebuilds automatically, so you verify immediately
- It re-applies backend patches (`server.py`) which are NOT captured by git stash

See also `templates/restore-tui-design.sh` in this skill for a ready-to-use script.
See also `references/cmux-multi-instance-launcher.md` for the macOS cmux → VPS multi-instance TUI launcher pattern.

## Link Rendering (components/markdown.tsx)

By default, the TUI renders markdown links as underlined text with a slugified title (e.g. `urlSlugTitleLabel` turns `https://example.com/path/to/docs` into "Docs"). Users who want to see the full URL should:

1. In `defaultLinkLabel`, remove the `urlSlugTitleLabel` call — just return the raw URL
2. In `ResolvedLink`, remove `useLinkTitle` — don't fetch page titles
3. Remove unused imports (`urlSlugTitleLabel`, `useLinkTitle`)

After: bare URLs show the full URL underlined, markdown links `[text](url)` still show the link text.

## Build & Apply

After modifying TUI source:

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build              # Compiles TypeScript + bundles Ink

# Reinstall the package so changes take effect:
cd ~/.hermes/hermes-agent
./venv/bin/python -m pip install -e .   # Use venv python directly (see pitfall #3)
```

## CLI Compact Banner (`cli.py` → `_build_compact_banner()`)

The **CLI banner** (not the Ink TUI) is built in `cli.py`. It's a Rich-formatted bordered box shown when `--compact` or terminal < 80 columns. Separate from the Ink/React TUI welcome screen.

### Adding Multi-Line ASCII Art to the Banner

**Gotcha:** Rich `[style]...\n...[/]` tags do NOT apply styles across newlines. Each line of a multi-line art piece needs its own border characters and styling.

**Pattern:**
```python
# Store art as plain strings (no Rich markup)
WALTER_LOGO_LINES = [
    "██╗    ██╗    █████╗ ██╗  ████████╗███████╗██████╗",
    "██║    ██║   ██╔══██╗██║  ╚══██╔══╝██╔════╝██╔══██╗",
    # ... more lines ...
]

# In _build_compact_banner(), render each line with borders
logo_lines = "\n".join(
    f"[bold {border_color}]║[/] [#03DFE8]{line}[/] [bold {border_color}]║[/]"
    for line in WALTER_LOGO_LINES
)
# Use ╠═══╣ to separate logo from text sections
return (
    f"\n[bold {border_color}]╔{bar}╗[/]\n"
    f"{logo_lines}\n"
    f"[bold {border_color}]╠{bar}╣[/]\n"  # separator
    f"[bold {border_color}]║[/] [{title_color}]{line1}[/] [bold {border_color}]║[/]\n"
    # ...
)
```

### Key files
- `cli.py` line ~1618: `_build_compact_banner()` — compact bordered box
- `cli.py` line ~1591: `HERMES_AGENT_LOGO` / `HERMES_CADUCEUS` — existing art constants
- `hermes_cli/banner.py` line ~361: `build_welcome_banner()` — full banner with caduceus + tools

## ASCII Art Logo Pitfalls

When adding ASCII art logos to the TUI (e.g. block-character art like `██╗`), watch for alignment issues:

- **Character width ambiguity:** Box-drawing chars (`╗║═╝╚╔`) and block chars (`█`) have `east_asian_width = A` (Ambiguous). Most terminals treat them as 1 cell wide, but some may treat them as double-width. Always verify alignment in the actual terminal.
- **First line offset:** The top line of block art (using `╗` corners) often has different spacing than subsequent lines (using `║` verticals). Compare character positions across lines — if the first line's blocks don't align with lines 2+, adjust spacing between blocks on line 1 only.
- **Testing:** Print the logo in a Python loop showing `L1: [first 15 chars]` etc. to verify column alignment before deploying.
- **User-facing lesson:** When the user says "the first line is shifted one block," check the gap between the W and A sections — L1 often has 4 spaces while L2-L4 have 3. The fix is usually one space in that gap, not within the W itself. Verify with a character-position dump: `for i,c in enumerate(line[:15]): print(f'[{i}] {c}')`.

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

## Link clicking on headless servers

When the user clicks a link in the TUI, `openExternalUrl()` tries to run `xdg-open` (Linux) or `open` (macOS). On a headless VPS, `xdg-open` is typically not installed, and even if it were, the browser would open on the server, not the user's machine.

### Fix

In `lib/openExternalUrl.ts`, when no browser opener is available (or it fails), copy the URL to clipboard via OSC 52:

```typescript
function copyUrlToClipboard(url: string, dependencies: OpenDependencies = {}): boolean {
  const spawnFn = dependencies.spawn ?? spawn

  // Best-effort native clipboard write (silently fails without DISPLAY)
  try {
    const child = spawnFn('xclip', ['-selection', 'clipboard', '-in'], {
      stdio: ['pipe', 'ignore', 'ignore']
    })
    child.stdin?.end(url)
    child.once('error', () => {})
    child.unref()
  } catch {}

  // OSC 52 — travels over SSH to the local terminal
  const b64 = Buffer.from(url, 'utf8').toString('base64')
  process.stdout.write(`\x1b]52;c;${b64}\x07`)

  return true
}
```

Wired into `openExternalUrl`:
- `if (!command)` → calls `copyUrlToClipboard()` instead of returning false
- `child.once('error', ...)` → calls `copyUrlToClipboard()` as fallback when xdg-open fails

## Link Rendering: Show Raw URLs

By default, the TUI's markdown renderer transforms URLs into friendly labels:
- `urlSlugTitleLabel(url)` extracts a title-like slug from the path (e.g. `https://example.com/docs` → "Docs")
- `useLinkTitle(url)` fetches the page's `<title>` tag and shows that instead

**User preference: show the raw URL.** When the user can't see the full URL, they can't verify where a link goes or copy it.

### Fix in `components/markdown.tsx`

1. **`defaultLinkLabel`** — return the URL as-is, don't slugify:
```tsx
// Before:
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : /^https?:\/\//i.test(url) ? urlSlugTitleLabel(url) : url

// After:
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

2. **`ResolvedLink`** — remove `useLinkTitle` hook entirely:
```tsx
// Before:
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const fetched = useLinkTitle(url)
  const display = fetched || fallbackLabel || defaultLinkLabel(url)
  // ...
}

// After:
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  // ...
}
```

3. **Clean imports** — remove `urlSlugTitleLabel` and `useLinkTitle` from the import line.

**Result:** `[click here](https://example.com/path)` shows "click here" (underlined). Bare `https://example.com/path` shows the full URL (underlined). No more hidden URLs.

**Pitfall:** If you keep `useLinkTitle`, it fetches page titles over the network and replaces URLs with titles like "Hermes Agent Documentation" — the user can't see where the link goes.

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

## Composer Input Border / Frame

The user-input area (`TextInput` inside `ComposerPane`) has **no explicit border by default**. It sits as a flat row of text prefixed by the prompt glyph (`❯` or `$`). If the user says "the input area is no longer framed," check two things:

1. **Was there ever a border?** Search git history for `borderStyle` in `appLayout.tsx`. Upstream Hermes has never shipped a border around the composer — the "frame" the user remembers may have been:
   - The `StatusRule` separator line (`─`) directly above the input, which can *look* like a top border when the terminal is wide.
   - A transient overlay (approval prompt, etc.) that had a border and gave the impression the input itself was framed.
   - A previous local patch that was lost during `hermes update` (the update stashes local changes).

2. **Is the separator line invisible?** The `StatusRule` (appChrome.tsx) draws `─` characters in `t.color.border`. On light-terminal profiles, or after commit `4cc6da84a` (ANSI256 normalization), the border color may be remapped to a tone very close to the background, making the separator disappear. This creates the *illusion* that a frame was removed.

### Adding a Border Around the Composer

To add an actual border, wrap the input block in `appLayout.tsx` (~line 246, inside `ComposerPane`):

```tsx
{!isBlocked && (
  <Box
    borderColor={ui.theme.color.border}
    borderStyle="single"
    flexDirection="column"
    paddingX={1}
    width={Math.max(1, composer.cols - 2)}
  >
    {composer.inputBuf.map((line, i) => (
      <Box key={i}>
        <Box width={promptWidth}>
          {/* prompt prefix logic */}
        </Box>
        <Text color={ui.theme.color.text}>{line || ' '}</Text>
      </Box>
    ))}

    <Box
      onMouseDown={captureInputDrag}
      onMouseDrag={dragFromPromptRow}
      onMouseUp={endInputDrag}
      position="relative"
      width={Math.max(1, composer.cols - 2)}
    >
      <Box width={promptWidth}>{/* prompt prefix */}</Box>
      <Box flexGrow={0} flexShrink={0} height={inputHeight} width={inputColumns}>
        <TextInput
          columns={inputColumns}
          mouseApiRef={inputMouseRef}
          onChange={composer.updateInput}
          onPaste={composer.handleTextPaste}
          onSubmit={composer.submit}
          placeholder={composer.empty ? PLACEHOLDER : ui.busy ? 'Ctrl+C to interrupt…' : ''}
          value={composer.input}
        />
      </Box>
      <Box position="absolute" right={0}>
        <GoodVibesHeart t={ui.theme} tick={status.goodVibesTick} />
      </Box>
    </Box>
  </Box>
)}
```

**Column math:** The outer `Box` with `paddingX={1}` + `borderStyle="single"` consumes 4 columns (left border + left pad + right pad + right border). If you previously sized `TextInput` at `cols - promptWidth - 2`, you may need to reduce it by another 2 so the text doesn't wrap prematurely inside the narrower inner width.

### Theme `border` Color Visibility on Light Terminals

Commit `4cc6da84a` ("normalize legacy Terminal.app colors") added ANSI256-safe color remapping. On terminals detected as light, the `border` token (`#7A4F1F` in `LIGHT_THEME`) is normalized through `normalizeAnsiForeground()` into an `ansi256()` value. If that mapped color is too close to the background, separator lines disappear.

**Quick diagnosis:**
- Run `echo $HERMES_TUI_THEME $HERMES_TUI_LIGHT $COLORFGBG` to check detection.
- Temporarily force dark theme: `HERMES_TUI_THEME=dark hermes --tui`. If the frame reappears, the issue is color normalization.
- Override the border color in your skin YAML to something darker/higher contrast on light backgrounds:
  ```yaml
  colors:
    banner_border: "#5A3A10"   # darker bronze for light terminals
  ```

## Rolling Window: Tool Calls & Thinking (Compact Live View)

Instead of auto-collapsing everything after a timer, use a "rolling window" that keeps the last N items expanded while older ones fold away.

### Pattern: Show Only Last 2 Tool Calls (hide older ones)

The user's preferred mode: the tools chevron shows only the 2 most recent tool calls. Older ones are hidden entirely (not just collapsed). Each visible call shows its emoji.

In the tools panel `render` function in `thinking.tsx`, slice `groups` to the last 2:

```tsx
render: rails => {
  // Only show the last 2 tool groups (rolling window)
  const visibleGroups = groups.slice(-2)
  const offset = groups.length - visibleGroups.length

  return (
    <Box flexDirection="column">
      {visibleGroups.map((group, vi) => {
        const index = offset + vi
        const branch: TreeBranch = vi === visibleGroups.length - 1 ? 'last' : 'mid'
        // ...rest of per-tool rendering unchanged
      })}
    </Box>
  )}
```

**Pitfall:** When changing from `render: rails => (` (expression) to `render: rails => {` (block), remember to close with `)}` not just `)`. The panel object's `render` property needs the closing brace + paren.

### Pattern: Thinking Spinner Visibility (No Frozen Spinner)

Reference: `references/tui-thinking-cmux-2026-05-18.md` captures the full session recipe, verification guards, cmux passthrough details, and restore-persistence checklist.

The user preference is: **show the spinner only while reasoning is live**. When thinking completes, remove the spinner entirely and leave a dim static `Thinking` label plus the cached/truncated thinking content. Do NOT use `running={false}` for completed thinking — it freezes a braille glyph on screen and looks broken.

```tsx
export function Spinner({ color, running = true, variant = 'think' }: { color: string; running?: boolean; variant?: 'think' | 'tool' }) {
  // ...
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)
    return () => clearInterval(id)
  }, [spin, running])
  // ...
}
```

In the thinking header, render the spinner only in the live branch:

```tsx
{thinkingLive ? (
  <Text bold color={t.color.text}>
    <Spinner color={t.color.accent} running variant="think" /> Thinking
  </Text>
) : (
  <Text color={t.color.muted} dim>Thinking</Text>
)}
```

**Pitfall:** If you remove `showDots`, also remove every JSX reference to it (notably `dim={!thinkingLive && !showDots}`). `npm run build` uses esbuild and may not type-check this; run a grep/type-check guard before shipping.

### Pattern: Sticky Thinking (No Auto-Collapse)

When the user wants thinking content to **stay visible** after completion (no auto-collapse timer), remove the `AUTO_COLLAPSE_DONE_MS` timeout entirely. The section opens when reasoning starts and only closes on manual click or next cycle:

```tsx
// ✅ Sticky — opens on start, never auto-closes
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

### Pattern: Thinking Auto-Open (NO auto-collapse)

Keep thinking open while streaming. **Never auto-collapse** — content stays visible until the user manually closes or a new thinking cycle starts. The spinner is rendered only while `thinkingLive` is true, then disappears.

```tsx
// Thinking section: open when active, NEVER close automatically
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])

// Header: spinner exists only while live
{thinkingLive ? <Spinner color={t.color.accent} running variant="think" /> : null}
```

The `Spinner` component signature:
```tsx
export function Spinner({ color, running = true, variant = 'think' }: {
  color: string; running?: boolean; variant?: 'think' | 'tool'
})
```

Do not use `running={false}` for completed thinking. The `AUTO_COLLAPSE_DONE_MS` constant should be removed entirely.

**When to use sticky:** User explicitly wants to read thinking content after it completes. The auto-collapse timer (`AUTO_COLLAPSE_DONE_MS = 3000`) collapses the section before the user can finish reading — remove it. Also remove the unused `AUTO_COLLAPSE_DONE_MS` constant.

**Pitfall:** If you remove auto-collapse but keep `openThinking` in the `visible` sync effect (line ~785), the section can still be collapsed by `/details thinking collapsed` or config overrides. This is correct — sticky only means "no timer-based collapse".

### Pattern: Last 2 Tool Calls Expanded

In `thinking.tsx`, use a rolling window for sub-accordion state:

```tsx
// Rolling window: keep last 2 sub-accordions expanded
const recentToolKeys = useMemo(
  () => new Set(tools.slice(-2).map(t => t.id)),
  [tools]
)

useEffect(() => {
  if (!tools.length) return
  // Keep only the last 2 tool sub-accordions open
  setOpenToolCalls(prev => {
    const prevArr = [...prev].sort()
    const newArr = [...recentToolKeys].sort()
    if (prevArr.length === newArr.length && prevArr.every((k, i) => k === newArr[i])) return prev
    return recentToolKeys
  })
}, [tools, recentToolKeys])
```

### Pattern: Thinking Auto-Open (Sticky — No Auto-Collapse)

Keep thinking open while streaming. Once done, it stays open (content visible) until the user manually clicks the chevron or a new thinking cycle starts. See "Sticky Thinking" above for the full pattern and rationale.

```tsx
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

**Deprecated pattern:** The old `AUTO_COLLAPSE_DONE_MS` timer collapsed thinking after 3 seconds, fighting with the `visible` sync effect and hiding content before the user could read it. Removed in favor of sticky.

### Pattern: Thinking Content Persistence Between Turns

When a new turn starts, `turnController.clearReasoning()` resets `reasoning` to `''`. This makes the thinking content disappear before the user can read it. Cache the last non-empty reasoning in a `useRef` to keep it visible until fresh reasoning arrives.

In `components/thinking.tsx`, add `useRef` to imports and create a caching mechanism:

```tsx
import { memo, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'

// Inside the ToolTrail component:
const cachedReasoningRef = useRef(reasoning)
useEffect(() => {
  if (reasoning) {
    cachedReasoningRef.current = reasoning
  }
}, [reasoning])

const displayReasoning = reasoning || cachedReasoningRef.current
const cot = useMemo(() => thinkingPreview(displayReasoning, 'truncated', THINKING_2LINE_MAX), [displayReasoning])
```

Then use `displayReasoning` instead of `reasoning` in the Thinking component render:

```tsx
render: rails => (
  <Thinking
    active={thinkingLive}
    branch="last"
    mode={thinkingLive ? 'full' : 'truncated'}
    rails={rails}
    reasoning={thinkingLive ? displayReasoning : cot}
    streaming={thinkingLive && reasoningStreaming}
    t={t}
  />
)
```

**Behavior:**
- Thinking starts → content streams in, spinner animates
- Thinking ends → spinner disappears, content stays visible as the truncated cached preview
- New turn starts → `reasoning` clears to `''`, but `displayReasoning` uses cached value → content remains
- New thinking starts → `reasoning` updates with fresh content → display updates

**Why `thinkingLive ? displayReasoning : cot`:** When actively reasoning, show the live/full bounded content (`displayReasoning`) so the current run writes in front of the user. When done, show the truncated preview (`cot`) — this prevents the section from showing a wall of text after completion.

### Pattern: Auto-Open Tools Section When Active

In the `visible` sync effect, keep tools open when tools are running:

```tsx
useEffect(() => {
  setOpenThinking(visible.thinking === 'expanded')
  setOpenSubagents(visible.subagents === 'expanded')
  setOpenMeta(visible.activity === 'expanded')
}, [visible.thinking, visible.subagents, visible.activity])

useEffect(() => {
  setOpenTools(visible.tools === 'expanded' || (visible.tools !== 'hidden' && tools.length > 0))
}, [visible.tools, tools.length])
```

**Pitfall:** Do not keep `tools.length` in the same effect that resets `openThinking`. Otherwise a tool start can collapse the thinking panel while reasoning is still in progress.

**Pitfall:** Do NOT add `openTools` to the rolling window effect dependencies — the `visible` sync effect handles open/close. The rolling window only manages sub-accordion state. Mixing them creates a toggle loop.

**Pitfall:** `groups` is built during render (not in a useMemo). Use `tools` as the useEffect dependency, not `groups`. `recentToolKeys` is derived from `tools` via useMemo so it's stable.

## Tool Emojis in Section Headers

The "Tool calls" Chevron header shows `▸ Tool calls (3)` by default. To show tool emojis in the header:

```tsx
if (hasTools && visible.tools !== 'hidden') {
  const toolEmojis = [...new Set(groups.map(g => g.emoji).filter(Boolean))]
  const emojiPrefix = toolEmojis.length > 0 ? toolEmojis.slice(0, 3).join('') + ' ' : ''
  panels.push({
    header: (
      <Chevron
        count={groups.length}
        // ...
        title={`${emojiPrefix}Tool calls`}
      />
    ),
    // ...
  })
}
```

Shows up to 3 unique emojis from the active tools. Example: `▸ 💻📖🔧 Tool calls (5)`.

**Note:** This runs inside the render body where `groups` is available. The `useMemo` for `recentToolKeys` runs before render (in the hooks section) and uses `tools`, not `groups`.

## Spinner `running` Prop (Legacy — Do Not Use For Completed Thinking)

The `Spinner` component accepts a `running` prop (default `true`). When `false`, the `setInterval` is not created and the spinner stays on its current frame. This can still be useful for niche tool indicators, but **not** for completed thinking: Lucas wants the spinner gone, not frozen.

```tsx
export function Spinner({ color, running = true, variant = 'think' }: { color: string; running?: boolean; variant?: 'think' | 'tool' }) {
  // ...
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)
    return () => clearInterval(id)
  }, [spin, running])
  // ...
}
```

Preferred thinking header pattern:
```tsx
{thinkingLive ? (
  <Spinner color={t.color.accent} running variant="think" />
) : ( /* dim static text, no spinner */ )}
```

### Remove Thinking Auto-Collapse

The old `AUTO_COLLAPSE_DONE_MS` timer (3s `setTimeout` to `setOpenThinking(false)`) fights with the `visible` sync effect. Remove it entirely — thinking stays expanded until the user manually collapses or a new thinking cycle starts:

```tsx
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

Delete the `AUTO_COLLAPSE_DONE_MS` constant entirely.

## Link Rendering: Show Full URLs

By default, the TUI transforms URLs into short labels via `urlSlugTitleLabel()` (extracts a title from the URL path) and `useLinkTitle()` (fetches the page's `<title>` tag). Users who want to see the actual URL can disable both.

In `components/markdown.tsx`:

1. **`defaultLinkLabel`** — return the raw URL instead of `urlSlugTitleLabel(url)`:
```tsx
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

2. **`ResolvedLink`** — skip `useLinkTitle()` entirely:
```tsx
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  return (
    <Link url={url}>
      <Text color={t.color.accent} underline>{display}</Text>
    </Link>
  )
}
```

3. **Clean up imports** — remove `urlSlugTitleLabel` and `useLinkTitle` from the `externalLink.js` import.

**Pitfall:** The restore script must include `markdown.tsx` in the overrides list since this file is now customized.

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

## Session Orchestrator (Ctrl+X)

The TUI has a **Session Orchestrator** overlay (`activeSessionSwitcher.tsx`) for managing multiple live sessions. It is NOT visible by default — users frequently can't find it.

**Open:** `Ctrl+X` or `/sessions` slash command.

**Capabilities:**
- Lists all active sessions with status glyphs: `✓` idle, `…` starting, `?` waiting, `▶` working
- Shows model name per session (short form: strips provider prefix)
- Create new session inline with prompt input
- Model picker (Tab) before launching a new session

**Keybindings:**
| Key | Action |
|-----|--------|
| ↑↓ | Navigate sessions |
| Enter | Switch to selected / start new |
| Ctrl+N | New session row |
| Ctrl+D | Close selected session |
| Ctrl+R | Refresh session list |
| Tab | Model picker (on new session row) |
| Esc | Close overlay |

**Source:** `ui-tui/src/components/activeSessionSwitcher.tsx` + mounted in `appOverlays.tsx` when `overlay.sessions` is true.

**Pitfall:** There is no visual indicator that Ctrl+X exists. Users must know the shortcut or use `/sessions`. The Kanban board has NO TUI component — it is CLI-only (`hermes kanban`) + gateway (`/kanban`) + dashboard plugin API.

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

## Rolling Window: Tool Calls & Thinking (Compact Live View)

Instead of auto-collapsing everything after a timer, use a "rolling window" that keeps the last N items expanded while older ones fold away.
3. **Rebuild required — pip path matters** — TypeScript changes need `npm run build` + `pip install -e .`. On this system the venv is Python 3.11 at `venv/bin/python` — `source venv/bin/activate && pip install -e .` may fail with PEP 668 if the system Python 3.12 takes over. Always use `./venv/bin/python -m pip install -e .` explicitly.
4. **`borderStyle="round"`** — Uses Unicode box-drawing characters (╭╮╰╯). Works in most modern terminals but may render as `+` in basic terminals.
5. **Bubble width** — Cap at `cols - 8` to avoid overflow on narrow terminals.
6. **Section defaults are code, not config** — Changing `SECTION_DEFAULTS` in `details.ts` requires a full rebuild. Runtime overrides via `display.sections` in config.yaml work without rebuild.
7. **"Frame disappeared after update"** — `hermes update` stashes local changes. If the user previously had a patched border around the composer, it was likely lost in the autostash. Check `git stash list` in `~/.hermes/hermes-agent` and re-apply the patch manually (do not blindly `git stash pop` — the TUI internals may have changed).
8. **Stash pop fails after update** — `git stash pop` often fails because the TUI internals changed (new components, renamed props, deleted files). Always use `git checkout stash@{0} -- <file>` to extract individual files. If that file no longer exists in the new version, the checkout will fail cleanly and you'll know you need to port manually.
9. **Props removed between versions** — The TUI API changes across releases. For example, `voiceRecordKey` was removed from `TextInput` props in v0.12.0. If a stashed patch references a deleted prop, the TypeScript build will fail with `Property 'voiceRecordKey' does not exist on type 'TextInputProps'`. Fix: remove the offending prop line and rebuild.
10. **Backend patches are invisible to git stash** — If you modified `_session_info()` in `tui_gateway/server.py` to send extra data (e.g. `recent_sessions`), those changes are inside the repo but `git stash` only captures the *pre-update* working tree. After `hermes update`, the backend resets to upstream and your custom data disappears even if you recover the frontend files. You must re-apply backend patches separately. See "Recent Sessions Grid" above for the exact Python code to re-inject.
11. **`compactPreview` needs a string, not ReactNode** — `group.content` is a `ReactNode`. Don't pass it to `compactPreview()`. Use `group.label` (a plain string) for the collapsed sub-accordion header.
12. **Restore script overwrites `types.ts`** — `~/.hermes/scripts/restore-tui-design.sh` copies `types.ts` from `~/.hermes/tui-overrides/`. If you added custom fields to types (e.g. `emoji` on `ActiveTool`, `recent_sessions` on `SessionInfo`), those are lost after restore. Keep `types.ts` in the tui-overrides backup or re-apply the type patches after restore.
13. **Restore script may downgrade the package** — the script runs `pip install -e .` which can install a stale cached wheel. Run `./venv/bin/python -m pip install -e .` again after restore to ensure the current version is installed.
14. **`source="tui"` vs `exclude_sources`** — TUI sessions have `source="tui"` (set in `server.py` line ~2808 and ~2020). Use `source="tui"` for filtering recent sessions instead of excluding sources — it's more precise and doesn't need updating when new sources are added.
15. **Rolling window vs auto-collapse timer** — The old auto-collapse timer (`setTimeout` + `busy` dependency) fights with the `visible` sync effect. Use the rolling window pattern instead: `useMemo` for `recentToolKeys` from `tools`, separate `useEffect` for sub-accordion state, and modify the `visible` sync effect to keep tools open when `tools.length > 0`.
16. **tmux runs as a different user** — On multi-user VPS setups (e.g. Oracle Cloud with `ubuntu` user), tmux runs as the SSH login user, NOT root. Editing `/root/.tmux.conf` has zero effect. Always check `ps aux | grep tmux` to find the owning user and edit THEIR `~/.tmux.conf`. This applies to `set-clipboard`, `allow-passthrough`, and `update-environment`.
17. **`sudo -i` strips SSH env vars** — When hermes is launched via `sudo -i bash -lc 'hermes --tui'`, SSH_CONNECTION/SSH_CLIENT/SSH_TTY are lost. Fix with `/etc/sudoers.d/keep-ssh-env` containing `Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"`.
19. **Restore script exit code masking** — The restore script uses `npm run build 2>&1 | tail -5` which swallows the build exit code. Even if the build fails with errors, the script continues and prints "Done." Always scroll up to check for "ERROR:" lines in the output.
20. **Override files drift after upstream API changes** — When upstream removes or renames exported symbols, the override files in `~/.hermes/tui-overrides/` become stale. The restore script blindly copies them and the build fails. This is NOT a "start from scratch" situation — find the upstream commit (`git log --oneline -- <file>`), see what changed, and update only the broken imports/props in the override files. See `references/override-compat-fix-20260521.md` for a concrete example.
17. **`groups` is not memoized** — `groups` is built during render (not in a `useMemo`). Effects that depend on tool IDs must use `tools` (the prop) with a `useMemo` derivation, not `groups` directly.
18. **SSH_CONNECTION default fallback in .bashrc** — When launching hermes from tmux that was created by the agent itself (not from an SSH session), `SSH_CONNECTION` won't be in the environment even with `update-environment`. The setting only picks up vars from the SSH session that created tmux — if tmux was started by `tmux new-session` from a non-SSH context, the vars are explicitly UNSET (prefix `-` in `tmux show-environment`). Fix: add `export SSH_CONNECTION="${SSH_CONNECTION:-127.0.0.1 45996 127.0.0.1 22}"` to root's `.bashrc` as a fallback.
14. **User wants full autonomy — "tu as toutes les clefs"** — When the user says to handle everything yourself (e.g. "tu fait tout tout seul", "tu as toutes les clefs"), do NOT ask them to run commands, restart services, or verify things manually. Execute the full fix chain end-to-end: edit config, kill tmux, restart hermes, verify the process env. Only report what was done, not what they should do. This applies especially to tmux restarts, hermes relaunches, and environment fixes — the user expects the agent to own the entire pipeline.
15. **Restore script source filter drift** — The restore script (`restore-tui-design.sh`) patches `server.py` via a Python heredoc. If you change the `source=` or `exclude_sources=` parameter in `server.py`, you MUST also update the restore script's heredoc to match. Otherwise the next `hermes update` + restore will silently revert to the old filter. The heredoc uses single-quoted `PYEOF` so Python double quotes pass through unescaped — do NOT backslash-escape them.
