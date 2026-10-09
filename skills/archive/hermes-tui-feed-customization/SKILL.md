---
name: hermes-tui-feed-customization
description: Customize the Hermes TUI message feed — chronological thinking+tools flow, tool emoji pipeline, inline reasoning, SECTION_DEFAULTS. Covers the ToolTrail component architecture and common pitfalls when modifying the Ink/React TUI.
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, ink, tooltrail, thinking, emojis]
---

# Hermes TUI Feed Customization

How to customize the TUI message feed: chronological thinking+tools flow, tool emoji pipeline, inline reasoning display.

## ToolTrail Architecture (thinking.tsx)

The ToolTrail component renders thinking/reasoning and tool calls. Default: **separate collapsible panels**:

```
▸ Thinking          ← collapsible panel (chevron)
  ┊ reasoning text
▸ Tool calls (3)    ← separate collapsible panel
  ├─ 💻 Terminal("cmd") ✓
  └─ 🔍 Search("query") ✓
```

To merge into **chronological inline flow** (like the CLI):

1. Replace the thinking panel's `render` with inline dim text using `cleanThinkingText(reasoning)` (full text, not truncated)
2. Embed tool call rendering (TreeTextRow with elbows ├─/└─) INSIDE the same panel's render, after thinking text
3. Remove the separate `if (hasTools)` panel block entirely

## Tool Emoji Pipeline

1. **Registry** (`tools/*.py`) — `emoji=` param in `registry.register()`
2. **Skin override** (`skins/*.yaml` `tool_emojis:`) — takes precedence
3. **Gateway** (`tui_gateway/server.py` `_on_tool_start`) — sends emoji in `tool.start` event
4. **TUI** (`turnController.ts` `recordToolStart`) — stores in `ActiveTool.emoji`
5. **Trail line** (`text.ts` `buildToolTrailLine`) — emoji embedded in text on completion

**Critical:** `buildToolTrailLine` must receive `emoji` from `completeTool()` in turnController. Otherwise emoji disappears when tool completes.

## SECTION_DEFAULTS (details.ts)

```typescript
// ui-tui/src/domain/details.ts
const SECTION_DEFAULTS: SectionVisibility = {
  thinking: 'collapsed',  // change to 'expanded' for inline thinking
  tools: 'collapsed',     // change to 'expanded' for visible tools
  activity: 'hidden'
}
```

Config `display.sections` in config.yaml overrides per-section.

## Thinking Text: Full vs Truncated

- `THINKING_COT_MAX = 160` (config/limits.ts) — truncates preview
- `thinkingPreview(text, 'truncated', 160)` — 160 chars max
- `cleanThinkingText(text)` — **full text**, removes status lines. Use for inline rendering.

## Pitfalls

- **`●` hardcoded bullet** — Line ~1088 in thinking.tsx: `<Text color={t.color.accent}>● </Text>` before each completed tool. Replace or remove since emoji is in trail text.
- **`tool.generating` duplication** — Gateway pushes `drafting terminal…` to trail, then `tool.start` creates active tool. Both render → duplicate. Fix: skip `pushTrail` for `tool.generating` in createGatewayEventHandler.ts.
- **Node.js caches bundle** — Rebuilding `dist/entry.js` doesn't affect running processes. Kill and relaunch.
- **`execute_code` + `read_file`/`write_file` truncates** — `read_file` returns content with line number prefixes (`1|`). Writing back corrupts files. Use `patch` tool instead.
- **Don't kill user's TUI sessions** — Ask them to `/quit` and relaunch.
- **Skin `tool_emojis` override registry** — Check active skin before assuming defaults.
- **`running` prop on Spinner** — Committed Spinner doesn't have `running` prop. Don't add without updating signature.
