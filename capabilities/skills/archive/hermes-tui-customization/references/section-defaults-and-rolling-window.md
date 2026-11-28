# hermes-tui-customization — Thinking / Tools / Activity section defaults, the rolling window (compact live view of tool calls and thinking), tool emojis in headers, the legacy spinner prop.

Moved verbatim from SKILL.md on 2026-11-01.

## Section Defaults (Thinking / Tools / Activity)

File: `domain/details.ts` → `SECTION_DEFAULTS`

Controls whether the thinking reasoning and tool call accordions are open or closed by default. Users must click to expand/collapse at runtime.

### Auto-Collapse Timer (Deprecated — use Rolling Window instead)

The old auto-collapse timer used `setTimeout` + `busy` dependency to collapse everything after 4s. This fought with the `visible` sync effect and collapsed too aggressively. **Replaced by the Rolling Window pattern below.**

### Per-Tool Sub-Accordions

To make EACH tool call individually collapsible within the "Tool calls" parent accordion (instead of a flat `●` list), wrap each `Group` in a `TreeNode` with its own chevron header:

```tsx
// Track per-tool open state
const [openToolCalls, setOpenToolCalls] = useState<Set<string>>(new Set())

// In the tools panel render:
render: rails => (
  <Box flexDirection="column">
    {groups.map((group, index) => {
      const branch: TreeBranch = index === groups.length - 1 ? 'last' : 'mid'
      const isOpen = openToolCalls.has(group.key)

      const toggleTool = () => {
        setOpenToolCalls(prev => {
          const next = new Set(prev)
          if (next.has(group.key)) next.delete(group.key)
          else next.add(group.key)
          return next
        })
      }

      return (
        <TreeNode
          branch={branch}
          header={
            <Box onClick={toggleTool}>
              <Text color={group.color} wrap="truncate-end">
                <Text color={t.color.accent}>{isOpen ? '▾ ' : '▸ '}</Text>
                {group.emoji ? <Text color={t.color.accent}>{group.emoji} </Text> : null}
                {isOpen ? group.content : compactPreview(group.label, 60)}
              </Text>
            </Box>
          }
          key={group.key}
          open={isOpen}
          rails={rails}
          t={t}
        >
          {childRails => (
            <Box flexDirection="column">
              {group.details.map((detail, detailIndex) => (
                <Detail {...detail} branch={...} key={detail.key} rails={childRails} t={t} />
              ))}
            </Box>
          )}
        </TreeNode>
      )
    })}
  </Box>
)
```

**Update `expandAll`** to also open all individual tool calls:
```tsx
if (visible.tools !== 'hidden') {
  setOpenTools(true)
  setOpenToolCalls(new Set(groups.map(g => g.key)))
}
```

### Two-Line Reasoning Limit

To cap reasoning display at ~2 lines, change the `cot` computation in `ToolTrail` and the `Thinking` component mode:

```tsx
const THINKING_2LINE_MAX = 140  // ~2 lines on typical terminal
const cot = useMemo(() => thinkingPreview(reasoning, 'truncated', THINKING_2LINE_MAX), [reasoning])

// In the Thinking component call:
<Thinking mode="truncated" ... />
```

Also update `SubagentAccordion` thinking calls to use `mode="truncated"` for consistency.

### Tool Emojis in the TUI Header

The `ToolTrail` component renders active tools with their per-tool emoji (`💻 terminal`, `📖 read_file`, etc.). To also show tool emojis in the collapsed "Tool calls" section header (the `Chevron`), add emoji collection logic before the `panels.push()` in `thinking.tsx`:

```tsx
if (hasTools && visible.tools !== 'hidden') {
    const toolEmojis = [...new Set(groups.map(g => g.emoji).filter(Boolean))]
    const emojiPrefix = toolEmojis.length > 0 ? toolEmojis.slice(0, 3).join('') + ' ' : ''
    panels.push({
      header: (
        <Chevron
          // ...existing props...
          title={`${emojiPrefix}Tool calls`}
        />
      ),
```

