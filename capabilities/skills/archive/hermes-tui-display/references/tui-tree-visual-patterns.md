---
name: tui-tree-visual-patterns
description: Flat tree structure patterns for Hermes TUI — chronological thinking/tools rendering, tool emoji mapping, continuous rail spacers, user message box styling.
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [tui, tree, visual, customization, ink]
---

# TUI Tree Visual Patterns

Patterns for customizing the Hermes TUI tree structure and visual layout.

## Flat Chronological Tree

The default ToolTrail uses accordions (▾/▸) for collapsible sections. For a flat chronological tree where each thinking block has its tools as sub-branches, use these patterns.

### Tree Branch Types

Add 'first' to TreeBranch for the ┌ connector:

```typescript
type TreeBranch = 'first' | 'mid' | 'last'

const treeLead = (rails: TreeRails, branch: TreeBranch) =>
  `${rails.map(on => (on ? '│' : ' ')).join('')}${branch === 'first' ? '┌ ' : branch === 'mid' ? '├ ' : '└ '}`
```

### Tool Emoji Mapping

Match CLI registry emojis for consistency. Source: `tools/*.py` registry.register() calls.

```typescript
const toolEmoji = (label: string): string => {
  const l = label.toLowerCase()
  // Browser tools
  if (/browser_navigate|browser_open/.test(l)) return '🌐'
  if (/browser_click|browser_select/.test(l)) return '👆'
  if (/browser_type|browser_press/.test(l)) return '⌨️'
  if (/browser_scroll|browser_back/.test(l)) return '📜'
  if (/browser_snapshot|browser_get_images/.test(l)) return '📸'
  if (/browser_vision/.test(l)) return '👁️'
  if (/browser_console/.test(l)) return '🧪'
  // File tools
  if (/read_file/.test(l)) return '📖'
  if (/write_file/.test(l)) return '✍️'
  if (/patch/.test(l)) return '🔧'
  if (/search_files/.test(l)) return '🔎'
  // Web/search tools
  if (/web_search|web_extract/.test(l)) return '🔎'
  if (/session_search/.test(l)) return '🔎'
  if (/hindsight_recall|hindsight_reflect/.test(l)) return '🧠'
  // Code/terminal
  if (/terminal|execute_code/.test(l)) return '💻'
  if (/code_exec/.test(l)) return '🐍'
  // Image/media
  if (/image_generate/.test(l)) return '🎨'
  if (/text_to_speech/.test(l)) return '🔊'
  // Delegation
  if (/delegate_task/.test(l)) return '🔀'
  // Cron/scheduling
  if (/cronjob/.test(l)) return '⏰'
  // Memory
  if (/memory/.test(l)) return '🧠'
  // Clarify
  if (/clarify/.test(l)) return '❓'
  // Kanban
  if (/kanban/.test(l)) return '📋'
  // Default
  return '⚡'
}
```

### Spacer with Continuous Rail

To add vertical spacing between tree nodes while maintaining the continuous rail:

```typescript
function TreeRow({ branch, children, rails = [], stemColor, stemDim = true, t }) {
  const lead = treeLead(rails, branch)
  const spacerLead = `${rails.map(on => (on ? '│' : ' ')).join('')}`

  return (
    <Box flexDirection="column">
      <Box>
        <NoSelect flexShrink={0} fromLeftEdge width={lead.length}>
          <Text color={stemColor ?? t.color.muted} dim={stemDim}>{lead}</Text>
        </NoSelect>
        <Box flexDirection="column" flexGrow={1}>{children}</Box>
      </Box>
      {/* Spacer line with continuous rail */}
      {branch !== 'last' && spacerLead.trim() !== '' && (
        <Box>
          <NoSelect flexShrink={0} fromLeftEdge width={spacerLead.length}>
            <Text color={stemColor ?? t.color.muted} dim={stemDim}>{spacerLead}</Text>
          </NoSelect>
        </Box>
      )}
    </Box>
  )
}
```

### Flat ToolTrail Render

Replace the accordion-based ToolTrail with a flat chronological render in `components/thinking.tsx`:

```typescript
// In ToolTrail component, replace the panels.map section with:
const thinkingLines = cot ? cot.split('\n') : []
const hasContent = hasThinking || hasTools

return (
  <Box flexDirection="column">
    {/* Thinking nodes — flat, no chevrons */}
    {hasThinking ? (
      <TreeRow branch={hasTools ? 'mid' : 'last'} rails={[]} t={t}>
        <Box flexDirection="column" flexGrow={1}>
          {thinkingLines.map((line, i) => (
            <Text color={t.color.muted} key={i} wrap="wrap-trim">
              {line || ' '}
              {i === thinkingLines.length - 1 && thinkingLive ? (
                <StreamCursor color={t.color.muted} streaming={reasoningStreaming} visible={reasoningActive} />
              ) : null}
            </Text>
          ))}
        </Box>
      </TreeRow>
    ) : null}

    {/* Tool calls as children of thinking */}
    {hasTools ? (
      groups.map((group, i) => (
        <Box flexDirection="column" key={group.key}>
          <TreeRow branch={i === groups.length - 1 ? 'last' : 'mid'} rails={[true]} t={t}>
            <Text color={group.color}>
              {toolEmoji(group.label)} {toolLabel(group)}
            </Text>
          </TreeRow>
        </Box>
      ))
    ) : null}
  </Box>
)
```

### Result

This produces a tree like:
```
┌ (Thinking text...)
│
├ (Thinking text...)
│└ 📖 read_file
│
├ (Thinking text...)
│└ 🔧 patch
│└ 🔎 search_files
│
└ (Thinking text...)

│Output Answer
```

## User Message Box Styling

User messages can be styled as right-aligned boxes with borders. In `components/messageLine.tsx`:

```tsx
{msg.role === 'user' ? (
  <Box justifyContent="flex-end">
    <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" paddingX={1}>
      <Text bold color={body}>{content}</Text>
    </Box>
  </Box>
) : (
  <Box>
    <NoSelect flexShrink={0} fromLeftEdge width={gutterWidth}>
      <Text bold={msg.role === 'user'} color={prefix}>
        {glyph}{' '}
      </Text>
    </NoSelect>
    <Box width={transcriptBodyWidth(cols, msg.role, t.brand.prompt, TERMUX_TUI_MODE)}>{content}</Box>
  </Box>
)}
```

## Pitfalls

- **Tool calls must be chronological** — don't group all tools at the end. Each thinking block should have its tools as sub-branches immediately after.
- **Continuous rail on spacers** — the │ must continue through blank lines between blocks. Use `spacerLead` pattern.
- **Emoji consistency** — match the CLI registry (`tools/*.py` `emoji=` parameter) for visual consistency across interfaces.
- **TreeBranch 'first'** — needed for ┌ connector. Default only has 'mid' and 'last'.
- **User messages right-aligned** — use `justifyContent="flex-end"` on parent Box, not `alignItems`.
