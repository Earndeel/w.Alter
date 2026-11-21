# Override Compatibility Fix — 2026-05-21

## Context
Hermes v0.14.0 update broke the TUI restore. `bash ~/.hermes/scripts/restore-tui-design.sh` reported "Done" but the TUI build had silently failed.

## Errors
```
src/components/appLayout.tsx:10:9: ERROR: No matching export in "src/config/limits.ts" for import "FULL_RENDER_TAIL_ITEMS"
src/components/messageLine.tsx:9:2: ERROR: No matching export in "src/lib/text.ts" for import "boundedHistoryRenderText"
```

## Root Cause
PR #28829 (`bb/tui-no-history-truncation`) — "fix(tui): render full assistant text in scrollback (no history truncation)" removed both symbols:
- `FULL_RENDER_TAIL_ITEMS` from `limits.ts` — was used to decide which messages to truncate
- `boundedHistoryRenderText` from `text.ts` — was the truncation function

The concept of "history truncation" was removed entirely. All messages now render full text.

## Upstream Diff (PR #28829)

**appLayout.tsx** — removed import + prop:
```diff
-import { FULL_RENDER_TAIL_ITEMS } from '../config/limits.js'
 ...
-  limitHistoryRender={row.index < transcript.historyItems.length - FULL_RENDER_TAIL_ITEMS}
```

**messageLine.tsx** — removed import, prop, and usage:
```diff
-import {
-  boundedHistoryRenderText,
-  boundedLiveRenderText,
+import {
+  boundedLiveRenderText,
```
```diff
-  limitHistoryRender = false,
```
```diff
-  <Md compact={compact} t={t} text={limitHistoryRender ? boundedHistoryRenderText(msg.text) : msg.text} />
+  <Md compact={compact} t={t} text={msg.text} />
```

**types interface** — removed prop:
```diff
-  limitHistoryRender?: boolean
```

## Fix Applied

Updated `~/.hermes/tui-overrides/appLayout.tsx`:
- Removed `import { FULL_RENDER_TAIL_ITEMS }` line
- Removed `limitHistoryRender={...}` prop from `<MessageLine>`

Updated `~/.hermes/tui-overrides/messageLine.tsx`:
- Removed `boundedHistoryRenderText` from import
- Removed `limitHistoryRender = false` from destructured props
- Changed `<Md text={limitHistoryRender ? boundedHistoryRenderText(msg.text) : msg.text} />` to `<Md text={msg.text} />`
- Removed `limitHistoryRender?: boolean` from interface

Then re-ran `bash ~/.hermes/scripts/restore-tui-design.sh` — build succeeded.

## Lesson
The restore script blindly copies override files without checking API compatibility. After any `hermes update`, if the build fails, check `git log` on the failing file to find the breaking PR, then update `~/.hermes/tui-overrides/` (not the repo copies) to match the new API.