This shows up to 3 unique tool emojis as a prefix on the section header: `▸ 💻📖🔧 Tool calls (3)` instead of `▸ Tool calls (3)`.

**Pitfall:** the restore script copies `thinking.tsx` from `~/.hermes/tui-overrides/`. After making this change, snapshot it with:
```bash
cp ~/.hermes/hermes-agent/ui-tui/src/components/thinking.tsx ~/.hermes/tui-overrides/thinking.tsx
```

### Tool Emojis in the TUI (active tools during execution)

The TUI shows per-tool emojis for active (in-progress) tools. The full pipeline is implemented:

**Backend** (`tui_gateway/server.py` — `_on_tool_start`):
```python
from agent.display import get_tool_emoji
payload["emoji"] = get_tool_emoji(name)
```

**TypeScript types** — `emoji?: string` on `ActiveTool` in `types.ts` and on the `tool.start` payload in `gatewayTypes.ts`.

**Event handler** (`createGatewayEventHandler.ts`):
```tsx
turnController.recordToolStart(ev.payload.tool_id, ev.payload.name ?? 'tool', ev.payload.context ?? '', ev.payload.emoji)
```

**Turn controller** (`turnController.ts`):
```tsx
recordToolStart(toolId: string, name: string, context: string, emoji?: string) {
  this.activeTools = [...this.activeTools, { context, emoji, id: toolId, name, startedAt: Date.now() }]
}
```

**ToolTrail rendering** (`thinking.tsx`):
```tsx
const emoji = tool.emoji || '⚡'
// renders: {emoji} {spinner} {label} ({elapsed})
```

**Emoji source:** `get_tool_emoji()` in `agent/display.py` checks:
1. Active skin's `tool_emojis` overrides
2. Tool registry's per-tool `emoji` field (set in `registry.register(..., emoji="💻")`)
3. Default `"⚡"` fallback

Most built-in tools have emojis registered: `💻` terminal, `📖` read_file, `✍️` write_file, `🔧` patch, `🔎` search_files, `🔀` delegate_task, `🌐` browser, `🐍` code_execution, `🧠` memory, `📚` skills, `📨` send_message, `❓` clarify, `📋` kanban.

**Pitfall:** the restore script (`~/.hermes/scripts/restore-tui-design.sh`) copies `types.ts` from `~/.hermes/tui-overrides/`, which may be stale and strip the `emoji` field. After restore, re-check `types.ts` for all custom fields.

```typescript
// Built-in defaults — override with `display.sections.<name>` in config.yaml
const SECTION_DEFAULTS: SectionVisibility = {
  thinking: 'collapsed',   // 'expanded' | 'collapsed' | 'hidden'
  tools: 'collapsed',      // 'expanded' | 'collapsed' | 'hidden'
  activity: 'hidden'       // ambient meta — usually noise
  // subagents: not set → falls through to global details_mode
}
```

**Resolution order:** explicit `display.sections.<name>` in config.yaml → `SECTION_DEFAULTS` → global `details_mode`.

Users can also toggle at runtime with `/details <section> expanded|collapsed|hidden`.

To change defaults, edit `SECTION_DEFAULTS` in `domain/details.ts` and rebuild.

## Rolling Window: Tool Calls & Thinking (Compact Live View)

Instead of auto-collapsing everything after a timer, use a "rolling window" that keeps the last N items expanded while older ones fold away.

### Pattern: Show Only Last 2 Tool Calls (hide older ones)

The user's preferred mode: the tools chevron shows only the 2 most recent tool calls. Older ones are hidden entirely (not just collapsed). Each visible call shows its emoji.

In the tools panel `render` function in `thinking.tsx`, slice `groups` to the last 2:

```tsx
render: rails => {
  // Only show the last 2 tool groups (rolling window)
  const visibleGroups = groups.slice(-2)
  const offset = groups.length - visibleGroups.length

  return (
    <Box flexDirection="column">
      {visibleGroups.map((group, vi) => {
        const index = offset + vi
        const branch: TreeBranch = vi === visibleGroups.length - 1 ? 'last' : 'mid'
        // ...rest of per-tool rendering unchanged
      })}
    </Box>
  )}
```

