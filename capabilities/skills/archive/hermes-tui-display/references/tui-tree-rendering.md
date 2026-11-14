---
name: tui-tree-rendering
description: Continuous left-rail tree rendering in Hermes TUI — ToolTrail owns all prefixes via treeBranch prop, transcript persistence, emoji mapping
version: 2.1.0
author: walter
metadata:
  hermes:
    tags: [tui, tree, rendering, ink, react, tooltrail]
---

# TUI Tree Rendering

Continuous left-rail tree structures in the Hermes Ink/React TUI.

**Related skill**: `tui-tree-customization` covers visual styling (icons, borders, separators). This skill covers the continuous rail architecture and prefix rendering.

## CRITICAL: ToolTrail Owns All Prefixes

**The #1 pitfall**: Do NOT put tree prefixes (┌/├/└) in parent components. They disappear when segments are flushed to the transcript. **ToolTrail must render its own prefixes internally.**

### Target Format (user-specified, June 2026)

```
┌ (Thinking block 1...              ← treeBranch='first'
│  thinking continuation)
│                                   ← parent spacer between blocks
├ (Thinking block 2...              ← treeBranch='mid'
│  thinking continuation)
│ └ 💻 terminal(command)            ← tools as sub-branches
│                                   ← parent spacer between blocks
├ (Thinking block 3)                ← treeBranch='mid'
│ └ 🔧 patch(path)
│ └ 🔎 search_files(pattern)
│                                   ← parent spacer between blocks
└ (Thinking last block)             ← treeBranch='last'
  └ 📖 read_file(path)             ← space prefix (rail ended)
                                    ← empty (no rail)
│Output Answer                      ← answer with │ prefix
```

Key rules:
- Each thinking segment = primary node (┌/├/└)
- Tools = sub-branches `│ └` under their thinking (NOT at the same level)
- NO spacer between thinking and its tools (they belong together)
- Spacer `│` between BLOCKS (handled by parent)
- Last block: continuation uses space, tool prefix `  └`
- Non-last blocks: continuation uses `│`, tool prefix `│ └`

### Correct Architecture

```
Parent (streamingAssistant / TranscriptPane)
  └─ detects consecutive trail groups
  └─ passes treeBranch='first'|'mid'|'last' to MessageLine
  └─ adds spacer rows with │ between trail segments

MessageLine
  └─ passes treeBranch prop through to ToolTrail

ToolTrail (thinking.tsx)
  └─ computes firstLinePrefix, continuationPrefix, toolPrefix from treeBranch
  └─ renders ┌/├/└ on FIRST line of thinking text
  └─ renders continuationPrefix (│ or space) on subsequent lines
  └─ renders toolPrefix (│ └ or   └) for each tool call — directly after thinking, no spacer
```

### Why This Matters

When a turn completes, `flushStreamingSegment()` moves segments from the live streaming area to the transcript history. The transcript renders via `TranscriptPane` → `MessageLine` → `ToolTrail`. If prefixes are in the parent wrapper, they're lost. ToolTrail must be self-contained.

## Implementation

### 1. treeBranch + cols Prop Chain

Add to component props:
- `treeBranch?: 'first' | 'mid' | 'last'` — position in trail group
- `cols?: number` — terminal width for line pre-wrapping (default 80)

Pass through: `MessageLine` → `ToolTrail`

In `messageLine.tsx`:
```tsx
<ToolTrail
  cols={cols}  // Pass terminal width for pre-wrapping
  treeBranch={treeBranch}
  // ... other props
/>
```

### 2. Parent: Detect Trail Groups

In both `streamingAssistant.tsx` and `appLayout.tsx` (TranscriptPane):

```tsx
// Detect consecutive trail blocks
const trailGroups: { start: number; end: number }[] = []
let currentGroup: { start: number; end: number } | null = null

blocks.forEach((block, i) => {
  const isTrail = block.msg.kind === 'trail' || block.tools?.length
  if (isTrail) {
    if (!currentGroup) currentGroup = { start: i, end: i }
    else currentGroup.end = i
  } else {
    if (currentGroup) { trailGroups.push(currentGroup); currentGroup = null }
  }
})
if (currentGroup) trailGroups.push(currentGroup)

// Compute branch for each trail block
const getTrailInfo = (index: number) => {
  for (const group of trailGroups) {
    if (index >= group.start && index <= group.end) {
      const pos = index - group.start
      const size = group.end - group.start + 1
      const branch = size === 1 ? 'last' : pos === 0 ? 'first' : pos === size - 1 ? 'last' : 'mid'
      return { branch, isLast: pos === size - 1 }
    }
  }
  return null
}
```

### 3. Parent: Render with Spacers

