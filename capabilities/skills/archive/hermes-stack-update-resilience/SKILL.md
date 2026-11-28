---
name: hermes-stack-update-resilience
category: devops
description: "Use when updating Hermes — keep custom plugins alive."
---

# Hermes Stack Update Resilience

Use when: updating Hermes Agent on a system that carries custom plugins
(walter-browse, walter-computer-use), locally-modified core files, and
user-authored skills — or when deciding whether a newly announced Hermes
feature (Browser Use mode, new tools) should replace or integrate with the
existing Walter stack.

## Core principle

Update Hermes regularly (fixes, security, unseen improvements), but never let
an update own the browsing/extraction path. walter_browse stays the canonical
facade; anything Hermes ships is evaluated as an OPTIONAL backend or
complement, never a substitution without user sign-off.

## Isolation pattern (verified to survive a 1095-commit update, 2026-08-11)

Custom plugins survive `hermes update` intact when they follow this contract:

1. **Subprocess boundary**: the plugin invokes an external CLI
   (`/root/.hermes/bin/universal-scraper`) via `subprocess` instead of
   importing its runtime into the Hermes interpreter.
2. **Stdlib-only glue**: the plugin's `__init__.py` imports only
   `subprocess`, `json`, `urllib`, `pathlib` — plus the ONE stable helper
   `hermes_constants.get_hermes_home` for path resolution. NO `agent/*`,
   `tools/*`, `cli/*`, `gateway/*` imports.
3. **External CLI is self-sufficient**: the CLI lives in its own venv
   (`/root/.venv/scrapling/...`) and only reads skill scripts under
   the Hermes skills directory — files an update never touches.

Keep this contract for any new backend (including a future browser-use
backend): subprocess boundary + stdlib-only glue.

## Pre-update checklist

```bash
hermes --version                          # current version
cd /root/.hermes/hermes-agent
git status --short                        # audit local modifications FIRST
git log -1 --oneline                      # current HEAD
# verify custom plugins listed under plugins.enabled in the live config
grep -A5 '^plugins:' <hermes_config_path> # path from: hermes config path
```

Backup: full `hermes backup -o file.zip` can HANG on large session stores;
`hermes backup --quick` may emit a state snapshot under
`~/.hermes/state-snapshots/` instead of a zip — acceptable.

Pitfall: NEVER `pkill -f "hermes backup"` in the same shell that then re-runs
the backup — the pkill matches the new command too (exit -15). Start the
backup, wait, then inspect.

## Post-update verification recipe

```bash
hermes --version
# 1. custom plugins still present in plugins.enabled (see pre-update grep)
# 2. direct import test of each custom plugin:
/root/.hermes/hermes-agent/venv/bin/python - <<'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location('wb','/root/.hermes/plugins/walter-browse/__init__.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('OK', m.WALTER_BROWSE_SCHEMA['name'])
EOF
# 3. smoke-test the external CLI:
/root/.hermes/bin/universal-scraper --url https://dummyjson.com/products/1 \
  --expected-fields '{"title":["title"]}' --required-field title --mode scrapling
```

Then: `echo n | hermes config migrate` (advances the config version despite
warnings; unknown-toolset warnings like `moa` are pre-existing noise).
Gateway may run as a plain process (`python -m hermes_cli.main gateway run`),
not systemd — check `ps aux | grep gateway` before assuming restart needed.

Note: `hermes plugins list` shows ONLY bundled plugins. Custom plugins
(walter-browse, walter-computer-use) never appear there — verify via the
config's plugins.enabled section and the import test above.

## Browser Use mode (browser_exec) — the 2026-08-11 decision

Hermes v0.20.0 ships Browser Use mode (`tools/browser_use_cli.py`): setting
`browser.backend: browser-use` swaps the ~12 browser tools for a single
`browser_exec` running Python inside the browser via browser-use CLI 3.0
(-48-66% tokens claimed, no accuracy drop — tweet 2086881660658663469).
Bundled plugin `browser-browser-use` exists but is NOT enabled by default.

DECISION: do NOT flip `browser.backend: browser-use` globally — it bypasses
the semantic extraction contract. If ever integrated, it becomes a **4th
backend inside the Walter router** (after scrapling → camoufox-max →
webtop-cdp): router generates an interaction script, executes it, feeds the
DOM to the SAME semantic scorer. Enablement alone is not integration — only
the router backend wrapper connects it to walter_browse. Full detail in
`references/browser-use-mode.md`.

