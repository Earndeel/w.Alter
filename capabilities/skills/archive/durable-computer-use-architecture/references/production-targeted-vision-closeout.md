# Production targeted-Vision closeout gates

Use this note when closing the last Vision gap of an AX-first desktop operator. It records only durable contracts; a failed smoke is evidence, not a recommended recipe.

## Architecture invariants

- Hermes LLM remains the sole planner. Vision is one bounded sensor call, never an embedded workflow engine.
- If the public `computer_use(goal)` schema must remain byte-stable, keep Vision behind the existing goal handler. A plugin action extension still alters the effective action enum.
- AX/native is preferred when it exposes a reliable actionable ref. Raw AX geometry for a non-actionable element may corroborate a Vision box, but cannot independently authorize a click.
- The positive path is: AX insufficiency proved → exact window/region crop → one sensor call → snapshot/crop/geometry-bound visual ref → one LLM-selected primitive → targeted recapture/read-back.

## Geometry contract

Derive mapping from requested crop `(x,y,w,h)`, returned image dimensions, source capture dimensions, window/display geometry, and explicit `scale_x`/`scale_y`.

- Never assign confidence `1.0` merely because a returned image is proportionally resized.
- Non-uniform positive scales are not automatically ambiguous: if source dimensions and crop bounds are explicit and coherent, X and Y can be mapped independently. Confidence should remain below perfect and reflect the evidence.
- Missing source dimensions, non-positive dimensions/scales, out-of-source crop bounds, or inconsistent target identity are ambiguous: set `geometry_ambiguous=true`, `adaptation_required=true`, issue no actionable ref, and perform no driver click.
- Preserve the image's real MIME type. Do not label JPEG bytes returned by a zoom endpoint as PNG merely because the legacy field is named `png_b64`.

## Visual-ref contract

A visual ref binds all of:

- snapshot/generation;
- PID and native window ID;
- requested crop and returned dimensions;
- source capture dimensions and both scales;
- target bounds in crop coordinates;
- crop digest;
- short TTL and one-use state.

Invalidate refs on a new incompatible snapshot, crop, target, or generation. Consuming a ref must be atomic and one-use. Verification may retain an immutable consumed-target record for read-back, but it must not rearm the action.

## Cross-modal corroboration

A conservative Vision result may be corroborated by a current, non-actionable AX candidate only when both are in the same proven coordinate basis and overlap strongly. Keep both the raw sensor confidence and the cross-modal agreement in evidence. Never lower a confidence threshold simply to pass a smoke, and never let corroboration become an app-specific selector.

## TDD and closeout sequence

1. Write failing tests for geometry scaling/MIME, valid visual ref, fresh-crop invalidation, stale snapshot rejection before driver, one-use consumption, and ambiguous geometry before driver.
2. Implement the smallest consumer behind the existing front door.
3. Run targeted Vision tests.
4. Run one real positive smoke and one negative stale/geometry smoke. Count Vision calls and full screenshots explicitly.
5. Only after both smokes pass: full tests once, directly affected E2E, targeted mini-review, then transactional deployment preserving rollback.
6. If the positive smoke fails closed, stop deployment. Do not call the operator complete, do not convert failed attempts into a workflow, and do not keep retrying tiny/uncertain targets merely to manufacture a PASS.

## Evidence shape

Record: AX fallback justification, crop region/dimensions, full screenshots, Vision calls, visual-ref identity, geometry confidence/ambiguity, blind-click flag, driver reach, verification result, Computer Use calls, LLM decisions, AX observations, device RPC, total latency, and Operator latency. A sensor call refused before action is valid safety evidence, but it is not the required positive production proof.