```tsx
{blocks.map((block, i) => {
  const info = getTrailInfo(i)
  const isTrail = info !== null

  return (
    <Box flexDirection="column" key={block.key}>
      <MessageLine
        {...props}
        msg={block.msg}
        {...(isTrail ? { treeBranch: info!.branch } : {})}
      />
      {/* Spacer with continuous rail between trail segments (width=3 for alignment) */}
      {isTrail && !info!.isLast && (
        <Box>
          <NoSelect flexShrink={0} width={3}>
            <Text color={t.color.muted} dim>│ </Text>
          </NoSelect>
        </Box>
      )}
    </Box>
  )
})}
```

### 4. ToolTrail: Internal Prefix Rendering

Three prefix variables derived from `treeBranch`:

```tsx
const firstLinePrefix = treeBranch === 'first' ? '┌' : treeBranch === 'mid' ? '├' : '└'
// Continuation rail: │ for first/mid blocks, space for last block (rail ends)
const continuationPrefix = treeBranch === 'last' ? ' ' : '│'
// Tool sub-branch: │ └ for first/mid, space └ for last
const toolPrefix = treeBranch === 'last' ? '  └' : '│ └'

return (
  <Box flexDirection="column">
    {/* Thinking — first line has tree prefix, subsequent lines have continuationPrefix */}
    {hasThinking && wrappedThinkingLines.map((line, i) => (
      <Box key={i}>
        <NoSelect flexShrink={0} width={railWidth}>
          <Text color={t.color.muted} dim>
            {i === 0 ? firstLinePrefix : continuationPrefix}
          </Text>
        </NoSelect>
        <Text color={t.color.muted}>
          {line}
        </Text>
      </Box>
    ))}

    {/* Tool calls — sub-branches directly under thinking (NO spacer between them) */}
    {hasTools && groups.map((group, i) => (
      <Box key={group.key}>
        <NoSelect flexShrink={0} width={3}>
          <Text color={t.color.muted} dim>
            {toolPrefix}
          </Text>
        </NoSelect>
        <Text color={group.color}>
          {toolEmoji(group.label)} {toolLabel(group)}
        </Text>
      </Box>
    ))}
  </Box>
)
```

## turnController: Associate Tools with Thinking

By default, all tools accumulate in one block at the end. To associate tools with their preceding thinking:

In `turnController.ts`, modify `recordToolStart()`:

```tsx
recordToolStart(toolId, name, context, verboseArgs) {
  this.flushStreamingSegment()
  this.closeReasoningSegment()  // Close current reasoning
  
  // Attach pending tools to the last trail segment
  if (this.pendingSegmentTools.length > 0) {
    const segments = this.store.get().streamSegments
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i].kind === 'trail') {
        // Find the message and attach tools
        // ... implementation depends on store structure
        break
      }
    }
  }
  
  // Start new tool
  this.pendingSegmentTools.push({ toolId, name, context, verboseArgs })
}
```

## Tool Emoji Mapping

