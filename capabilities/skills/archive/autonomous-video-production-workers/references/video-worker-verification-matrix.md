# Video worker verification matrix

Session-derived checks for an isolated worker built from a validated media-agent bundle.

## Bundle integrity

- Enumerate archive members before use.
- Resolve the real package root when the archive includes a same-named top-level directory.
- Compare member count, byte totals and SHA-256 values after materialization.
- Keep immutable contracts, playbooks and deterministic media scripts together with the package.

## Effective Hermes state

- The target profile reports the intended model/provider and has its own `SOUL.md`.
- The profile config passes `config check`.
- Skill discovery shows the orchestrator skill exactly once.
- The effective tool inventory is checked with the profile selector, not inferred from a YAML fragment.
- A generation worker keeps `video_gen`; unrelated routes such as BFL, voice, web, memory and delegation are absent unless explicitly required.

## Local runtime evidence

- The package self-test uses synthetic media and reports schema parsing plus media checks as passing.
- A temporary work initializer creates the expected state and directory structure.
- A sample mission validates against its JSON contract.
- No paid image/video request is submitted during installation validation.

## Delivery boundary

- A blank queue identifier remains blank rather than being guessed.
- Drive/Sheets/Telegram support in a playbook is not proof that an adapter or account is configured.
- Missing delivery capability is reported as an explicit `BLOCKED_*` or `NEEDS_INPUT` state.
