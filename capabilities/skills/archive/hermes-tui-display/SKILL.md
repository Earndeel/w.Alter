---
name: hermes-tui-display
description: Customize Hermes TUI display — role glyphs, thinking/reasoning rendering, tool emoji, brand icons. Ink/React source modifications for the --tui mode.
version: 1.1.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, display, glyphs, ink, react, thinking, reasoning]
---

# Hermes TUI Display Customization

Modify the Ink/React TUI (`hermes --tui`) display: role glyphs, reasoning rendering, tool emojis, brand icons.

Source: `~/.hermes/hermes-agent/ui-tui/src/`

## File Map

| File | Controls |
|------|----------|
| `domain/roles.ts` | Per-role glyph + color (user, assistant, tool, system) |
| `theme.ts` | `BRAND` const: icon, prompt, welcome, goodbye, tool prefix |
| `components/thinking.tsx` | Reasoning display + ToolTrail (1279 lines) |
| `components/appChrome.tsx` | Status indicator frames (EMOJI_FRAMES, ASCII_FRAMES, kaomoji) |
| `components/appLayout.tsx` | Layout status indicator |
| `components/messageLine.tsx` | Message line renderer (uses ROLE glyphs) |
| `components/streamingAssistant.tsx` | Live streaming area |

## Tool Emoji Plumbing (end-to-end)

Backend → Gateway → TUI, already wired:

1. Python `agent/display.py` → `get_tool_emoji(tool_name)` resolves: skin override → registry `emoji` field → `⚡` fallback
2. Gateway `tui_gateway/server.py` → sends `emoji` in `tool_start` event payload
3. TUI `types.ts` → `ActiveTool.emoji` field
4. TUI `turnController.ts:679` → `recordToolStart(toolId, name, context, emoji)`
5. TUI `thinking.tsx:897` → `const emoji = tool.emoji || '⚡'`

**Gateway must send the emoji.** The registry `emoji` field alone is NOT enough — `tui_gateway/server.py` `_on_tool_start()` must explicitly call `get_tool_emoji()` and include it in the payload. If the gateway payload omits `emoji`, the TUI falls back to `⚡` regardless of registry settings. See Pitfall #7 and `references/gateway-emoji-payload.py`.

## Reasoning Display: Collapsible vs Inline

Default: reasoning is a collapsible chevron panel (▾/▸ toggle) inside ToolTrail.

