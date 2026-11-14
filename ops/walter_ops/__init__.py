"""walter/ops: install, deploy, version, keep and restore Walter and its instances (owner decision, 2026-10-29).

Sub-components: installer (clean-install, onboarding, personal-restore: designed, not built yet), deploy (wraps the
core platform's `walter release|install|export`), git and backup (the `walter_backup` package, unchanged: *backup* is
the right name for that part), recovery (the restore drill and the monthly restore test), guardian (`check`).
Ops coordinates the other modules through their public interfaces only; it owns none of their code or migrations.
Standard library and system python3, like walter_backup: it must work when everything else is down.
"""
