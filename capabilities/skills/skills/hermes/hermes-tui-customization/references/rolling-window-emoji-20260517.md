# Session Notes: Rolling Window + Emoji Headers (2026-05-17)

## Changes Applied

### 1. Recent sessions filter: `source="tui"`
**Before:** `exclude_sources=["tool"]` — showed CLI, Telegram, cron, gateway sessions
**After:** `source="tui"` — shows only TUI sessions
**File:** `tui_gateway/server.py` → `_session_info()`

### 2. Title fallback chain
**Before:** `s.get("title") or "—"`
**After:** `s.get("title") or ((s.get("preview") or "")[:30] + "…") or "—"`
**Reason:** Many sessions had NULL titles, showing bare "—". Now falls back to preview text.

### 3. Rolling window for tool calls + thinking
**Replaced:** Auto-collapse timer (`setTimeout` 4s, `busy` dependency)
**With:** Rolling window pattern:
- `recentToolKeys = useMemo(() => new Set(tools.slice(-2).map(t => t.id)), [tools])`
- Effect keeps only last 2 sub-accordions open
- `visible` sync effect keeps tools section open when `tools.length > 0`
- Thinking opens while streaming, auto-collapses 3s after done

### 4. Tool emojis in Chevron header
**Before:** `▸ Tool calls (3)`
**After:** `▸ 💻📖🔧 Tool calls (3)`
**Implementation:** Collect unique emojis from `groups`, slice to 3, prefix the title.

## Pitfalls Encountered

1. **`groups` not available in hooks** — `groups` is built during render, not memoized. Had to derive `recentToolKeys` from `tools` prop via `useMemo`.

2. **`visible` sync effect fighting rolling window** — The original `visible` effect set `openTools(false)` on mount (since default is 'collapsed'). The rolling window effect then set it `true`. Fixed by merging: `openTools = expanded || (not hidden && tools.length > 0)`.

3. **Restore script stale `types.ts`** — The restore script copies `types.ts` from overrides. If `emoji` field is missing from `ActiveTool`, emojis silently fail. Override file was already up to date.

## Session 2026-05-17 (evening): Only Last 2 Tools + Thinking Dots

### Changes Applied

1. **Tools: only show last 2 groups** — `groups.slice(-2)` in the render function. Older tools disappear entirely (not just collapsed). Uses `visibleGroups` + `offset` for correct branch/rail rendering.

2. **Thinking: auto-collapse with dots animation** — Added `useEffect` that opens thinking while streaming (`reasoningActive || reasoningStreaming`) and auto-collapses 3s after done. Collapsed header shows `<Spinner variant="think" />` animation when `!openThinking && !thinkingLive && reasoning && !busy`.

3. **Thinking: truncated mode** — Changed from `mode="full"` to `mode="truncated"` with `THINKING_2LINE_MAX = 140` chars (~2 lines). Keeps the panel compact.

4. **Tool sub-accordions** — Each tool group now has a `TreeNode` with click-to-expand. Uses `openToolCalls` Set state and `toggleTool()` handler. `compactPreview(group.label, 60)` shown when collapsed.

### Pitfall: `read_file` returns line numbers
The `read_file` tool returns content with `     1|import ...` prefixes. Using `read_file` output directly in a Python script to rewrite a file will corrupt it (line numbers become part of the content). Use the `patch` tool instead for targeted edits.

### Pitfall: `replace_all=true` creates duplicates
When patching the SKILL.md, `replace_all=true` found 2 matches for a section header and inserted the new content twice. Always check match uniqueness or use `replace_all=false`.

## Files Modified
- `ui-tui/src/components/thinking.tsx` — rolling window + emoji header
- `tui_gateway/server.py` — `source="tui"` + title fallback
- `~/.hermes/scripts/restore-tui-design.sh` — synced with all changes
- `~/.hermes/tui-overrides/thinking.tsx` — backup synced

## Session 2026-05-18: Spinner `running` Prop + Sticky Thinking + Link URLs

### Changes Applied

1. **Spinner `running` prop** — Added optional `running` prop (default `true`) to `Spinner` component. When `false`, the `setInterval` animation stops. Used to freeze the thinking spinner when reasoning is done.

2. **Sticky thinking (no auto-collapse)** — Removed `AUTO_COLLAPSE_DONE_MS = 3000` timer entirely. Thinking section opens when reasoning starts and stays open until the user manually clicks or a new cycle starts. The old auto-collapse fought with user intent.

3. **Raw URL display** — Modified `components/markdown.tsx`:
   - `defaultLinkLabel()` now returns the URL as-is (no `urlSlugTitleLabel` slug extraction)
   - Removed `useLinkTitle()` hook from `ResolvedLink` (no more page title fetching)
   - Removed unused imports (`urlSlugTitleLabel`, `useLinkTitle`)
   - Result: bare URLs show full URL, markdown links show link text

### Files Modified
- `ui-tui/src/components/thinking.tsx` — `running` prop + sticky thinking
- `ui-tui/src/components/markdown.tsx` — raw URL display
- `~/.hermes/tui-overrides/thinking.tsx` — backup synced
- `~/.hermes/tui-overrides/markdown.tsx` — backup synced
