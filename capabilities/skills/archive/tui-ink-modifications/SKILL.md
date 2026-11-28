---
name: tui-ink-modifications
description: Modify Hermes TUI (Ink/React) rendering — pitfalls, user preferences, and safe patterns for thinking.tsx, text.ts, turnController.ts, messageLine.tsx
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [tui, ink, react, rendering, ui]
---

# TUI Ink Modifications

When modifying the Hermes TUI (Ink/React) components, follow these rules strictly.

## Critical Pitfalls

### 1. NEVER `git checkout` files with user customizations

The user has extensive TUI customizations across multiple files. Using `git checkout -- <file>` restores from HEAD and **destroys all user customizations** — borders, messages, logo, session grid, timestamps, etc.

**Safe approach**: Use `patch` (find-and-replace) on specific sections only. Never wholesale replace a file.

**Files with user customizations** (DO NOT checkout these):
- `ui-tui/src/components/appLayout.tsx` — rounded borders, input area
- `ui-tui/src/components/messageLine.tsx` — right-aligned user messages
- `ui-tui/src/components/branding.tsx` — W.ALTER logo, session cards
- `ui-tui/src/components/appChrome.tsx` — status indicator
- `ui-tui/src/theme.ts` — colors, brand
- `ui-tui/src/domain/roles.ts` — role glyphs

### 2. The `hermes update` stash/pop cycle

`hermes update` auto-stashes local changes and pops them after. This preserves user customizations. If a `git checkout` wipes a customized file, the stash pop will conflict and the user loses their changes permanently.

**Rule**: Only modify files you NEED to modify. Use targeted `patch` operations.

### 3. `execute_code` + `read_file` truncates at 500 lines

The `read_file` function in `execute_code` defaults to 500 lines. If you read a file and write it back, you'll truncate it. **Never use `write_file` on large TSX files via `execute_code`** — use the `patch` tool instead.

### 4. Build must happen AFTER all changes

```bash
cd /root/.hermes/hermes-agent/ui-tui && rm -f dist/entry.js && npm run build
```

The bundle (`dist/entry.js`) is loaded at Node.js process startup. Old processes use old bundles. After building, kill old processes.

## User Rendering Preferences

The user wants the TUI to look like the CLI feed:

1. **Thinking + tools in one continuous flow** — NOT separate collapsible panels
2. **Tree elbows (├─, └─)** for tool calls — keeps visual structure
3. **No "thinking" label everywhere** — just the content with elbows
4. **CLI-style emojis** — 💻 terminal, 🔍 search, 🔧 patch, 📖 read, ✍️ write
5. **No tokens display** — suppress `Σ ~125 total` and `~Xk tokens` labels
6. **No execution time** — remove `(2.1s)` from trail lines and active tools
7. **No collapsible panels** — thinking and tools should be always visible

## Key Files for Rendering

| File | What it controls |
|------|-----------------|
| `thinking.tsx` ToolTrail | Main rendering: thinking panel, tools panel, subagents, activity, Σ |
| `text.ts` `buildToolTrailLine` | Trail line format for completed tools |
| `turnController.ts` `completeTool` | What data is passed to trail line builder |
| `tui_gateway/server.py` `_on_tool_start` | Gateway sends emoji in `tool.start` event |
| `details.ts` `SECTION_DEFAULTS` | Default visibility (collapsed/expanded/hidden) |

## Gateway Emoji Fix

The gateway's `_on_tool_start` must send `emoji` in the `tool.start` payload. The registry emojis are NOT available at gateway level (tools not discovered yet). Use a static map + skin overrides:

```python
# In _on_tool_start, after _tool_progress_enabled check:
_DEFAULT_EMOJIS = {"terminal": "💻", "web_search": "🔍", "patch": "🔧", ...}
_skin_emojis = resolve_skin().get("tool_emojis", {})
emoji = _skin_emojis.get(name) or _DEFAULT_EMOJIS.get(name, "⚡")
payload["emoji"] = emoji
```

## Skin Emoji Override

The skin (`~/.hermes/skins/<name>.yaml`) can override tool emojis via `tool_emojis:` section. Remove `spinner.waiting_faces`, `spinner.thinking_faces`, `spinner.thinking_verbs` from the skin to avoid kawaii faces (💧, 🔷, ❄) polluting the feed.

## Build Verification

After building, verify the bundle contains changes:
```bash
grep -c 'cleanThinkingText' /root/.hermes/hermes-agent/ui-tui/dist/entry.js
grep -o 'tools: "expanded"' /root/.hermes/hermes-agent/ui-tui/dist/entry.js | head -1
```

Kill old processes after rebuild:
```bash
for pid in $(pgrep -f 'node.*entry\.js'); do kill $pid; done
```

User must `/quit` and relaunch `hermes --tui` for changes to take effect.

## Additional Pitfalls

### `buildToolTrailLine` emoji parameter
Default `buildToolTrailLine()` in `text.ts` has no emoji parameter. Add `emoji?: string` as 6th param, prepend `${emoji ? emoji + ' ' : ''}`. In `turnController.ts` `completeTool()`, pass `done?.emoji` as 6th arg. Without this, completed trail lines lack emojis.

### `tool.generating` creates duplicates
`createGatewayEventHandler.ts` line ~510: `tool.generating` handler pushes `drafting {name}…` to trail. When `tool.start` fires, it creates a SEPARATE active tool entry. Both render → duplicate. Remove the `pushTrail` call in the `tool.generating` case.

### `appendToolShelfMessage` already merges
The system's `liveProgress.ts` already merges tools into thinking messages via `appendToolShelfMessage()`. It checks `canHoldToolShelf()` (trail message with thinking, no text) and merges tools into it. If tools still appear separate, the model may be sending assistant text between thinking and tools, creating a barrier message.

### Question ≠ Action
When the user asks "c'est quoi X" or "explique moi X", they want an EXPLANATION. Do NOT remove/modify X. Example: user asked about Σ token count → agent removed it → user got angry. Always explain first.

### Process management
Never mass-kill `tui_gateway` or `node.*entry.js` — the user may have multiple TUI sessions. Use `ps -eo pid,lstart,args | grep` to identify specific PIDs. Ask before killing.

### `thinkingBlocks` for tree rendering
The user wanted a tree structure: `┌ Thinking / ├ Thinking / │ └ 💻 tool / └ Thinking`. This requires:
1. Add `thinkingBlocks?: { thinking: string; tools: string[] }[]` to `Msg` in `types.ts`
2. Add `reasoningBlocks` array to `TurnController` class in `turnController.ts`
3. In `closeReasoningSegment`, save `activeReasoningText` as a new block
4. In `recordToolComplete`, add trail line to last block's `tools`
5. In `clearReasoning`, reset `reasoningBlocks = []`
6. Set `thinkingBlocks` on `finalDetails` message
7. Pass `thinkingBlocks` from `messageLine.tsx` to `ToolTrail`
8. In `ToolTrail`, when `thinkingBlocks` is present, render tree with ┌/├/└/│ connectors

### `canHoldToolShelf` modification
Default `canHoldToolShelf` in `liveProgress.ts` merges tools into ANY trail message with thinking OR tools. To prevent tools piling into one message: change to require `msg.thinking?.trim() && !msg.tools?.length` so each thinking block gets tools only once.
