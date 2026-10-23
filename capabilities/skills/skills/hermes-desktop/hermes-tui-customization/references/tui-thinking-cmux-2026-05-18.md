# TUI thinking + cmux notification fixes — 2026-05-18

## Durable lessons

### Thinking panel behavior preferred by Lucas
- Only one thinking panel should be open at a time.
- While reasoning is live: open the panel, show the spinner, and stream the current reasoning visibly.
- When reasoning finishes: remove the spinner entirely; do not freeze it with `running={false}`.
- Keep the completed thinking content visible as a truncated cached preview until fresh reasoning arrives.
- Do not auto-collapse completed thinking with timers.

### Implementation pattern
In `ui-tui/src/components/thinking.tsx`:
- Cache the last non-empty reasoning with `useRef` so `turnController.clearReasoning()` does not blank the panel between turns.
- Use `thinkingLive = reasoningActive || reasoningStreaming` as the single live-state gate.
- Render live content with `mode={thinkingLive ? 'full' : 'truncated'}` and `reasoning={thinkingLive ? displayReasoning : cot}`.
- Header branch should render `<Spinner ... />` only when `thinkingLive` is true; completed state is dim static `Thinking` text.
- If removing helper state like `showDots`, grep both source and built dist; esbuild build may pass while TypeScript references remain.

### Effect ordering pitfall
Do not put `tools.length` in the same `useEffect` that resets `openThinking` from visibility config. Tool starts can otherwise collapse an in-progress thinking panel. Split effects:
- one effect for `openThinking`, `openSubagents`, `openMeta` keyed by visibility fields;
- one effect for `openTools` keyed by `visible.tools` and `tools.length`.

### Type/build guard
`npm run build` bundles with esbuild and does not reliably catch all TS mistakes. For TUI changes, run targeted guards such as:

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
grep -R "showDots" -n src dist || true
npm run type-check -- --pretty false 2>&1 | grep -E "showDots|recordToolStart|<changed-file>" || true
```

### turnController emoji signature
If `createGatewayEventHandler.ts` passes `ev.payload.emoji` into `turnController.recordToolStart`, update the method signature to accept `emoji?: string` and store it in `ActiveTool`; otherwise typecheck catches the mismatch.

### cmux notification delivery
Writing raw OSC directly to arbitrary `/dev/pts/N` is unreliable through nested tmux. The durable pattern is `/usr/local/bin/cmux-notify` emitting DCS tmux passthrough (`ESC P tmux ; <OSC 777> ESC \\`) to pts devices running `tmux: client`, so it traverses root tmux → ubuntu tmux → SSH → cmux → macOS notification.

### Restore persistence
Whenever adding or modifying TUI source overrides, also update:
- `~/.hermes/tui-overrides/<file>`
- `~/.hermes/scripts/restore-tui-design.sh`

In this session, `turnController.ts` had to be added to restore copying alongside `thinking.tsx`, `createGatewayEventHandler.ts`, and `gatewayTypes.ts`.