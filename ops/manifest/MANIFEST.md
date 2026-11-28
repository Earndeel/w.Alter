# Walter Ops

**Role.** One facade over the backup mechanisms (PostgreSQL dumps, encrypted offsite restic repository, monthly
restore tests), git publication and the guardians. It works without the other modules and without any model, and
owns no other module's code, contracts or migrations. (Formerly walter-backup; `walter-backup` remains an exact alias.)

**Use**
- `walter-ops backup status`: three separate answers — code compliance, health of each backup, last proven restore.
- Before a risky change: `walter-ops backup checkpoint --level git --scope <repo>` (code), `--level files --scope
  <module>`, `--level db --schema <schema>` (migration). It returns the rollback steps; it never restores by itself.
- `walter-ops git`: W.Alter repositories, uncommitted work and its age. `walter-ops check`: caches and old untracked
  work (alerts only, no automatic cleanup).
- Guardians (`walter-guardians`): per-module detection and authorised repairs; Telegram only when the owner is needed.
- Development board (`devboard`, tailnet page): projects, pending agreements, replaced decisions, agents' live work.
  Read-only; a wrong card is corrected with the MCP tool `devboard_correct`, only at {{owner.address}}'s request.

A real restore happens only with {{owner.address}}'s agreement. Planned, not built: clean install of a new W.Alter,
onboarding, full restore of an instance (`walter-ops install|onboard` answer "planned").
