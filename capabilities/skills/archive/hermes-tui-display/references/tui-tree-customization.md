---
name: tui-tree-customization
description: Customize the Thinking/ToolTrail tree structure in Hermes TUI — branch connectors, tool icons, borders, response separators.
version: 1.1.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, tree, thinking, tools, customization]
---

# TUI Tree Customization

Customize the visual structure of the Thinking/ToolTrail tree in `ui-tui/src/components/thinking.tsx`.

**Related skill**: `tui-tree-rendering` covers the continuous rail architecture and prefix rendering. This skill covers visual styling (icons, borders, separators).

## Tree Branch Types

`TreeBranch` has three values: `'first' | 'mid' | 'last'`

**Connectors** (defined in `treeLead`):
- `first` → `┌ ` (top of tree)
- `mid` → `├ ` (middle branches)
- `last` → `└ ` (final branch)

No dashes — clean tree lines.

## Tool Icons

- **Trail tools** (main ToolTrail component): `💻 `
- **Subagent tools** (SubagentAccordion): `🔧 `
- **Activity/search tools**: `🔎 ` (if needed)

Replace the default `● ` bullet with these icons in the tool rendering sections.

## ToolTrail Border

Wrap the entire tree output in a bordered box matching the input zone style:

```tsx
<Box borderColor={t.color.border} borderStyle="round" flexDirection="column" paddingX={1}>
  {panels.map((panel, index) => (
    <TreeNode
      branch={index === 0 ? 'first' : index === topCount - 1 ? 'last' : 'mid'}
      header={panel.header}
      key={panel.key}
      open={panel.open}
      t={t}
    >
      {panel.render}
    </TreeNode>
  ))}
</Box>
```

## Response Separator

Between the thinking block and the output answer, use a vertical bar `│ ` instead of `└─ Response`:

In `messageLine.tsx`, the `showResponseSeparator` section:
```tsx
<NoSelect flexShrink={0} fromLeftEdge width={gutterWidth}>
  <Text color={t.color.border}>│ </Text>
</NoSelect>
```

Remove the "Response" label text entirely.

## Branch Assignment Logic

First panel gets `'first'`, last gets `'last'`, middle panels get `'mid'`:

```tsx
branch={index === 0 ? 'first' : index === topCount - 1 ? 'last' : 'mid'}
```

For nested tool lists (e.g., `groups.map` in ToolTrail):
```tsx
const branch: TreeBranch = index === 0 ? 'first' : index === groups.length - 1 ? 'last' : 'mid'
```

## Files Modified

- `ui-tui/src/components/thinking.tsx` — tree structure, icons, border
- `ui-tui/src/components/messageLine.tsx` — response separator

## Build & Apply

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
# Then /quit the TUI and relaunch
```

## Visual Result

```
┌ (Thinking)
│
├ (Thinking)
│└ 💻 (tool call)
│
├ (Thinking)
│└ 🔧 (tool call)
│└ 🔎 (tool call)
│
└ (Thinking)

│Output Answer
```

## Pitfalls

- **TreeBranch type**: Must include `'first'` — original code only had `'mid' | 'last'`
- **nextTreeRails logic**: Use `branch !== 'last'` (not `branch === 'mid'`) to correctly propagate rails
- **Border padding**: Use `paddingX={1}` for consistent spacing with input zone
- **Icon width**: Emoji icons may render wider than ASCII — test with actual tool calls