**Pitfall:** When changing from `render: rails => (` (expression) to `render: rails => {` (block), remember to close with `)}` not just `)`. The panel object's `render` property needs the closing brace + paren.

### Pattern: Thinking Spinner Visibility (No Frozen Spinner)

Reference: `references/tui-thinking-cmux-2026-05-18.md` captures the full session recipe, verification guards, cmux passthrough details, and restore-persistence checklist.

The user preference is: **show the spinner only while reasoning is live**. When thinking completes, remove the spinner entirely and leave a dim static `Thinking` label plus the cached/truncated thinking content. Do NOT use `running={false}` for completed thinking — it freezes a braille glyph on screen and looks broken.

```tsx
export function Spinner({ color, running = true, variant = 'think' }: { color: string; running?: boolean; variant?: 'think' | 'tool' }) {
  // ...
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)
    return () => clearInterval(id)
  }, [spin, running])
  // ...
}
```

In the thinking header, render the spinner only in the live branch:

```tsx
{thinkingLive ? (
  <Text bold color={t.color.text}>
    <Spinner color={t.color.accent} running variant="think" /> Thinking
  </Text>
) : (
  <Text color={t.color.muted} dim>Thinking</Text>
)}
```

**Pitfall:** If you remove `showDots`, also remove every JSX reference to it (notably `dim={!thinkingLive && !showDots}`). `npm run build` uses esbuild and may not type-check this; run a grep/type-check guard before shipping.

### Pattern: Sticky Thinking (No Auto-Collapse)

When the user wants thinking content to **stay visible** after completion (no auto-collapse timer), remove the `AUTO_COLLAPSE_DONE_MS` timeout entirely. The section opens when reasoning starts and only closes on manual click or next cycle:

```tsx
// ✅ Sticky — opens on start, never auto-closes
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

### Pattern: Thinking Auto-Open (NO auto-collapse)

Keep thinking open while streaming. **Never auto-collapse** — content stays visible until the user manually closes or a new thinking cycle starts. The spinner is rendered only while `thinkingLive` is true, then disappears.

```tsx
// Thinking section: open when active, NEVER close automatically
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])

// Header: spinner exists only while live
{thinkingLive ? <Spinner color={t.color.accent} running variant="think" /> : null}
```

The `Spinner` component signature:
```tsx
export function Spinner({ color, running = true, variant = 'think' }: {
  color: string; running?: boolean; variant?: 'think' | 'tool'
})
```

Do not use `running={false}` for completed thinking. The `AUTO_COLLAPSE_DONE_MS` constant should be removed entirely.

**When to use sticky:** User explicitly wants to read thinking content after it completes. The auto-collapse timer (`AUTO_COLLAPSE_DONE_MS = 3000`) collapses the section before the user can finish reading — remove it. Also remove the unused `AUTO_COLLAPSE_DONE_MS` constant.

**Pitfall:** If you remove auto-collapse but keep `openThinking` in the `visible` sync effect (line ~785), the section can still be collapsed by `/details thinking collapsed` or config overrides. This is correct — sticky only means "no timer-based collapse".

### Pattern: Last 2 Tool Calls Expanded

In `thinking.tsx`, use a rolling window for sub-accordion state:

```tsx
// Rolling window: keep last 2 sub-accordions expanded
const recentToolKeys = useMemo(
  () => new Set(tools.slice(-2).map(t => t.id)),
  [tools]
)

useEffect(() => {
  if (!tools.length) return
  // Keep only the last 2 tool sub-accordions open
  setOpenToolCalls(prev => {
    const prevArr = [...prev].sort()
    const newArr = [...recentToolKeys].sort()
    if (prevArr.length === newArr.length && prevArr.every((k, i) => k === newArr[i])) return prev
    return recentToolKeys
  })
}, [tools, recentToolKeys])
```

### Pattern: Thinking Auto-Open (Sticky — No Auto-Collapse)

Keep thinking open while streaming. Once done, it stays open (content visible) until the user manually clicks the chevron or a new thinking cycle starts. See "Sticky Thinking" above for the full pattern and rationale.

```tsx
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

