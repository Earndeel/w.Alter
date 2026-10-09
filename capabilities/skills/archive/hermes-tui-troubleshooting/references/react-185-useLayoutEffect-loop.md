# React #185: useLayoutEffect → setState feedback loop

## Diagnostic signature

TUI freezes during scroll. Console shows:

```
ERROR Minified React error #185; visit https://react.dev/errors/185
getRootForUpdatedFiber → enqueueConcurrentHookUpdate → dispatchSetStateInternal → dispatchSetState
```

The dispatch originates from a hook effect list mount — a `useLayoutEffect` that calls a state setter synchronously.

## Root cause

`useLayoutEffect` measures DOM heights via Yoga layout and calls `bumpMeasuredHeightVersion()` (which is `setState`). Each `setState` triggers a re-render, which re-runs the layout effect, which measures again, which bumps again → infinite loop. React's internal guardrail kills it at 50 nested updates.

## Fix pattern (from useVirtualHistory.ts)

```ts
const measuredHeightBumpCount = useRef(0)

// Inside the useLayoutEffect that bumps measuredHeightVersion:
const bumpMeasuredHeightVersion = useCallback(() => {
  if (measuredHeightBumpCount.current >= 3) return   // gate
  measuredHeightBumpCount.current++
  setMeasuredHeightVersion(v => v + 1)
}, [])

// Reset the gate when the effective range changes —
// a new range means genuinely new items to measure, not a feed-forward artifact.
// MUST be placed AFTER effStart/effEnd are computed (TDZ — see pitfall below).
useEffect(() => {
  measuredHeightBumpCount.current = 0
}, [effStart, effEnd])
```

Three bumps per range cycle is enough for the initial mount + one resize cascade. Beyond that, it's a loop.

## TDZ pitfall

The reset `useEffect` references `effStart` and `effEnd` — `let` variables declared later in the component body. If the `useEffect` call is placed BEFORE their declaration, it crashes on first render with a `ReferenceError` (Temporal Dead Zone). In the test harness this manifests as `expose.current` being null (the component silently crashes).

**Rule:** hooks that depend on `let` variables must be placed AFTER those variables are assigned. TypeScript catches this (`Block-scoped variable used before its declaration`) — treat those diagnostics as blockers.
