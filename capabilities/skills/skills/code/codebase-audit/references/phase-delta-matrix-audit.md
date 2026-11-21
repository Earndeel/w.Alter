# Phase / Roadmap Delta-Matrix Audit (A–M style)

Use when asked to audit a staged product or plugin **against an abstract phase
list** ("phases A–M", "Lots 2.x", "production-complete") and produce a
prioritized existing/reusable/missing matrix, a version target, and a set of
safe end-to-end scenarios. Read-only; do not edit files.

## 1. The phase spec may not live in the repo — say so
The phase list is often external user intent, not a checked-in document. Search
the repo (`grep -ri "phase\\|Phase A"`) AND prior sessions before assuming it
exists. If it is absent, **reconstruct the phase model from the repo's own
certified artifacts** — its scenario manifest (`benchmarks/scenarios.json`
A–H), its lot roadmap (a `MIGRATION.md` listing Lots 2.x with per-lot gates),
and its `BACKLOG.md` / `should_fix` list. Label the reconstruction explicitly
in the report ("no in-repo A–M spec; mapped against certified A–H + lot
roadmap") so you don't fabricate an authority. Extending certified scenarios
A–H to A–M as "proposed hardening" is legitimate; presenting your own phases
as the user's spec is not.

## 2. Ground truth before writing anything
- **Run the full suite once up front** read-only
  (`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`). A
  green suite is the baseline every "existing/reusable" cell is credited from.
- **Verify the deployed bundle matches the candidate.** Compare hashes of the
  live plugin dir vs the repo `deploy/` candidate (`md5sum`), and read the live
  `plugin.yaml` version + the active config (`backend`, observer flag). A
  byte-identical candidate + matching version is a strong "existing" datapoint;
  divergence means the candidate is NOT what is running.
- **Check the host platform and transport.** `uname` first. This class of
  operator often runs on a Linux VPS and drives a **remote** macOS via a driver
  shim (`driver_command: .../walter-cua-remote`) over SSH/Tailscale to a remote
  cua-driver. Local `cua-driver` presence does NOT mean there is a local macOS.
  State this explicitly — it changes every "live macOS E2E" claim.

## 3. Delta-matrix shape (the core deliverable)
One row per phase; columns: **goal | existing | reusable | missing**. Then a
hard **prioritized ordering** (not alphabetical): the missing cells that gate
the most phases go on top. Anchor every cell to a real symbol/file
(`launch_app` + `native_launch_state`; `compact_ax_state`; `arm_native_refs`)
so "reusable" means *this concrete function*, not "conceptually similar".

Distinguish three reuse classes, mirroring the executable/interface/dead-end
split:
- **existing** — wired into the deployed production path (proven by a live
  smoke or an integration test through the real entry point).
- **reusable** — present in a sibling module or an archived lot (e.g.
  `adaptive_operator/*` contracts, device-node idempotency patterns) but NOT in
  the active plugin; needs a seam, not a rewrite.
- **missing** — genuine gap; name the L-phase that forces it.

Cross-check each "missing" against the repo's own documented remaining-gaps
list (an architecture doc often enumerates exactly what blocks Active Mode).

## 4. Version targeting heuristic
Given a `should_fix` backlog and "one final review": propose a **minor bump
(1.3.0 → 1.4.0), not a major (2.0)** unless a genuinely new production
capability ships. Major bumps invite re-certification of the whole surface;
for a review-gated final release keep the model-facing surface constant and
let the backlog drive the patch/minor. Justify the chosen number in one line.

## 5. Safe E2E scenario design (no app-specific runtime recipes)
Provide a concrete scenario list (≈10–15) that exercises the plugin through
installed apps WITHOUT embedding app workflows in the runtime. Rules that made
the difference:
- Use only **safe native primitives**: positional, off-screen-safe launch /
  open_url / observe → AX ref → invoke → verify. Never a hardcoded
  click-location-for-app-X.
- Include the **fail-closed L2 probe** (a destructive phrasing like
  `supprime`/`quit` must return `needs_confirmation` with `device_rpc=0`).
- Include the **stale-ref adaptation** case (deliberately force a superseded
  snapshot, assert no blind re-click).
- Include a **no-op baseline** (two captures, no action → AX unchanged) — this
  is the guard that bounds false positives from the verifier.
- Include a **deploy/rollback drill** as one scenario when a transactional
  deploy script exists.

## 6. Blockers to always enumerate
- **macOS TCC permission tiers mapped to phases.** Accessibility → AX
  roles/labels/AXPress; Screen Recording → any crop/screenshot (vision/visual
  click); Input Monitoring → synthetic clicks/keys. A-D that avoid pixels pass
  without them; any vision path re-introduces Screen Recording. Name which
  phase each permission gates.
- **User-presence fields hardcoded unknown** (`presence.* = None`) means any
  "active user / background-first" phase (H) is **untestable on the current
  seam**, not merely unoptimized.
- **No pinned baseline / no CI** ⇒ green tests today are an unpinned snapshot,
  not a gate.

## 7. Pitfall specific to this class: aggregate-smoke attestation
Do not trust the top-level `assertions`/`passed` bool of an aggregate live-smoke
artifact. In practice the per-scenario JSON can pass (`smoke-c.json`:
`passed=true`, AXPress performed, verified via targeted observation) while the
aggregate `live-smokes.json` reports the same scenario `false` due to a
post-run aggregate bookkeeping bug. **Read the per-scenario artifact and
reconcile the aggregate against it**; report the aggregate discrepancy as a
finding (blocker for any gate that consumes the aggregate), don't treat the
scenario as genuinely failed.

## 8. Report shape
Lead with outcomes, keep tight (it returns to a parent agent context): state
facts + a markdown delta matrix + version target + the scenario list + blockers.
No process replay.
