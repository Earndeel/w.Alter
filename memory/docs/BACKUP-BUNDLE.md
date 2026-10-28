# Configuration payload and compatibility links

`walter-backup run offsite` archives module sources, integration configuration and
declared service dependencies, then encrypts and uploads the payload. PG and the
main Hermes SQLite snapshot remain separate payloads. The public command requests
an asynchronous systemd run: confirm that invocation's completion and its new
remote objects before declaring success.

After the Core, Memory and Vault moves on 2026-10-28 UTC, their `/opt/walter-*`
paths are compatibility symlinks. A service can still require
`/opt/walter-memory/.env`, while the archive stores its single physical copy at
`/walter/memory/.env`. Checking only exact tar member names incorrectly rejected
that complete payload. The first final offsite invocation failed closed at this
check after uploading PG; it did not establish a new configuration backup.

Creation and verification now prove every required path by resolving the links
and targets recorded in the archive. They retain the required logical path and
the symlink, rather than dropping the requirement or duplicating credential
files. Absolute targets are rooted in the archived layout; relative targets are
relative to the link's parent. Missing targets, cycles, root escapes and paths
through a regular file are rejected. Verification never follows host symlinks.
The manifest format and old payloads remain supported; no database migration or
credential change is required. Restoring the actual link and canonical target
preserves existing service references.

`tests/test_backup_compat_paths.py` uses real temporary files and tar payloads for
all three moved modules. It restores the configuration with the real isolated
restore function and rejects altered manifests/links without contacting PG,
Drive or any service. The produced final archive must also pass verification,
with modes and required alias targets checked using metadata, never secret values.
