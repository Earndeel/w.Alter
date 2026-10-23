# Session Notes: TUI Post-Update Recovery (2026-05-06)

## Context
Hermes v0.12.0 update reset all TUI customizations. User (Lucas) was frustrated because this happens repeatedly. The autostash (`stash@{0}`) contained the pre-update working tree.

## Files Recovered from Stash
```bash
cd ~/.hermes/hermes-agent
git checkout stash@{0} -- ui-tui/src/components/branding.tsx
git checkout stash@{0} -- ui-tui/src/components/appLayout.tsx
git checkout stash@{0} -- ui-tui/src/components/messageLine.tsx
git checkout stash@{0} -- ui-tui/src/domain/details.ts
```

## Backend Patches Re-applied (NOT in stash)
`tui_gateway/server.py` resets to upstream on update. Two patches were re-applied:

### 1. Recent sessions in `_session_info()`
Injects `recent_sessions` array into the intro payload so the welcome panel can show a 2×3 grid.

### 2. Todo refresh in `_on_tool_complete()`
Attaches the agent's current `_todo_store` to **every** `tool.complete` event, not just `todo` tool completions. This keeps the live todo panel updated as the agent executes steps without explicitly calling `todo`.

## Iterative Fixes Applied During Session

### Logo responsiveness
**Problem:** ASCII logo misaligned on narrow terminals; hardcoded thresholds (`cols >= 55`) were wrong.
**Fix:**
- Remove leading space from line 6 of `WALTER_LOGO`
- Compute `LOGO_MAX_WIDTH = Math.max(...WALTER_LOGO.map(l => l.length))`
- Compute `frameInnerWidth = cols - 6` (border + padding)
- Show logo only when `frameInnerWidth >= LOGO_MAX_WIDTH`
- Wrap each logo line in `<Box justifyContent="center" width={frameInnerWidth}>`

### Session card layout
**Problem:** 3-line cards (title + preview + date) caused repetition when title fell back to preview.
**Fix:** 2-line cards only:
- Line 1: title (bold, accent, centered)
- Line 2: `DD/MM HH:mm · N msg` (muted, dim, centered)
- No preview line
- No border
- Cards spaced with `marginX={1}`

### Clickable sessions (rejected, then accepted, then rejected)
**Evolution:**
1. Added `onClick` + `onResume` → user rejected because cards got borders
2. Removed clickability entirely → user wanted them back
3. Re-added `onClick` on `<Box>` with **no border** → accepted
**Lesson:** `onClick` on `<Box>` works without any visual border. The user wants interactivity but no chrome.

### Date format preference (reinforced)
**User explicitly rejects:** relative/cron-style timestamps ("just now", "5m ago").
**Accepted format:** `DD/MM HH:mm` fixed. No conditional "today" logic.

### Todo panel frozen
**Root cause:** `tool.complete` only carried `todos` when the tool name was literally `"todo"`. After the initial plan, the agent runs `read_file`, `write_file`, etc. — the panel never updates.
**Fix:** Backend patch to inject `_todo_store.read()` into every `tool.complete` payload.

### Stash-only recovery insufficient
**Lesson:** Frontend files are in the stash, but backend patches (`server.py`) are NOT. The restoration script must patch both sides.

## Final Override File List
```
~/.hermes/tui-overrides/
  branding.tsx      # W.Alter logo, SessionPanel, SessionCard, RecentSession grid
  appLayout.tsx     # ComposerPane border, Banner removal
  messageLine.tsx   # User messages right-aligned
  details.ts        # thinking/tools collapsed by default
  types.ts          # RecentSession interface
```

## Restoration Script
`~/.hermes/scripts/restore-tui-design.sh` — see `templates/restore-tui-design.sh` in this skill for the canonical version.

Usage:
```bash
hermes update && bash ~/.hermes/scripts/restore-tui-design.sh
```