**Deprecated pattern:** The old `AUTO_COLLAPSE_DONE_MS` timer collapsed thinking after 3 seconds, fighting with the `visible` sync effect and hiding content before the user could read it. Removed in favor of sticky.

### Pattern: Thinking Content Persistence Between Turns

When a new turn starts, `turnController.clearReasoning()` resets `reasoning` to `''`. This makes the thinking content disappear before the user can read it. Cache the last non-empty reasoning in a `useRef` to keep it visible until fresh reasoning arrives.

In `components/thinking.tsx`, add `useRef` to imports and create a caching mechanism:

```tsx
import { memo, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'

// Inside the ToolTrail component:
const cachedReasoningRef = useRef(reasoning)
useEffect(() => {
  if (reasoning) {
    cachedReasoningRef.current = reasoning
  }
}, [reasoning])

const displayReasoning = reasoning || cachedReasoningRef.current
const cot = useMemo(() => thinkingPreview(displayReasoning, 'truncated', THINKING_2LINE_MAX), [displayReasoning])
```

Then use `displayReasoning` instead of `reasoning` in the Thinking component render:

```tsx
render: rails => (
  <Thinking
    active={thinkingLive}
    branch="last"
    mode={thinkingLive ? 'full' : 'truncated'}
    rails={rails}
    reasoning={thinkingLive ? displayReasoning : cot}
    streaming={thinkingLive && reasoningStreaming}
    t={t}
  />
)
```

**Behavior:**
- Thinking starts → content streams in, spinner animates
- Thinking ends → spinner disappears, content stays visible as the truncated cached preview
- New turn starts → `reasoning` clears to `''`, but `displayReasoning` uses cached value → content remains
- New thinking starts → `reasoning` updates with fresh content → display updates

**Why `thinkingLive ? displayReasoning : cot`:** When actively reasoning, show the live/full bounded content (`displayReasoning`) so the current run writes in front of the user. When done, show the truncated preview (`cot`) — this prevents the section from showing a wall of text after completion.

### Pattern: Auto-Open Tools Section When Active

In the `visible` sync effect, keep tools open when tools are running:

```tsx
useEffect(() => {
  setOpenThinking(visible.thinking === 'expanded')
  setOpenSubagents(visible.subagents === 'expanded')
  setOpenMeta(visible.activity === 'expanded')
}, [visible.thinking, visible.subagents, visible.activity])

useEffect(() => {
  setOpenTools(visible.tools === 'expanded' || (visible.tools !== 'hidden' && tools.length > 0))
}, [visible.tools, tools.length])
```

**Pitfall:** Do not keep `tools.length` in the same effect that resets `openThinking`. Otherwise a tool start can collapse the thinking panel while reasoning is still in progress.

**Pitfall:** Do NOT add `openTools` to the rolling window effect dependencies — the `visible` sync effect handles open/close. The rolling window only manages sub-accordion state. Mixing them creates a toggle loop.

**Pitfall:** `groups` is built during render (not in a useMemo). Use `tools` as the useEffect dependency, not `groups`. `recentToolKeys` is derived from `tools` via useMemo so it's stable.

## Tool Emojis in Section Headers

The "Tool calls" Chevron header shows `▸ Tool calls (3)` by default. To show tool emojis in the header:

```tsx
if (hasTools && visible.tools !== 'hidden') {
  const toolEmojis = [...new Set(groups.map(g => g.emoji).filter(Boolean))]
  const emojiPrefix = toolEmojis.length > 0 ? toolEmojis.slice(0, 3).join('') + ' ' : ''
  panels.push({
    header: (
      <Chevron
        count={groups.length}
        // ...
        title={`${emojiPrefix}Tool calls`}
      />
    ),
    // ...
  })
}
```

Shows up to 3 unique emojis from the active tools. Example: `▸ 💻📖🔧 Tool calls (5)`.

