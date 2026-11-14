---
name: hermes-tui-tree-rendering
description: TUI tree rendering for thinking/tools display — continuous rail architecture, tool emojis, user message styling.
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, tree, thinking, tools, rendering]
---

# Hermes TUI Tree Rendering

Customize the thinking/tools tree display in the Hermes TUI. Covers the ToolTrail component architecture, continuous rail pattern, tool emoji mapping, and user message styling.

## Architecture

```
streamingAssistant.tsx → renders segments
  ↓
messageLine.tsx → dispatches trail messages to ToolTrail
  ↓
thinking.tsx → ToolTrail component renders the tree
```

Key files:
- `ui-tui/src/components/thinking.tsx` — ToolTrail component, tree primitives
- `ui-tui/src/components/messageLine.tsx` — message routing, user message boxing
- `ui-tui/src/components/streamingAssistant.tsx` — segment rendering loop

## Tree Structure

`TreeBranch` type: `'first' | 'mid' | 'last'` for proper prefixes:
- `┌` first node
- `├` middle nodes
- `└` last node

```typescript
type TreeBranch = 'first' | 'mid' | 'last'

const treeLead = (rails: TreeRails, branch: TreeBranch) =>
  `${rails.map(on => (on ? '│' : ' ')).join('')}${branch === 'first' ? '┌ ' : branch === 'mid' ? '├ ' : '└ '}`
```

## Tool Emoji Mapping

Tool emojis come from the Python registry in `tools/*.py`. The TUI must replicate this mapping:

| Tool | Emoji | Source |
|------|-------|--------|
| `skill_view` | 📚 | `tools/skills_tool.py` |
| `skill_manage` | 📝 | `tools/skill_manager_tool.py` |
| `read_file` | 📖 | `tools/file_tools.py` |
| `write_file` | ✍️ | `tools/file_tools.py` |
| `patch` | 🔧 | `tools/file_tools.py` |
| `search_files` | 🔎 | `tools/file_tools.py` |
| `terminal` | 💻 | `tools/terminal_tool.py` |
| `execute_code` | 💻 | `tools/code_execution_tool.py` |
| `web_search` | 🔎 | `tools/web_tools.py` |
| `web_extract` | 🔎 | `tools/web_tools.py` |
| `browser_navigate` | 🌐 | `tools/browser_tool.py` |
| `browser_click` | 👆 | `tools/browser_tool.py` |
| `browser_type` | ⌨️ | `tools/browser_tool.py` |
| `browser_snapshot` | 📸 | `tools/browser_tool.py` |
| `image_generate` | 🎨 | `tools/image_generation_tool.py` |
| `text_to_speech` | 🔊 | `tools/tts_tool.py` |
| `delegate_task` | 🔀 | `tools/delegate_tool.py` |
| `cronjob` | ⏰ | `tools/cronjob_tools.py` |
| `memory` | 🧠 | `tools/memory_tool.py` |
| `hindsight_recall` | 🧠 | hindsight plugin |
| `clarify` | ❓ | `tools/clarify_tool.py` |
| `kanban` | 📋 | `tools/kanban_tools.py` |

Implementation in `toolEmoji()` function in thinking.tsx:
```typescript
const toolEmoji = (label: string): string => {
  const l = label.toLowerCase()
  if (/skill_view/.test(l)) return '📚'
  if (/skill_manage/.test(l)) return '📝'
  if (/read_file/.test(l)) return '📖'
  if (/write_file/.test(l)) return '✍️'
  if (/patch/.test(l)) return '🔧'
  if (/search_files/.test(l)) return '🔎'
  if (/terminal|execute_code/.test(l)) return '💻'
  // ... etc
  return '⚡'
}
```

## Continuous Rail Pattern

**Critical rule**: The rail (│) must be continuous across the entire tree without gaps.

### Pitfalls

1. **Remove margins from trail containers** — `marginTop`/`marginBottom` on trail containers in messageLine.tsx create visual gaps in the rail. Remove them.

2. **Render spacers with rail characters** — between thinking and tools, and between tools, render spacer lines with `│` prefix.

3. **Tool calls use `│└` prefix** — as sub-branches under the thinking node.

4. **Spacer lines between tools also need `│` prefix** — to maintain continuity.

### User's Preferred Tree Style

```
┌ (Thinking text...)
│
│└ 💻 tool_call_1
│
│└ 🔧 tool_call_2
│
└ (Final thinking...)
```

## Stripping Tool Duration

Use `splitToolDuration()` to remove execution time from tool labels:

```typescript
const toolLabel = (group: Group) => {
  const { label } = splitToolDuration(String(group.content))
  return label || group.content
}
```

## User Message Styling

User messages are boxed and right-aligned in the feed:

```tsx
{msg.role === 'user' ? (
  <Box justifyContent="flex-end">
    <Box borderColor={t.color.border} borderStyle="round" paddingX={1}>
      <Text bold color={body}>{content}</Text>
    </Box>
  </Box>
) : (
  // Regular message rendering with glyph prefix
)}
```

## Build Process

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
```

Override files are stored in `~/.hermes/tui-overrides/` and restored via `~/.hermes/scripts/restore-tui-design.sh` after hermes updates.