To make it **inline** (like CLI's `[thinking]` dim preview):

In `thinking.tsx`, ToolTrail component (~line 1039):

```tsx
// Replace the collapsible thinking panel with inline dim text
if (hasThinking && visible.thinking !== 'hidden') {
  // IMPORTANT: use cleanThinkingText(displayReasoning), NOT cot
  // cot = thinkingPreview(..., 'truncated', 140) — truncated to 140 chars!
  const fullThinking = cleanThinkingText(displayReasoning)

  panels.push({
    header: (
      <Box>
        <Text color={t.color.muted} dim={!thinkingLive}>
          {thinkingLive ? (
            <Text bold color={t.color.text}>
              <Spinner color={t.color.accent} running variant="think" /> thinking
            </Text>
          ) : (
            <Text color={t.color.muted} dim>thinking</Text>
          )}
          {thinkingTokensLabel ? (
            <Text color={t.color.statusFg} dim>{'  '}{thinkingTokensLabel}</Text>
          ) : null}
        </Text>
      </Box>
    ),
    key: 'thinking',
    open: true,   // always visible — not collapsible
    render: () => (
      <Box flexDirection="column" paddingLeft={2}>
        {fullThinking.split('\n').map((line: string, index: number, arr: string[]) => (
          <Text color={t.color.muted} dim key={index} wrap="wrap-trim">
            {line || ' '}
            {index === arr.length - 1 && thinkingLive ? (
              <StreamCursor color={t.color.muted} streaming={reasoningStreaming} visible={thinkingLive} />
            ) : null}
          </Text>
        ))}
      </Box>
    )
  })
}
```

Requires import: add `cleanThinkingText` to the import from `'../lib/text.js'`.

Key changes from default:
- Remove `onClick` handler and chevron (`▸`/`▾`) from header
- Set `open: true` (always visible)
- Replace `<Thinking>` component with simple dim `<Text>` lines
- Keep `<StreamCursor>` on last line during streaming
- Lowercase `thinking` label (matches CLI style)

## Role Glyphs

`domain/roles.ts` defines per-role rendering. Default:

```ts
export const ROLE = {
  assistant: t => ({ body: t.color.text, glyph: t.brand.tool, prefix: t.color.border }),
  system: t => ({ body: '', glyph: '·', prefix: t.color.muted }),
  tool: t => ({ body: t.color.muted, glyph: '⚡', prefix: t.color.muted }),
  user: t => ({ body: t.color.label, glyph: t.brand.prompt, prefix: t.color.label })
}
```

Minimal variant (no assistant glyph, bullet user, pipe tool):

```ts
export const ROLE = {
  assistant: t => ({ body: t.color.text, glyph: '', prefix: t.color.border }),
  system: t => ({ body: '', glyph: '·', prefix: t.color.muted }),
  tool: t => ({ body: t.color.muted, glyph: '┊', prefix: t.color.muted }),
  user: t => ({ body: t.color.label, glyph: '●', prefix: t.color.label })
}
```

When glyph is empty, `messageLine.tsx` must conditionally skip the 3-width spacer. Default code always renders a 3-char `NoSelect` block — replace with:

```tsx
{glyph ? (
  <NoSelect flexShrink={0} fromLeftEdge width={3}>
    <Text bold={false} color={prefix}>{glyph}{' '}</Text>
  </NoSelect>
) : null}
<Box width={Math.max(20, cols - (glyph ? 5 : 2))}>{content}</Box>
```

## Brand (theme.ts)

`BRAND` const controls icon, prompt glyph, welcome/goodbye text:

```ts
const BRAND: ThemeBrand = {
  name: 'Hermes Agent',
  icon: '',           // no brand icon (empty = nothing rendered)
  prompt: '●',       // input prompt glyph
  welcome: 'Type your message or /help for commands.',
  goodbye: 'Goodbye.',
  tool: '┊',         // tool prefix character
  helpHeader: '(^_^)? Commands'
}
```

Setting `icon: ''` removes the icon from `branding.tsx` Banner, `appChrome.tsx` EMOJI_FRAMES fallback, and `appLayout.tsx` status indicator. Also update EMOJI_FRAMES[0] and its fallback to match (e.g. `⚡` instead of `⚕`).

`brand.prompt` is used by `roles.ts` user glyph (via `t.brand.prompt`). Changing BRAND changes user glyph automatically unless roles.ts hardcodes a different value.

## Build

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build          # → dist/entry.js (~2.9MB, ~200ms)
```

Uses custom `scripts/build.mjs` (NOT vite). After build, restart TUI.

## Debugging Slash Commands

Hermes slash commands span three layers — Python command registry, tui_gateway JSON-RPC bridge, and the Ink/TypeScript frontend. When a command misbehaves, the bug is almost always one layer being out of sync with another.

### Architecture

```
Python backend (hermes_cli/commands.py)     <- canonical COMMAND_REGISTRY
       │
       ▼
TUI gateway (tui_gateway/server.py)         <- slash.exec / command.dispatch
       │
       ▼
TUI frontend (ui-tui/src/app/slash/)        <- local handlers + fallthrough
```

The Python `COMMAND_REGISTRY` is the source of truth for: CLI dispatch, gateway help, Telegram BotCommand menu, Slack subcommand map, and autocomplete data shipped to Ink.

### Investigation Steps

1. Check if the command exists in the TUI frontend: `search_files --pattern "/commandname" --file_glob "*.ts" --path ui-tui/`
2. Check if the command exists in the Python backend: `search_files --pattern "commandname" --path hermes_cli/commands.py --context 3`
3. Check the gateway implementation: `search_files --pattern "complete.slash|slash.exec" --path tui_gateway/`

### Common Issues

1. **Command shows in TUI but not in autocomplete.** Missing from `COMMAND_REGISTRY` in `hermes_cli/commands.py`. Autocomplete data ships from Python.
2. **Command shows in autocomplete but doesn't work.** Check `tui_gateway/server.py` and `ui-tui/src/app/createSlashHandler.ts`. Local TUI handlers take precedence over gateway dispatch.
3. **Command behavior differs between CLI and TUI.** Check both `cli.py::process_command` and the TUI's local handler.
4. **Command persists config but doesn't apply live.** For TUI-local commands, also patch the relevant nanostore state immediately (usually `patchUiState(...)`).
5. **Gateway dispatch silently ignores the command.** Check `GATEWAY_KNOWN_COMMANDS` includes the canonical name. If `cli_only` with `gateway_config_gate`, verify the gate is truthy.

### Adding a Missing Command

1. Add a `CommandDef` entry to `COMMAND_REGISTRY` in `hermes_cli/commands.py`:
   ```python
   CommandDef("commandname", "Description", "Session",
              cli_only=True, aliases=("alias",),
              args_hint="[arg1|arg2|arg3]",
              subcommands=("arg1", "arg2", "arg3")),
   ```
2. Add handler in `HermesCLI.process_command()` in `cli.py`
3. For gateway-available commands, add handler in `gateway/run.py`

### Debugging Tactics

- **Python side hangs**: use `python-debugpy` skill to break inside `_SlashWorker.exec`
- **Ink side not reacting**: use `node-inspect-debugger` skill to break in `app.tsx` slash dispatch
- **Registry mismatch**: compare canonical `COMMAND_REGISTRY` against TUI's local command list

## Pitfalls

1. **Search `⚕` before changing branding** — the caduceus appears in `EMOJI_FRAMES` (appChrome.tsx), `appLayout.tsx` status, `brand.icon`, and `brand.goodbye`. Miss one and you get inconsistent glyphs.

2. **`brand.prompt` vs `ROLE.user.glyph`** — roles.ts reads `t.brand.prompt` by default. If you hardcode a glyph in roles.ts, changing BRAND.prompt later won't affect it. Pick one source of truth.

3. **LSP errors in appChrome.tsx** — Pre-existing TS errors about `compressions` on `Usage` type (~line 437). Unrelated to display changes, safe to ignore.

4. **Thinking component still imported** — After switching to inline rendering, the `Thinking` component import in thinking.tsx is still used by `SubagentAccordion`. Don't remove it.

5. **`openThinking` state still exists** — The inline approach sets `open: true` directly but the `openThinking` useState is still referenced by other effects. Don't remove the state variable, just stop using it for the thinking panel.

6. **Tool emoji is per-call** — `tool.emoji` comes from the backend per tool invocation. To permanently change an emoji, modify the tool's `registry.register(emoji=...)` in `tools/*.py`, not the TUI.

7. **Gateway must explicitly send emoji** — `_on_tool_start()` in `tui_gateway/server.py` must call `get_tool_emoji(name)` from `agent.display` and include `payload["emoji"] = emoji`. Without this, the TUI always falls back to `⚡` even when the registry has a per-tool emoji.

8. **`cot` is truncated to 140 chars** — `cot` in ToolTrail is computed as `thinkingPreview(displayReasoning, 'truncated', THINKING_2LINE_MAX)` where `THINKING_2LINE_MAX = 140`. When making thinking inline, you MUST use `cleanThinkingText(displayReasoning)` (full text with cleanup, no truncation). Import `cleanThinkingText` from `'../lib/text.js'`.

9. **Empty glyph leaves 3-char spacer** — `messageLine.tsx` hardcodes `width={3}` for the glyph area. If you set a role's glyph to `''`, the spacer still renders as 3 blank chars. Must add conditional: `{glyph ? <NoSelect width={3}>...</NoSelect> : null}` and adjust content width to `cols - (glyph ? 5 : 2)`.

10. **Patches can silently revert** — If the file is modified externally between your patch and the build step (e.g., auto-format, git operation, another process), your changes may be lost. Always re-read the file after a failed patch attempt and before building.

11. **Hardcoded `●` in ToolTrail** — `thinking.tsx` line ~1088 has `<Text color={t.color.accent}>● </Text>` before each completed tool in the tools panel. Replace with nothing (emoji is already in the trail text from `buildToolTrailLine`).

12. **`SECTION_DEFAULTS` keeps reverting** — `details.ts` is in git. Any `git checkout`, `hermes update` stash/pop, or build script that touches the working copy can revert `SECTION_DEFAULTS` back to `'collapsed'`. Always verify after build: `grep -A5 'SECTION_DEFAULTS' ui-tui/src/domain/details.ts`. Also add overrides in config.yaml as belt-and-suspenders.

13. **`execute_code` + `read_file` + `write_file` = file corruption** — `read_file()` returns `LINE_NUM|content`. Using this output with `write_file()` writes the line numbers literally. ALWAYS use `patch` for edits, never `read_file` → modify → `write_file` in execute_code.

14. **Multiple Node.js TUI processes** — Each `hermes --tui` launch spawns a Node.js process that loads the bundle once at startup. Old processes use old bundles. Check with `ps -eo pid,lstart,args | grep 'node.*entry.js'`. Kill old ones before expecting changes to appear.

15. **Skin spinner pollution** — Skin `spinner.waiting_faces`, `spinner.thinking_faces`, `spinner.thinking_verbs` add decorative kawaii faces (💧, 🔷, ❄) and verbs ("calculuis", "optimise") to the CLI spinner. These are NOT tool emojis. Remove the `spinner` section from the skin for a clean feed; keep only `tool_emojis`.

16. **`buildToolTrailLine` needs emoji parameter** — The default `buildToolTrailLine()` in `text.ts` doesn't include an emoji. Add an `emoji?: string` parameter and prepend it: `${em}${formatToolCall(name, context)}...`. Then in `turnController.ts` `completeTool()`, pass `done?.emoji` as the 6th argument. Without this, completed trail lines have no emoji.

17. **Don't remove features without explicit request** — If the user asks "c'est quoi X" (what is X), they want an EXPLANATION, not a deletion. Example: user asked about Σ token count → I removed it → user got angry. Always explain first, only modify when explicitly asked.

18. **User has extensive TUI customizations** — The user's TUI has custom appLayout.tsx (rounded borders), messageLine.tsx (right-aligned user messages), branding.tsx (W.ALTER logo), session grid, date formatting. These are in the `hermes update` auto-stash.

    **CRITICAL — NEVER `git checkout` to revert your own changes.** Even when YOU modified a file, the working tree may contain pre-existing uncommitted customizations that your `git checkout` will destroy along with your edits. The ONLY safe reversion flow:

    1. `git diff -- <file>` — inspect what's in the working tree FIRST
    2. `git stash` — preserve everything before reverting
    3. `git checkout -- <file>` — now safe, the stash has the backup
    4. Re-apply only needed parts from the stash, OR use `patch` to revert your specific hunks without touching anything else

    Better yet: avoid `git checkout --` entirely. Use `patch` to undo your specific changes line-by-line. If you must checkout, always stash first.

19. **`hermes update` stash/pop cycle** — Running `hermes update` auto-stashes local changes. When the stash is popped, it can create merge conflicts. Resolve conflicts with `git checkout --theirs` (take stash version = user's customizations), then re-apply only your targeted changes.

20. **Kill processes carefully** — Each `hermes --tui` spawns a Node.js + gateway process. The user may have multiple TUI sessions on different tmux terminals. NEVER mass-kill `tui_gateway` or `node.*entry.js` — it kills the user's active sessions and causes signal 1 errors. Ask first, or kill only specific PIDs.

21. **`tool.generating` creates duplicates** — The `tool.generating` event in `createGatewayEventHandler.ts` pushes `drafting {name}…` to the trail. When `tool.start` fires moments later, it creates an ACTIVE tool entry for the same tool. Both appear in the ToolTrail, causing duplicate entries. Remove the `pushTrail` call in the `tool.generating` handler.

22. **`running` prop on Spinner** — Committed Spinner doesn't have `running` prop. Don't add without updating signature.

23. **`appendToolShelfMessage` already merges** — The system's `liveProgress.ts` already merges tools into thinking messages via `appendToolShelfMessage()`. It checks `canHoldToolShelf()` (trail message with thinking, no text) and merges tools into it. If tools still appear separate, the model may be sending assistant text between thinking and tools, creating a barrier message.

24. **`canHoldToolShelf` modification** — Default `canHoldToolShelf` in `liveProgress.ts` merges tools into ANY trail message with thinking OR tools. To prevent tools piling into one message: change to require `msg.thinking?.trim() && !msg.tools?.length` so each thinking block gets tools only once.

25. **`thinkingBlocks` for tree rendering** — To render tree structure (┌/├/└/│ connectors), add `thinkingBlocks?: { thinking: string; tools: string[] }[]` to `Msg` in `types.ts`, add `reasoningBlocks` array to `TurnController` in `turnController.ts`, save active reasoning text as blocks in `closeReasoningSegment`, add trail lines to last block's tools in `recordToolComplete`, and render in `ToolTrail` when `thinkingBlocks` is present.

26. **Command autocomplete data** — The `subcommands` tuple in `CommandDef` must match what's in the TUI code. `cli_only=True` commands won't work in gateway/messaging platforms unless you add a `gateway_config_gate` and the gate is truthy. After adding live UI state, search every consumer of the old prop/helper and thread the new state through all render paths (both live `StreamingAssistant`/`ToolTrail` and transcript/pending `MessageLine` rows).

28. **`usePet()` returns `PetRender`, not `{ enabled, data }`** — The hook signature is `usePet(): PetRender` where `PetRender = { enabled: boolean, grid: PetGrid | null, kitty: KittyView | null }`. There is NO `data` property. Accessing `pet.data` causes a silent render crash (Ink swallows the error, TUI goes blank with no error message). When passing pet to a component, pass `pet` (the PetRender object itself), not `pet.data`. When checking if content is ready: `pet.enabled && (pet.grid || pet.kitty)`. PetSprite renders `pet.grid`, PetKitty renders `pet.kitty`, PetBlock wraps both.

27. **useVirtualHistory infinite loop under fast streaming** — Models streaming >500 tok/s (MiMo UltraSpeed, speculative decoding) can trigger React error #185 ("Maximum update depth exceeded") in `useVirtualHistory.ts`. The `useLayoutEffect` that calls `bumpMeasuredHeightVersion()` has `measuredHeightVersion` in its dependency array, creating a self-reinforcing loop when content changes faster than React can settle. Fix: add a `useRef` guard (`lastBumpedOffsetVersion`) so the bump fires at most once per unique `preMeasureOffsetVersion`. The TUI shows "pondering" with no output when this hits — check gateway logs for the React error. See `references/usevirtualhistory-infinite-loop.md` for the full fix and tracing path from minified error URLs.

## Merged Thinking+Tools Panel (Chronological)

The default ToolTrail has separate collapsible panels for Thinking and Tool calls. To merge them into one chronological flow with tree elbows:

1. In `thinking.tsx`, replace BOTH the thinking panel push AND the tools panel push with a SINGLE panel that renders thinking first, then tools with `TreeTextRow` (├─/└─ elbows)
2. Set `header: null` (no "thinking" label)
3. Use `cleanThinkingText(displayReasoning)` for full text (NOT `cot` which truncates to 140 chars)
4. Render tool groups with `TreeTextRow` using `rails={[]}` for top-level elbows

The system's `appendToolShelfMessage` in `liveProgress.ts` ALREADY merges tools into thinking messages when `canHoldToolShelf()` returns true (trail message with thinking, no text). So tools should naturally attach to the thinking message.

**Critical**: Remove `tool.generating` trail push in `createGatewayEventHandler.ts` — it creates duplicate "drafting terminal…" entries alongside the actual tool.start entry.

## Flat Inline Feed (CLI-style)

The default ToolTrail renders thinking and tools as separate collapsible panels. To match the CLI's chronological feed (thinking → tool1 → tool2 → ...), replace the `return` block in ToolTrail with a flat inline render:

```tsx
// ── Flat inline render (CLI-style chronological feed) ──────────
const fullThinking = hasThinking ? cleanThinkingText(reasoning) : ''

return (
  <Box flexDirection="column">
    {/* Thinking — inline dim text */}
    {fullThinking ? (
      <Box flexDirection="column" paddingLeft={2}>
        {fullThinking.split('\n').map((line: string, index: number, arr: string[]) => (
          <Text color={t.color.muted} dim key={`th-${index}`} wrap="wrap-trim">
            {line || ' '}
            {index === arr.length - 1 && reasoningActive ? (
              <StreamCursor color={t.color.muted} streaming={reasoningStreaming} visible={reasoningActive} />
            ) : null}
          </Text>
        ))}
      </Box>
    ) : reasoningActive ? (
      <Box paddingLeft={2}>
        <Text color={t.color.muted}>
          <Spinner color={t.color.accent} running variant="think" /> thinking
          <StreamCursor color={t.color.muted} streaming={reasoningStreaming} visible />
        </Text>
      </Box>
    ) : null}

    {/* Tool calls — flat chronological list */}
    {groups.map((group, index) => (
      <Text color={group.color} key={group.key} wrap="wrap-trim">
        {'  '}{toolLabel(group)}
      </Text>
    ))}

    {/* Subagents, Activity, Σ tokens, Outcome — same as before */}
    ...
  </Box>
)
```

This removes all panels, chevrons, and tree structure. Thinking and tools appear in order, like the CLI.

## Removing Tokens & Duration

To remove the `Σ ~125 total` token count and `(2.1s)` execution time:

- **Tokens**: Set `thinkingTokensLabel = null`, `toolTokensLabel = undefined`, `totalTokensLabel = null` in ToolTrail
- **Duration**: Remove `${took}` from `buildToolTrailLine()` return string and `buildVerboseToolTrailLine()`
- **Active tool elapsed**: Remove `{tool.startedAt ? ` (${fmtElapsed(now - tool.startedAt)})` : ''}` from active tool rendering

**Important**: Don't remove features without asking. The user may want them — just explain what they are first.

## Tool Emoji Pipeline (Gateway → TUI)

The gateway must explicitly send emojis. The full flow:

1. `_on_tool_start()` in `tui_gateway/server.py` loads skin `tool_emojis` via `resolve_skin()` with fallback to static `_DEFAULT_EMOJIS` map
2. Sends `payload["emoji"] = emoji` in `tool.start` event
3. TUI `createGatewayEventHandler.ts` → `turnController.recordToolStart(..., emoji)`
4. Stored in `ActiveTool.emoji`, rendered in ToolTrail active tool line
5. On completion, `completeTool()` passes `done?.emoji` to `buildToolTrailLine()`

**Pitfall**: `get_tool_emoji()` from `agent.display` returns `⚡` for ALL tools when called from the gateway because the registry is empty at gateway startup. Use static map + skin override instead.

### TUI-side toolEmoji Mapping — Sync with Active Skin

The ToolTrail has a local `toolEmoji(label)` function as fallback. This MUST stay in sync with the active skin's `tool_emojis` section (e.g. `~/.hermes/skins/walter-blue.yaml`).

Key differences to watch:
- `web_search` → 🔍 (not 🔎 — skin uses magnifying glass tilted left)
- `web_extract` → 📄 (not grouped with web_search)
- `vision_analyze` → 👁️ (grouped with browser_vision)
- `video_generate` → 🎬 (not in default registry)
- `x_search` → 🐦 (not in default registry)
- `hindsight_retain` → 🧠 (grouped with recall/reflect)

When adding a tool emoji to the skin, ALSO add it to the TUI's `toolEmoji()` function in `thinking.tsx`. The TUI function is the fallback when the gateway doesn't send an emoji.

---

## Absorbed Sub-skills (references/)

The following skills have been absorbed into this umbrella. Their full content lives in `references/` so it is preserved and searchable, but they are no longer top-level skills.

### TUI Tree Rendering (`references/tui-tree-rendering.md`)
Continuous left-rail tree rendering in Hermes TUI — tool trail, thinking steps, streaming updates, collapsible nodes, color theming, and performance. This absorbs the former top-level `hermes-tui-tree-rendering` skill; tree rendering is a display customization branch, not a separate top-level trigger.

### TUI Tree Customization (`references/tui-tree-customization.md`)
Customize the Thinking/ToolTrail tree structure in Hermes TUI — glyphs, colors, spacing, depth limits, tool categorization.

### TUI Tree Visual Patterns (`references/tui-tree-visual-patterns.md`)
Flat tree structure patterns for Hermes TUI — chronological flat trees vs nested hierarchical trees, step deduplication, line anchoring, and timestamp rendering.