## Pre-install verification of a patch-based upgrade bundle (read-only)

When an upgrade arrives as a **bundle of core patches + a plugin dir** (not a
`hermes update`), verify it read-only against a clean replay BEFORE installing
or flipping config. Do not let a "bundle validated upstream" claim substitute
for local evidence. The Lot 1.1 walter-computer-use bundle (2026-08-13) passed
this exact recipe — full transcript + command sequence in
`references/bundle-preinstall-audit.md`. Methodology:

1. **Reproducibility (tree identity, not git identity)**: `git am` the patches
   onto a FRESH clone pinned at the documented base commit; set a throwaway
   `git config user.email/name` first (a fresh clone has none and `git am`
   aborts on that). Then `git diff --quiet <replay-HEAD> <fresh-HEAD>` → empty
   = trees identical. Note: commit hashes differ between replays (committer
   identity changes); compare TREES, not SHAs.
2. **Run the documented gate commands exactly as written** — the README's
   `scripts/run_tests.sh <files...>` line and the plugin's pytest invocation —
   not just ad-hoc subsets. exit 0 is the go/no-go.
3. **Run the compatibility checker in an ISOLATED HERMES_HOME** (copy config +
   plugin dir into a temp home, `HERMES_HOME=... PYTHONPATH=$PWD`). Do NOT run
   it against the live profile.
4. **Prove "doesn't start a driver"** (fail-closed): confirm the checker prints
   `driver_started:false`, and check no NEW cua-driver process/socket appeared
   (`pgrep -af cua-driver` count unchanged, no new `/tmp/hc-*.sock`). Check the
   backend `__init__` doesn't spawn — `start()` is the only spawn point and
   must never be called by the checker.
5. **Prove fail-closed on bad config**: disable the plugin in the isolated
   config → checker must return `{"status":"incompatible"}` and exit 1.
6. **Rollback constructible**: base must be an ancestor of replay HEAD
   (`git merge-base --is-ancestor <base> HEAD`) → `git reset --hard <base>` or
   `git revert` works; active worktree stays clean (`git status --porcelain`
   empty) so nothing is mutated until the explicit install step.
7. **Keep plugin backups outside discovery**: never rename an old plugin to
   `~/.hermes/plugins/<name>.bak` while retaining its `plugin.yaml`. Hermes
   discovers directories by manifest and duplicate manifests with the same
   `name:` can shadow the new plugin while still appearing enabled. Archive
   displaced plugins under the sealed backup/release directory instead, then
   assert exactly one discoverable manifest for that plugin name.
8. **Treat systemd stop by PID, not only state label**: a user gateway may exit
   non-zero during an intentional SIGTERM and leave the unit `failed` even
   though `MainPID=0`. A transaction may proceed only when PID is zero and the
   state is `inactive|failed`; then call `systemctl --user reset-failed` before
   starting the replacement. Never proceed while a PID remains.
   For post-restart health checks, do **not** pipe `hermes gateway status` into
   `grep -q`: grep may close stdout after the first match and make the Hermes
   CLI raise `BrokenPipeError`, falsely failing an otherwise successful
   deployment. Query systemd directly with the correct user bus instead:
   `XDG_RUNTIME_DIR=/run/user/0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus systemctl --user is-active --quiet hermes-gateway.service`, then assert
   `systemctl --user show ... -p MainPID --value` is greater than zero.
9. **Clean up temp homes/clones**; confirm no leftover sockets.
10. Report gaps — e.g. README lacking an explicit rollback command, or no
   `HEAD == base` pin asserted before `git am` (both minor; `git am` already
   fails closed on mismatch).

Verdict stock: reproducibility + all gates + fail-closed no-driver + isolated
check + rollback-based-ancestor ⇒ **ship**, listing minimal pre-smoke actions.

## References
- `references/browser-use-mode.md` — Browser Use mode mechanics, verified
  facts on this system, router-backend integration shape, update-survival
  evidence.
- `references/bundle-preinstall-audit.md` — verified read-only audit recipe
  for a patch+plugin upgrade bundle (Lot 1.1), with exact commands and
  evidence checks (reproducibility, fail-closed, no-driver, rollback).