---
name: durable-computer-use-architecture
description: "Use when making Hermes Computer Use durable and extensible."
version: 1.3.2
author: W.Alter
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [computer-use, cua-driver, plugins, update-safe, vision-routing, architecture]
    related_skills:
      - computer-use
      - hermes-agent-update
      - systematic-debugging
---

# Durable Computer Use Architecture

## Purpose

Use this skill when a Hermes Computer Use customization must survive Hermes
updates and remain easy to evolve. The target is a small, explicit extension
boundary — not a second agent, a background orchestration service, or a
collection of monkey-patches that only one checkout understands.

This skill covers architecture and verification. The protected
`computer-use` skill remains the authority for operating the desktop safely;
`hermes-agent-update` remains the authority for the general Hermes update
procedure.

## Non-negotiable design goals

1. **Update survival** — W.Alter policy code lives outside the Hermes checkout
   whenever possible. User plugins and profile configuration are durable across
   `hermes update`; local core edits are treated as a temporary compatibility
   seam and must have a recovery patch.
2. **Core stays thin** — Hermes owns the public tool schema, approvals,
   session lifecycle, backend lifecycle, and multimodal result plumbing. The
   extension owns backend policy and strategy selection.
3. **Strategy/model interchangeability** — a new capture technique or native
   backend is a named implementation behind a stable contract. Changing the
   vision model is configuration, not a Computer Use rewrite.
4. **Fail closed** — if the host contract disappears or changes incompatibly,
   the extension must report incompatibility. Never silently fall back to the
   built-in backend while claiming the custom policy is active.
5. **Evidence over reassurance** — prove plugin discovery, backend resolution,
   strategy behavior, config validity, tests, and patch applicability with real
   tool output.

## Architecture

Keep the runtime split like this:

```text
Hermes core
  computer_use schema
  approval + permission mode
  session-owned backend cache/lifecycle
  multimodal capture response
        |
        | stable backend factory / ComputerUseBackend contract
        v
User plugin outside checkout
  W.Alter backend adapter
  named capture strategy registry
  target selection + policy
  compatibility check
        |
        v
cua-driver / native OS surface
```

The plugin should subclass or compose the host Cua backend only at the narrow
contract boundary. It should not replace `computer_use` merely to reimplement
approval, action dispatch, or result shaping.

## Implementation procedure

### 1. Inspect before editing

Read the actual current implementations and trace usages:

- `tools/computer_use/backend.py` — dataclasses and abstract contract;
- `tools/computer_use/tool.py` — backend selection and lifecycle;
- `tools/computer_use/cua_backend.py` — driver transport and capture;
- `tools/computer_use/vision_routing.py` — native vs auxiliary vision policy;
- `hermes_cli/plugins.py` — plugin registration and trust gates;
- `hermes_cli/config_defaults.py` — canonical config section;
- `hermes_cli/update_cmd.py` — autostash and restore behavior.

Check `git status --short` and `git diff` first. Never reset, clean, or stash
blindly when the checkout contains user work.

### 2. Choose the smallest extension seam

Prefer, in order:

1. Existing `ComputerUseBackend` variation;
2. a small backend-factory registry exposed to plugins;
3. a named plugin backend selected through `config.yaml`;
4. a separate strategy registry inside the plugin.

Do not create a second model tool unless the existing tool cannot express the
capability. Do not use `override=True` for `computer_use` when a backend seam
solves the problem; tool overrides require privileged operator approval and
couple the plugin to more Hermes internals.

### 3. Keep configuration canonical

Behavioral settings belong in `config.yaml`, never in a new user-facing
`.env` variable. A generic shape is:

```yaml
computer_use:
  backend: walter
  capture_strategy: safe-window

auxiliary:
  vision:
    provider: <provider>
    model: <vision-model>
```

The active Computer Use backend and capture strategy should be independent of
the active vision model. The existing vision-routing policy should decide:

- keep the image native when the main provider/model is known to accept it;
- use the explicit `auxiliary.vision` route when configured;
- route to auxiliary vision when the main route is unknown or unsafe.

Changing `auxiliary.vision.provider` or `.model` should not require editing the
native backend.

### 4. Design strategies as named policies

A strategy should accept normalized window metadata and return either one
validated exact target (`pid` + `window_id`) or no target. It should:

