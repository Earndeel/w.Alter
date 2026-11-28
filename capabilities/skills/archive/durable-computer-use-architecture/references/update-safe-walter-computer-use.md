# Update-safe W.Alter Computer Use reference

## Durable paths used by the current W.Alter installation

- User plugin: `/root/.hermes/plugins/walter-computer-use/`
  - `plugin.yaml` declares a user `backend` plugin.
  - `__init__.py` registers the named `walter` backend and the
    `safe-window` strategy.
  - `test_walter_computer_use.py` exercises target filtering without a live
    desktop.
  - `README.md` documents backend/strategy/vision separation.
- Recovery patch: `/root/.hermes/overrides/walter-computer-use.patch`
- Compatibility check: `/root/.hermes/scripts/check-walter-computer-use.py`
- Patch refresh: `/root/.hermes/scripts/refresh-walter-computer-use-override.py`

The exact `/root` prefix is deployment-specific; use `HERMES_HOME` and
`HERMES_AGENT_ROOT` when adapting this reference to another profile or host.

## Core seam

The minimal host-side seam currently consists of:

- `tools/computer_use/backend.py`: `register_backend_factory`,
  `get_backend_factory`, and `registered_backend_names`;
- `tools/computer_use/tool.py`: resolves `HERMES_COMPUTER_USE_BACKEND` first,
  then `computer_use.backend` from config, then the built-in `cua` path;
- `hermes_cli/plugins.py`: `PluginContext.register_computer_use_backend`;
- `hermes_cli/config_defaults.py`: `computer_use.backend` and the generic
  `computer_use.capture_strategy` defaults.

The plugin does not override the `computer_use` tool, so Hermes continues to
own approvals, permission modes, session caches, and multimodal response
formatting.

## Post-update sequence

1. Run the normal Hermes update procedure from the `hermes-agent-update` skill.
2. Run `python3 ~/.hermes/scripts/check-walter-computer-use.py`.
3. If it reports a missing seam or backend, inspect the update diff before
   starting any desktop session.
4. Refresh or apply the targeted patch only after checking `git status` and
   preserving unrelated user work:

```bash
python3 ~/.hermes/scripts/refresh-walter-computer-use-override.py
# After an update conflict, inspect first, then use:
git apply --3way ~/.hermes/overrides/walter-computer-use.patch
```

5. Run the Computer Use and plugin test subsets with `scripts/run_tests.sh`.
6. Only then perform live AX/TCC validation on the Mac. Software compatibility
   does not prove a real desktop interaction.

## Vision model evolution

Do not edit the backend to change the vision model. Set the existing
`auxiliary.vision.provider` and `auxiliary.vision.model` config values, start a
new Hermes session, and run the vision-routing tests. An explicit auxiliary
route takes precedence; otherwise the routing helper fails closed to auxiliary
vision when main-route image support is unknown.

## Failure interpretation

- Plugin absent or disabled: configuration is not active; do not call the
  system healthy.
- Backend seam absent: incompatible Hermes checkout; do not silently use the
  built-in backend.
- Strategy returns no target: capture must fail without reusing an old window.
- AX/TCC validation pending: software path is verified, native desktop path is
  not yet proven.
