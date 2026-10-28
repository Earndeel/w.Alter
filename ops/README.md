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

## Repository hygiene

`walter-backup git` inventories tracked changes and non-ignored untracked files separately. Git NUL records preserve
filenames containing spaces, newlines and rename destinations. The inventory reads status, names and filesystem
timestamps; it exposes no file contents, diffs, environment values or remote URLs.

The existing `check` watchdog now raises G0 `warning` incidents for:

* recognisable generated caches already tracked by Git, even in a clean working tree;
* untracked working files whose oldest visible modification exceeds `git.untracked_warn_hours` (48 hours by default);
* a failed Git status/file inventory, which cannot establish cleanliness.

The existing information incident for tracked edits uses their own age. An old untracked file no longer makes a
fresh tracked edit look old. Ages are **estimates from file mtime**, not proof of when work began: touching a file
resets this indicator, and a deleted file has no mtime to inspect. Git has no history of uncommitted edits.
The watchdog only reports; it never deletes, stages, commits, stashes or moves a working file.

`git.generated_patterns` lists narrow cache patterns (`.pyc`/`.pyo`, `__pycache__`, common Python test/type/lint
caches and `.DS_Store`). It does not guess whether a generated asset or source file should be committed. The module
`.gitignore` prevents its own interpreter/test caches from being added accidentally; **ignore rules do not untrack
an existing indexed file**, which needs a reviewed versioned removal.

`git.preserved_paths` keeps intentional evidence out of hygiene warnings. Defaults cover `archive/**`,
`archives/**`, `reports/**`, `outputs/**` and `docs/reports/**`, relative to each repository. Those files remain
visible in untracked totals and a separate preserved count; they are neither deleted nor automatically ignored.
Override the list for other intentional evidence roots. The full counts are retained while filename evidence is
limited to 50 entries per category. Checkpoints based on Git still omit untracked files, including preserved
reports: use the appropriate file backup or version the intended deliverable to protect it.

Declared compatibility links, historical reports and deliberate migration bridges are not generated residue.
Their retirement needs evidence that no consumer depends on them and the recorded migration decision; a path
looking old is not permission to remove it. This watchdog neither infers nor removes obsolete compatibility.

Behavioural regressions use temporary Git repositories and synthetic files:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. walter-python -m pytest -q -p no:cacheprovider tests
```

See `docs/CORRECTIONS-2026-10-29.md` for the tracked-bytecode cleanup and RED/GREEN evidence.