- reject off-screen/stale rows;
- avoid desktop/helper surfaces for unqualified captures;
- reject explicit zero/tiny geometry while treating missing geometry as
  unknown rather than inventing a false measurement;
- preserve exact-target and explicit app semantics;
- delegate the actual capture/action to the host backend.

Add a new strategy by registering a new name in the external plugin. Keep the
strategy deterministic and unit-testable with synthetic window dictionaries;
do not require a live desktop for policy tests. When one application exposes
wide menu/toolbar helper strips before its main surface, preserve z-order among
surfaces whose area is comparable to the application's largest candidate
instead of relying on a fixed height threshold. Preserve legacy ordering when
geometry is absent.

### 4a. Keep local recovery bounded and verdict-driven

A backend plugin may collapse one model-visible recovery round when the driver
has proved the first input was a no-op. The safe initial pattern is narrow:

- start from a current element capture and remember only usable element centers;
- retry only `effect=suspected_noop` with structured `recommended=px`;
- reissue the same background pointer action once at the remembered center;
- never retry `effect=unverifiable` without a fresh semantic check;
- never auto-escalate to page or foreground delivery, because those rungs have
  separate targeting and approval requirements;
- cap the local loop and return its attempt/transition/stop trace in result
  metadata.

Benchmark this as a reduction in **model-visible control rounds**, not as an
invented wall-clock speedup. The recovery path still performs two driver calls;
it saves one model decision round only when the deterministic retry succeeds.

### 5. Add a compatibility boundary

At plugin registration and factory construction, verify the minimum host
contract (`register_computer_use_backend`, backend lifecycle, capture, and
window enumeration). If missing, raise a clear compatibility error. Do not
catch it and choose `cua` silently.

The compatibility check must not start cua-driver or perform a visible desktop
action. A post-update check should instantiate the backend without calling
`start()` and report the configured backend, strategy, and host version/path.

### 6. Protect remaining core edits

If a small core seam is necessary before upstreaming it:

- keep the custom behavior in a focused diff;
- save a targeted patch outside the checkout, under the active Hermes home;
- add a re-runnable refresh script;
- test that the patch applies to a clean checkout at `HEAD`;
- run the post-update compatibility checker after every Hermes update.

Hermes' updater autostashes tracked and untracked changes and attempts to
restore them. That protects content from loss, but a structural conflict can
reset the working tree while leaving the stash intact. A recovery patch and a
fail-closed checker are therefore required for local core seams.

### 7. Treat state databases as durable data

Never delete a `state.db` because it is untracked, appears inside a checkout,
or has a surprising size. First resolve the active `HERMES_HOME` with
`get_hermes_home()` or `hermes config path`, then confirm the exact database
path used by the running code. Inspect metadata only; do not open or copy the
database unless the user explicitly asks. A repo-local zero-byte database may
be an unused artifact, but deletion still requires explicit scope confirmation
because Hermes state databases contain session and tool-call history.

Cleanup must be narrowly scoped: remove only generated caches that were
identified as disposable, never run `git clean` or a global stash against a
mixed checkout, and leave unrelated user modifications in place. Run the
regression suite before cleanup and the compatibility checker afterward with
`PYTHONDONTWRITEBYTECODE=1` so verification does not recreate bytecode caches.
See `references/state-and-cleanup-safety.md` for the exact decision sequence.

## Verification checklist

Run the canonical Hermes test wrapper, not direct pytest:

```bash
scripts/run_tests.sh tests/tools/test_computer_use_*.py
scripts/run_tests.sh tests/hermes_cli/test_plugins.py tests/hermes_cli/test_plugins_cmd.py
scripts/run_tests.sh tests/hermes_cli/test_config.py tests/hermes_cli/test_config_loader_e2e.py
```

Also verify:

```bash
hermes config check
python3 ~/.hermes/scripts/check-walter-computer-use.py
.venv/bin/ruff check <changed-files>
git diff --check
```

For update survival, use a temporary clean worktree and run:

```bash
git worktree add --detach /tmp/cu-verify HEAD
git -C /tmp/cu-verify apply --check ~/.hermes/overrides/walter-computer-use.patch
git worktree remove --force /tmp/cu-verify
```

Report real counts and command results. Separate software-contract evidence
from live AX/TCC validation: a green policy test does not prove that a locked
Mac desktop will accept a real click.

