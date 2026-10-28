# walter-backup

Façade over Walter's existing backup, restore and versioning mechanisms (P5, 2026-10-28). It wraps what exists —
the PG, state.db and offsite units, the monthly offsite restore test, the isolated restore drill, git — without moving
them; implementations move only after qualification, with compatibility links (owner decision, 2026-10-28).

It must keep working when Router, Context, Memory (partly), Hermes, DSH or every model provider is down: system
`python3`, standard library, systemd, git, docker and files only. No model anywhere.

| Command | What |
|---|---|
| `walter-backup status` | three separate answers: **conformity** (contracts), **backup_health** (each kind's newest output and last run), **restorability** (last proven restore, drill possible now) |
| `walter-backup check` | the module's watchdog (G0): Incident v1 list, read by the guardian supervisor |
| `walter-backup run <kind>` | start an existing mechanism (`pg`, `statedb`, `offsite`, `restore_test`, `restore_drill`) |
| `walter-backup verify [--sample N]` | cheap proofs on the newest local copies (`pg_restore --list`, `zstd -t`) + N Raw Vault objects re-downloaded and sha256-checked through Walter Memory (optional: `unknown` when Memory is down) |
| `walter-backup git` | Git Manager: every Walter repository, uncommitted work and its age, remotes, checkpoints |
| `walter-backup checkpoint --level git|files|db` | protect a state before a risky change, adapted to the risk: a git ref on the exact working state (HEAD and index untouched; it reaches the Drive with the daily config bundle), an archive of a module, or a dump of named schemas — those two are age-encrypted with the recovery public key and copied to the remote at once |
| `walter-backup status` → `offsite` | what is **really off the VM**: newest file of each kind on the remote (`gdrive:` via rclone), and whether a copy of the private recovery key exists in the owner's vault (by item name, metadata only) — without it the Drive backups are unreadable once the VM is gone |
| `walter-backup checkpoints` | recorded checkpoints and how to restore each — restores are never run by the tool |

Configuration: `config/backup.toml` (neutral defaults), instance overrides in `@instance/config/backup/backup.toml`
(which units, where their outputs land, freshness limits). State: `@instance/state/backup/` (checkpoints.jsonl).
Maintenance: `contracts/maintenance.json` (guardian convention, read by `walter-guardians`).
