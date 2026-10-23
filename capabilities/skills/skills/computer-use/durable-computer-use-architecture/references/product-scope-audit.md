# Product-scope audit: W.Alter Computer Use

Use this reference when comparing a Hermes Computer Use implementation with the
broader W.Alter device-control product. It prevents capability inflation during
architecture reviews.

## Four boundaries to inspect

1. **UI control plane** — capture, AX/UIA/AT-SPI or DOM semantics, exact target
   identity, input delivery, and screenshot fallback.
2. **Device plane** — a local node exposing system, files, apps, packages,
   services, health, and capabilities through one device contract.
3. **Authorization plane** — capability/risk policy, explicit consent, TTL,
   audit, revocation, and a privileged helper that never gives the model a
   permanent root shell.
4. **Connectivity plane** — device identity, authenticated remote transport,
   ephemeral support sessions, expiry, and a visible stop path.

A plugin that only selects a CuaDriver backend belongs to boundary 1. Hermes'
separate terminal or file tools do not become boundary 2 merely because they can
run on the same host.

## Evidence map for the current Hermes pattern

The durable extension shape is:

```text
Hermes computer_use schema + approvals + lifecycle
        -> backend factory registry
        -> external W.Alter backend/strategy plugin
        -> CuaDriver or native OS surface
```

The following are strong UI-plane signals:

- exact `pid` + `window_id` targeting;
- AX/SOM elements with bounds and per-snapshot tokens;
- driver-level `verified` / `effect` / escalation fields;
- a fresh AX or DOM read-back after an action;
- capture-integrity diagnostics and fail-closed target clearing;
- a named plugin backend selected through `config.yaml`;
- a compatibility checker and clean-worktree patch check after host updates.

These are **not** evidence of a full device node:

- a cross-platform dependency name;
- a local CuaDriver session ID;
- an `unrestricted` or auto-approval mode;
- a generic `ok: true` action result;
- the existence of terminal/file tools elsewhere in Hermes;
- a vision screenshot without a state or domain postcondition.

## Verification vocabulary

Report the strongest level actually proven:

- **Delivery:** the event reached the driver/backend.
- **UI read-back:** AX/DOM or a fresh semantic snapshot shows the expected
  control/state transition.
- **Task postcondition:** a system or API probe proves the requested outcome,
  for example package presence, service health, file existence, or a successful
  print test.

A green unit suite normally proves contracts and policy only. Pair it with
explicit live AX/TCC evidence for a real desktop, and do not present either as
proof of package management, privilege brokering, remote support, or Android
coverage.

## Recommended maturity sequence

1. Prove the UI control plane on one real host.
2. Add a local Device Node contract with bounded app/system/file primitives.
3. Add declarative postconditions and `wait_for(predicate)` locally.
4. Add the privilege broker, consent UX, audit, TTL, and revocation.
5. Add authenticated remote connectivity and temporary support sessions.
6. Port the adapter contract to Windows and Android with platform-specific
   permission flows.

This order keeps the expensive network/distribution work from hiding an
unfinished local contract.

## Runtime versus source checkout

A Hermes audit must separate the runtime that actually imports the plugin from
the checkout intended to deliver the change. These can diverge when a managed
installation, a primary worktree, a detached worktree, or an external user
plugin is involved.

### Minimum evidence

1. Resolve the module paths with the exact interpreter used by the active
   `hermes` command (`hermes_cli.plugins`, the Computer Use tool, and the
   backend implementation).
2. Inspect `git status --short` and `git log -1` for both the active source tree
   and the checkout under review; never infer one from the other.
3. Load/discover plugins before inspecting the backend registry, then record the
   registered backend names, selected config value, and plugin error state.
4. Search the intended checkout for the extension seam and the model-facing
   tool. A working installed `walter` backend does not prove that the checkout
   contains `register_computer_use_backend` or equivalent wiring.
5. Run the project test wrapper against the actual changed paths, and run a
   compatibility checker without starting a GUI session. Report test counts
   and checker output, not just “it works”.

Classify the result explicitly:

- **Operational runtime only** — the active install resolves the plugin and
  backend, but the source checkout lacks or does not contain the same seam.
- **Source-integrated only** — the checkout contains the implementation, but
  the active runtime still loads an older package or cannot discover the plugin.
- **Integrated** — both surfaces resolve the same backend and targeted tests
  pass.

This distinction is especially important for W.Alter Computer Use: a thin
policy backend around CuaDriver, a live legacy Mac screen server, and a generic
Device Node are three different maturity levels. A live `/health` response or a
passing policy suite can validate transport/policy plumbing while leaving Mac
TCC, semantic UI read-back, system primitives, privilege brokering, Android,
and temporary support enrollment unproven.