Manual mapping function (CLI registry emojis aren't auto-imported). **Keep this in sync with `tools/*.py` registry `emoji=` fields:**

```tsx
const toolEmoji = (label: string): string => {
  const l = label.toLowerCase()
  // Browser tools
  if (/browser_navigate/.test(l)) return '🌐'
  if (/browser_click|browser_select/.test(l)) return '👆'
  if (/browser_type|browser_press/.test(l)) return '⌨️'
  if (/browser_scroll|browser_back/.test(l)) return '📜'
  if (/browser_snapshot/.test(l)) return '📸'
  if (/browser_get_images/.test(l)) return '🖼️'
  if (/browser_vision/.test(l)) return '👁️'
  if (/browser_console/.test(l)) return '🧪'
  if (/browser_dialog/.test(l)) return '💬'
  // File tools
  if (/read_file/.test(l)) return '📖'
  if (/write_file/.test(l)) return '✍️'
  if (/patch/.test(l)) return '🔧'
  if (/search_files/.test(l)) return '🔎'
  // Web/search tools
  if (/web_search|web_extract/.test(l)) return '🔎'
  if (/session_search/.test(l)) return '🔍'
  if (/hindsight_recall|hindsight_reflect/.test(l)) return '🧠'
  // Code/terminal
  if (/terminal/.test(l)) return '💻'
  if (/execute_code|code_exec/.test(l)) return '🐍'
  // Image/media
  if (/image_generate/.test(l)) return '🎨'
  if (/text_to_speech/.test(l)) return '🔊'
  // Delegation
  if (/delegate_task/.test(l)) return '🔀'
  // Cron/scheduling
  if (/cronjob/.test(l)) return '⏰'
  // Memory
  if (/memory/.test(l)) return '🧠'
  if (/mixture_of_agents/.test(l)) return '🧠'
  // Skills
  if (/skill_view|skills_list/.test(l)) return '📚'
  if (/skill_manage/.test(l)) return '📝'
  // Clarify
  if (/clarify/.test(l)) return '❓'
  // Kanban/Todo
  if (/kanban/.test(l)) return '📋'
  if (/todo/.test(l)) return '📋'
  // Process
  if (/process/.test(l)) return '⚙️'
  // Send message
  if (/send_message/.test(l)) return '📨'
  // Home Assistant
  if (/homeassistant/.test(l)) return '🏠'
  // Feishu
  if (/feishu_doc/.test(l)) return '📄'
  if (/feishu_drive/.test(l)) return '💬'
  // Default
  return '⚡'
}
```

**Key differences from older versions:**
- `browser_get_images` separated from `browser_snapshot` (🖼️ vs 📸)
- `session_search` uses 🔍 (not 🔎)
- `execute_code` separated from `terminal` (🐍 vs 💻)
- `skills_list` grouped with `skill_view` (📚)

## Pitfalls

1. **NEVER put tree prefixes in parent wrappers** — they disappear on transcript flush. ToolTrail must own them.
2. **Every line of multi-line thinking needs │** — not just the first line. Otherwise the rail has holes.
3. **Spacer rows between trail segments need │** — empty lines break visual continuity.
4. **Both streaming AND transcript need the same logic** — detect trail groups in both `streamingAssistant.tsx` and `appLayout.tsx` (TranscriptPane).
5. **Width consistency**: Thinking lines use `width={2}` (railWidth — single char prefix). Tool calls use `width={3}` (toolPrefix = 3 chars: `│ └` or `  └`). Spacer rows between trail segments in parent use `width={3}` to align.
6. **`dim` prop on tree prefix `<Text>`** — consistent muted appearance.
9. **NO spacer between thinking and its tools** — Tools are sub-branches of their thinking block, rendered directly after. Spacers go between BLOCKS (handled by the parent), never within a single ToolTrail.
10. **Word wrap: pre-split lines for continuous │** — Ink's `wrap="wrap-trim"` doesn't support per-visual-line prefixes. SOLUTION: Pre-wrap lines manually in ToolTrail using `cols` prop. Pass `cols` from MessageLine → ToolTrail, then:
   ```tsx
   const railWidth = 2
   // cols = terminal width, subtract padding (2) + rail (2) = 4
   const contentWidth = Math.max(30, cols - railWidth - 4)
   
   const wrapLine = (text: string, maxWidth: number): string[] => {
     if (!text) return []
     const trimmed = text.trim()
     if (!trimmed) return []
     if (trimmed.length <= maxWidth) return [trimmed]
     
     // Split by words
     const words = trimmed.split(/\s+/).filter(w => w)
     if (words.length === 0) return []
     
     const lines: string[] = []
     let current = words[0]  // Start with first word
     
     for (let i = 1; i < words.length; i++) {
       const word = words[i]
       // Try to add word with space
       if (current.length + 1 + word.length <= maxWidth) {
         current += ' ' + word
       } else {
         lines.push(current)
         current = word
       }
     }
     
     if (current) {
       lines.push(current)
     }
     
     return lines
   }
   
   // CRITICAL: Filter empty lines FIRST, then wrap
   const wrappedThinkingLines = thinkingLines
     .filter(line => line && line.trim())
     .flatMap(line => wrapLine(line, contentWidth))
   
   // CRITICAL: Recalculate hasThinking after wrap to avoid empty blocks
   const hasThinkingAfterWrap = wrappedThinkingLines.length > 0 || (reasoningActive || reasoningStreaming)
   const hasContentAfterWrap = hasThinkingAfterWrap || hasTools
   
   if (!hasContentAfterWrap) {
     return outcome ? <Text>· {outcome}</Text> : null
   }
   ```
   Then render `wrappedThinkingLines` instead of `thinkingLines`. Each wrapped line gets its own │ prefix.
   
   **Why filter before wrap?** Empty lines in thinking content (e.g., from `\n\n` in the source) would otherwise create phantom visual breaks in the tree. Filtering first ensures only content-bearing lines are rendered.
   
   **Why recalculate hasThinking?** After wrapping, `wrappedThinkingLines` might be empty even if `hasThinking` was true (e.g., thinking contained only whitespace). Rendering an empty thinking block with just a prefix creates a visual artifact.
   
   **Why `cols - railWidth - 4`?** Terminal width includes padding on both sides (2 chars) plus the rail (2 chars). The extra margin prevents characters from being cut off at the right edge.
10. **Tool call rail width = 3** — Tool calls use `│ └` (with space between │ and └), so width={3}. Spacer between tools also width={3} with `│ ` (pipe + space). Thinking lines use width={2}.

## Files Modified

- `ui-tui/src/components/thinking.tsx` — ToolTrail with internal prefixes + treeBranch prop
- `ui-tui/src/components/messageLine.tsx` — treeBranch prop pass-through
- `ui-tui/src/components/streamingAssistant.tsx` — trail group detection + spacers
- `ui-tui/src/components/appLayout.tsx` — TranscriptPane trail group detection + spacers
- `ui-tui/src/app/turnController.ts` — tool-to-thinking association
- `~/.hermes/tui-overrides/` — persisted overrides
- `~/.hermes/scripts/restore-tui-design.sh` — restoration script