**Note:** This runs inside the render body where `groups` is available. The `useMemo` for `recentToolKeys` runs before render (in the hooks section) and uses `tools`, not `groups`.

## Spinner `running` Prop (Legacy — Do Not Use For Completed Thinking)

The `Spinner` component accepts a `running` prop (default `true`). When `false`, the `setInterval` is not created and the spinner stays on its current frame. This can still be useful for niche tool indicators, but **not** for completed thinking: Lucas wants the spinner gone, not frozen.

```tsx
export function Spinner({ color, running = true, variant = 'think' }: { color: string; running?: boolean; variant?: 'think' | 'tool' }) {
  // ...
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)
    return () => clearInterval(id)
  }, [spin, running])
  // ...
}
```

Preferred thinking header pattern:
```tsx
{thinkingLive ? (
  <Spinner color={t.color.accent} running variant="think" />
) : ( /* dim static text, no spinner */ )}
```

### Remove Thinking Auto-Collapse

The old `AUTO_COLLAPSE_DONE_MS` timer (3s `setTimeout` to `setOpenThinking(false)`) fights with the `visible` sync effect. Remove it entirely — thinking stays expanded until the user manually collapses or a new thinking cycle starts:

```tsx
useEffect(() => {
  if (reasoningActive || reasoningStreaming) {
    setOpenThinking(true)
  }
}, [reasoningActive, reasoningStreaming])
```

Delete the `AUTO_COLLAPSE_DONE_MS` constant entirely.

## Rolling Window: Tool Calls & Thinking (Compact Live View)