## Anti-patterns

- Custom logic only in `tools/computer_use/cua_backend.py` with no external
  recovery path;
- monkey-patching private functions at every tool call;
- duplicating the complete Computer Use schema and approval layer in a plugin;
- selecting a vision model by changing native backend code;
- adding a new `HERMES_*` behavior variable instead of a config key;
- silently falling back to `cua` after a plugin/host incompatibility;
- claiming “update-safe” without checking the clean-worktree patch path;
- testing only mocked tool dispatch while skipping plugin discovery and config
  resolution.

## Reference

See `references/passive-shadow-observation-seams.md` for choosing between a
persisted-event sidecar, `post_tool_call`, middleware, and backend wrapping;
it also specifies cursor/quarantine semantics, private idempotent spooling,
fail-visible supervision, honest benchmark labels, archive sanitization, and
independent fail-closed closure of a sealed artifact. In particular, a reviewer
that times out or emits no terminal structured verdict is not a pass; review the
exact extracted archive, keep action/evidence denominators distinct, and publish
an external certificate when the archive hash must remain frozen.
See `references/live-observation-bus-seam-audit.md` when full live transport
facts are required before backend conversion. It covers the fidelity ladder,
MCP/CLI duplicate-event traps, the validated integrated-plugin return-boundary
pattern, opt-in and fully bounded telemetry, non-tautological source→emitted
native-ref accounting, alternating same-session benchmarks, dynamic deployed
plugin surface equivalence, transactional rollout/rollback, deterministic
sealing, and independent fail-closed closure gates. Treat private transport
interception as an audited compatibility seam, not the durable public contract;
prefer a host-owned final-resolved-result callback when Hermes exposes one.
Use `scripts/compare_plugin_surface.py` to compare baseline/candidate plugins in
isolated Hermes homes under one certified runtime, and
`scripts/seal_reviewed_commit.py` as a generic fail-closed deterministic archive
starter after two structured reviews pass.
See `references/update-safe-walter-computer-use.md` for the durable boundary,
verification evidence shape, and the current recovery/check scripts. See
See `references/computer-use-v1-audit-map.md` for the line-anchored file→
responsibility cartography of the active V1 core + walter plugin (primitive
inventories, verify→escalate ladder, vision routing, goal action, compact AX)
and the P0/P1/P2 gap inventory toward an Adaptive Universal Operator. See
`references/observation-v2-data-contract.md` for the raw-backend → observation
data contract: exact CaptureResult/ActionResult/UIElement shapes, where native
element_token/snapshot/bounds live and where they are dropped from model-facing
JSON, result-object vs backend-instance-state mutation lifetimes, the
snapshot-token stale guard (and that no explicit generation counter exists),
the additive honest-unknowns contract, and the proposed immutable event schema.
See
`references/product-scope-audit.md` when separating a UI backend from the
Device Node, privilege broker, and remote-session product planes. See
`references/macos-operator-completion-guardrails.md` for the macOS completion
program: fresh-session dynamic action/schema verification, unknown-app
inspection rather than `unsupported_goal`, live driver-schema reuse, additive
ActionResult contracts, presence/policy enforcement on every primitive,
short-lived visual refs, and the single-review/E2E/cutover completion gate. See
`references/device-node-vertical-slice.md` for the deployed-scope audit,
idempotency, approval, audit-chain, CuaDriver, shipped-artifact validation,
end-to-end session recovery, and multi-channel error-disclosure guardrails
learned from a live macOS/Tailscale vertical slice. See
`references/active-interruption-and-presence-wiring.md` when promoting shadow
contracts to enforcing runtime policy: the self-contained `runtime.py`
adapter (repo modules are NOT on `sys.path` at Hermes runtime), the presence
TTL `UserPresenceCache`/SSH-probe wiring, the L0/L1/L2 × origin × presence
interruption matrix, the "a failing test IS the spec" TDD read, and the
fail-open-on-unknown-presence / prose-derived-L2 / hot-path-SSH / hardcoded-TTL
pitfalls. These references are
deliberately operational; keep evolving details there instead of inflating
this class-level skill.

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/product-scope-audit-section.md` — Product-scope audit (backend versus device product): the front-door checklist, approval propagation, effect verification, identity-bound pixels, goal-router evidence.

