# Computer Use operations reference

## Evidence ladder

| Layer | Evidence | Does not prove |
|---|---|---|
| Permission | TCC/driver authorization state | usable pixels or AX target |
| Capture | valid frame, substantive coverage, current target | semantic action success |
| AX | current role/label/value/state/frame | visual appearance or task outcome |
| Delivery | driver accepted the action | postcondition |
| Readback | changed semantic/visual state | broader business outcome |
| Task postcondition | app/API/system evidence | unrelated scopes |

Stop at the first failed prerequisite. Treat `unverifiable` and timeout-after-dispatch as unknown completion; refresh state before deciding, and never auto-replay a mutation.

## Window/coordinate decision table

- Preserve exact PID/window ID when pinned by the caller.
- Prefer substantive on-screen windows over helper strips when geometry is present.
- A missing bounds field is unknown, not zero; preserve legacy ordering for old payloads.
- Use element tokens/snapshot-bound indices before coordinates.
- Use coordinates only from the newest pixel-bearing capture with matching target and scale metadata; never hard-code Retina conversion.
- If all candidates are off-screen or invalid, return no target and clear active state.

## Remote Mac gate

Validate, in order: direct target route, interactive Aqua session, signed permission-owning driver, non-prompting permissions, current window list, real capture integrity, AX tree, harmless reversible read/action, fresh readback. A VPS-side binary or tunnel health check covers only transport; it does not cover Mac TCC or pixels.

## Restoration gate

Record a baseline screenshot plus stable AX anchors; define target geometry; prefer app Reset/Default; use current refs; verify pane side/visibility, main content placement, and absence of transient overlays in both screenshot and AX. End the automation session only after the final readback.

## Benchmark gate

Freeze IDs/config/fixture/warmness. Report every sample and separate cold start, typical latency, tail spikes, grounding pass rate, action error rate, retry count, and verified completion. Never call a screenshot-only or invalid-capture test a full Computer Use benchmark.
