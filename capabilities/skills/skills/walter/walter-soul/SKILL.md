---
name: walter-soul
description: "Use when Monsieur talks about W.Alter's identity, its SOUL / personality / rules, how it presents itself, or wants them changed for Hermes, Claude Code, Codex or DSH: where the identity lives, how to edit it and render it to every runtime."
---

# W.Alter's identity (walter-soul)

Checked on the VM on 2026-11-01 (`walter-soul check`: hermes, claude-code, codex, dsh, agent all ok).

## Where things are

- **The identity belongs to the instance**: `/instances/monsieur/soul/identity.md` (who W.Alter is) and
  `/instances/monsieur/soul/rules.md` (its rules), optional per-runtime additions in
  `/instances/monsieur/soul/runtimes/` (today `agent-cli.md`). That folder is its own git repository: its
  post-commit hook runs `walter-soul sync`.
- **The software is neutral**: `/walter/core/identity` (renderer `bin/walter-soul`, neutral runtime adapters
  `runtimes/*.md` with `{{owner.address}}`-style placeholders, defaults for a new instance). Never put Monsieur's
  identity in `/walter/core/identity`.
- **Generated targets** (one-way, never edit by hand): Hermes `/root/.hermes/SOUL.md`, Claude Code
  `/opt/walter-profiles/claude-code/CLAUDE.md`, Codex `/opt/walter-profiles/codex/AGENTS.md`, DSH
  `/opt/walter-profiles/dsh/AGENTS.md`, plus the MCP `walter_profile`. Locations: `/walter/core/identity/config/targets.toml`
  overridden by `/instances/monsieur/config/soul/targets.toml`. The curated user profile included by
  `{{include profile}}` is `/root/.hermes/memories/USER.md`.
- Opening a session in `/opt/walter-profiles/{claude-code,codex,dsh}` = W.Alter mode; `/root` = technician mode.

## Change the identity or the rules

1. Edit `/instances/monsieur/soul/identity.md` or `rules.md` (or a file in `runtimes/`). Keep it concise: Monsieur
   asked for a much more concise SOUL.
2. `git -C /instances/monsieur/soul commit -am "<what changed>"` — the hook renders every target.
3. `walter-soul check` — every target `ok`. To preview one target: `walter-soul render hermes` (or `claude-code`,
   `codex`, `dsh`, `agent`); its path: `walter-soul path <target>`.
4. Hermes reads SOUL.md at session start: a running Hermes session keeps the old text until a new session
   (graceful restart if needed: `hermes gateway restart`).

## If a target was edited by hand

`walter-soul sync` refuses to overwrite it (exit 2) and keeps a copy in `/instances/monsieur/backups/soul-drift/`.
Port the change into the sources, commit, then `walter-soul sync --force`.

## History

The former skill `walter-operating-mode` (June–October 2026, identity written by hand inside a skill) is retired:
read it by name only as history.
