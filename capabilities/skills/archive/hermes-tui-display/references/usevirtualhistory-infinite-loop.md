# useVirtualHistory Infinite Loop (React Error #185)

## Symptom
- TUI shows "pondering" status indefinitely with no output
- Browser console (or gateway logs) shows React error #185: `Maximum update depth exceeded`
- Error URL maps to minified `entry.js` — trace via `errorBoundary.tsx` → `console.error` intercept
- Affected file: `ui-tui/src/hooks/useVirtualHistory.ts`

## Root Cause

The `useVirtualHistory` hook manages virtual list measurement and scrolling. A fast-streaming model (>1000 tok/s, e.g. MiMo UltraSpeed) triggers an infinite setState loop:

```
useLayoutEffect → bumpMeasuredHeightVersion()
  → setState(measuredHeightVersion + 1)
  → re-render
  → useLayoutEffect fires again (measuredHeightVersion changed)
  → bumpMeasuredHeightVersion() again
  → ∞ loop → React error #185
```

The dependency array of the `useLayoutEffect` includes `measuredHeightVersion`, and the effect body calls `bumpMeasuredHeightVersion()`, creating a self-referential cycle. At normal streaming speeds, the early-exit conditions (`!containerRef.current`, height unchanged) break the loop before React notices. At >1000 tok/s, content changes fast enough that the height check passes on every iteration, sustaining the loop.

## Fix: Ref-Based Guard

Break the cycle by tracking the last bumped version in a ref (which doesn't trigger re-renders):

```typescript
// Add at top of useVirtualHistory hook:
const lastBumpedOffsetVersion = useRef<number>(-1)

// In the useLayoutEffect that calls bumpMeasuredHeightVersion:
// BEFORE:
if (preMeasureOffset !== scrollOffset) {
  bumpMeasuredHeightVersion()
}

// AFTER:
if (preMeasureOffset !== scrollOffset && lastBumpedOffsetVersion.current !== preMeasureOffsetVersion) {
  lastBumpedOffsetVersion.current = preMeasureOffsetVersion
  bumpMeasuredHeightVersion()
}
```

The guard ensures `bumpMeasuredHeightVersion()` is called at most once per unique `preMeasureOffsetVersion`, regardless of how many times the effect fires during fast streaming.

## Verification

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
# Then test with MiMo UltraSpeed or any model that streams >500 tok/s
```

Test suite in the current checkout:
```bash
cd ~/.hermes/hermes-agent/ui-tui
npx vitest run --reporter=verbose src/__tests__/virtualHistoryOffsetCache.test.ts src/hooks/__tests__/useVirtualHistory* 2>&1
```
- Passing result observed on 2026-06-25: `6 passed` from `virtualHistoryOffsetCache.test.ts`.
- Some older checkouts may have `src/hooks/__tests__/useVirtualHistory*`; include it when present. The guard must not break normal measurement behavior.

## Key Insight

Ink/React `useLayoutEffect` + `setState` in the dependency chain is fragile under high-frequency updates. The standard React pattern for breaking such loops is a ref-based guard:
- Refs don't trigger re-renders
- Track "already done for this version" via `useRef`
- This pattern applies to any `useLayoutEffect` that calls a state-updating function whose value is in its own dependency array

## Minified Error Tracing

When you see a minified React error URL like:
```
https://reactjs.org/docs/error-decoder.html/?invariant=185&args[]=Maximum%20update%20depth...
```

1. The error is always React's "Maximum update depth exceeded"
2. Find the source by searching for `setState` calls inside `useLayoutEffect` in the component tree
3. In Hermes TUI, check `hooks/` directory — `useVirtualHistory.ts` is the primary suspect
4. Look for patterns where the effect both reads AND writes the same state variable
