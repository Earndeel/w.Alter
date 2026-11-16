# hermes-tui-customization — Welcome box / SessionPanel, two-column and responsive ASCII art, the CLI compact banner, logo pitfalls.

Moved verbatim from SKILL.md on 2026-11-01.

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