Instead of auto-collapsing everything after a timer, use a "rolling window" that keeps the last N items expanded while older ones fold away.
3. **Rebuild required — pip path matters** — TypeScript changes need `npm run build` + `pip install -e .`. On this system the venv is Python 3.11 at `venv/bin/python` — `source venv/bin/activate && pip install -e .` may fail with PEP 668 if the system Python 3.12 takes over. Always use `./venv/bin/python -m pip install -e .` explicitly.
4. **`borderStyle="round"`** — Uses Unicode box-drawing characters (╭╮╰╯). Works in most modern terminals but may render as `+` in basic terminals.
5. **Bubble width** — Cap at `cols - 8` to avoid overflow on narrow terminals.
6. **Section defaults are code, not config** — Changing `SECTION_DEFAULTS` in `details.ts` requires a full rebuild. Runtime overrides via `display.sections` in config.yaml work without rebuild.
7. **"Frame disappeared after update"** — `hermes update` stashes local changes. If the user previously had a patched border around the composer, it was likely lost in the autostash. Check `git stash list` in `~/.hermes/hermes-agent` and re-apply the patch manually (do not blindly `git stash pop` — the TUI internals may have changed).
8. **Stash pop fails after update** — `git stash pop` often fails because the TUI internals changed (new components, renamed props, deleted files). Always use `git checkout stash@{0} -- <file>` to extract individual files. If that file no longer exists in the new version, the checkout will fail cleanly and you'll know you need to port manually.
9. **Props removed between versions** — The TUI API changes across releases. For example, `voiceRecordKey` was removed from `TextInput` props in v0.12.0. If a stashed patch references a deleted prop, the TypeScript build will fail with `Property 'voiceRecordKey' does not exist on type 'TextInputProps'`. Fix: remove the offending prop line and rebuild.
10. **Backend patches are invisible to git stash** — If you modified `_session_info()` in `tui_gateway/server.py` to send extra data (e.g. `recent_sessions`), those changes are inside the repo but `git stash` only captures the *pre-update* working tree. After `hermes update`, the backend resets to upstream and your custom data disappears even if you recover the frontend files. You must re-apply backend patches separately. See "Recent Sessions Grid" above for the exact Python code to re-inject.
11. **`compactPreview` needs a string, not ReactNode** — `group.content` is a `ReactNode`. Don't pass it to `compactPreview()`. Use `group.label` (a plain string) for the collapsed sub-accordion header.
12. **Restore script overwrites `types.ts`** — `~/.hermes/scripts/restore-tui-design.sh` copies `types.ts` from `~/.hermes/tui-overrides/`. If you added custom fields to types (e.g. `emoji` on `ActiveTool`, `recent_sessions` on `SessionInfo`), those are lost after restore. Keep `types.ts` in the tui-overrides backup or re-apply the type patches after restore.
13. **Restore script may downgrade the package** — the script runs `pip install -e .` which can install a stale cached wheel. Run `./venv/bin/python -m pip install -e .` again after restore to ensure the current version is installed.
14. **`source="tui"` vs `exclude_sources`** — TUI sessions have `source="tui"` (set in `server.py` line ~2808 and ~2020). Use `source="tui"` for filtering recent sessions instead of excluding sources — it's more precise and doesn't need updating when new sources are added.
15. **Rolling window vs auto-collapse timer** — The old auto-collapse timer (`setTimeout` + `busy` dependency) fights with the `visible` sync effect. Use the rolling window pattern instead: `useMemo` for `recentToolKeys` from `tools`, separate `useEffect` for sub-accordion state, and modify the `visible` sync effect to keep tools open when `tools.length > 0`.
16. **tmux runs as a different user** — On multi-user VPS setups (e.g. Oracle Cloud with `ubuntu` user), tmux runs as the SSH login user, NOT root. Editing `/root/.tmux.conf` has zero effect. Always check `ps aux | grep tmux` to find the owning user and edit THEIR `~/.tmux.conf`. This applies to `set-clipboard`, `allow-passthrough`, and `update-environment`.
17. **`sudo -i` strips SSH env vars** — When hermes is launched via `sudo -i bash -lc 'hermes --tui'`, SSH_CONNECTION/SSH_CLIENT/SSH_TTY are lost. Fix with `/etc/sudoers.d/keep-ssh-env` containing `Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"`.
19. **Restore script exit code masking** — The restore script uses `npm run build 2>&1 | tail -5` which swallows the build exit code. Even if the build fails with errors, the script continues and prints "Done." Always scroll up to check for "ERROR:" lines in the output.
20. **Override files drift after upstream API changes** — When upstream removes or renames exported symbols, the override files in `~/.hermes/tui-overrides/` become stale. The restore script blindly copies them and the build fails. This is NOT a "start from scratch" situation — find the upstream commit (`git log --oneline -- <file>`), see what changed, and update only the broken imports/props in the override files. See `references/override-compat-fix-20260521.md` for a concrete example.
17. **`groups` is not memoized** — `groups` is built during render (not in a `useMemo`). Effects that depend on tool IDs must use `tools` (the prop) with a `useMemo` derivation, not `groups` directly.
18. **SSH_CONNECTION default fallback in .bashrc** — When launching hermes from tmux that was created by the agent itself (not from an SSH session), `SSH_CONNECTION` won't be in the environment even with `update-environment`. The setting only picks up vars from the SSH session that created tmux — if tmux was started by `tmux new-session` from a non-SSH context, the vars are explicitly UNSET (prefix `-` in `tmux show-environment`). Fix: add `export SSH_CONNECTION="${SSH_CONNECTION:-127.0.0.1 45996 127.0.0.1 22}"` to root's `.bashrc` as a fallback.
14. **User wants full autonomy — "tu as toutes les clefs"** — When the user says to handle everything yourself (e.g. "tu fait tout tout seul", "tu as toutes les clefs"), do NOT ask them to run commands, restart services, or verify things manually. Execute the full fix chain end-to-end: edit config, kill tmux, restart hermes, verify the process env. Only report what was done, not what they should do. This applies especially to tmux restarts, hermes relaunches, and environment fixes — the user expects the agent to own the entire pipeline.
15. **Restore script source filter drift** — The restore script (`restore-tui-design.sh`) patches `server.py` via a Python heredoc. If you change the `source=` or `exclude_sources=` parameter in `server.py`, you MUST also update the restore script's heredoc to match. Otherwise the next `hermes update` + restore will silently revert to the old filter. The heredoc uses single-quoted `PYEOF` so Python double quotes pass through unescaped — do NOT backslash-escape them.
