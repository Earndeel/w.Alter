# Pre-install read-only audit of a patch+plugin upgrade bundle (Lot 1.1, verified 2026-08-13)

Verified against `/tmp/hermes-lot11-bundle` (3 core patches + `plugin/`) and
`/tmp/hermes-lot11-clean-replay` (worktree = base + applied patches). Read-only:
nothing in sources or bundle was modified; all artifacts were temp copies under
`/tmp/wal11-*`, removed at the end.

## Shape of the bundle
- `core-patches/0001-0003-*.patch` — generic agent/computer-use seams (git-format, `git am`-able).
- `plugin/` — `__init__.py`, `plugin.yaml`, `check_compatibility.py`, `test_walter_computer_use.py`.
- `README.md` — documents the upgrade replay (fail-closed) + post-install smoke.

## 1. Reproducibility — tree identity, not commit identity
```bash
# fresh clone pinned at the DOCUMENTED base
git clone -q <clean-replay> /tmp/wal-amcheck2 && cd /tmp/wal-amcheck2
git config user.email "audit@local" && git config user.name "Audit"  # REQUIRED, fresh clone has none
git reset -q --hard 89a84e1ae6           # the base commit from README
git am /tmp/hermes-lot11-bundle/core-patches/*.patch
git diff --quiet <REPLAY-HEAD> HEAD && echo "TREES IDENTICAL"
```
Pitfall: commit SHAs differ between replays (committer identity changes). Compare
`git diff` trees, never `git rev-parse` equality.
`git apply --check --reverse <patch>` on the replay = confirmed patches are in the applied state.

## 2. Run documented gate commands verbatim
```bash
HERMES_PYTHON="$(command -v python3)" scripts/run_tests.sh \
  tests/tools/test_computer_use.py tests/tools/test_computer_use_*.py \
  tests/computer_use/test_cua_spawn_env_sanitization.py \
  tests/agent/test_terminal_tool_result_contract.py \
  tests/run_agent/test_terminal_result_enforcement.py \
  tests/hermes_cli/test_plugins.py tests/hermes_cli/test_plugin_ownership_ledger.py \
  tests/hermes_cli/test_plugin_prompt_sections.py tests/agent/test_plugin_prompt_sections.py -q
PYTHONPATH="$PWD" python3 -m pytest <plugin>/test_walter_computer_use.py -q
```
Both passed (core suite ~3 min; plugin 17 passed).

## 3. Isolated compatibility check (do NOT use the live profile)
```bash
ISO=/tmp/wal11-audit-iso; rm -rf "$ISO"; mkdir -p "$ISO/plugins"; cp -r <plugin> "$ISO/plugins/walter-computer-use"
cat > "$ISO/config.yaml" <<'EOF'
plugins:
  enabled: [walter-computer-use]
computer_use:
  backend: walter
EOF
HERMES_HOME="$ISO" PYTHONPATH="$PWD" timeout 60 python3 "$ISO/plugins/walter-computer-use/check_compatibility.py"
# expect exit 0 + {"status":"ok","backend_class":"WalterCuaBackend","driver_started":false, ...}
```

## 4. Prove "no driver started" (fail-closed)
- Count `pgrep -af cua-driver` BEFORE and AFTER the check — must be unchanged.
- `ls /tmp/hc-*.sock | wc -l` — must not grow (0 new).
- Inspect `CuaDriverBackend.__init__`: it must NOT spawn; only `start()` spawns,
  and the checker must never call it (it calls `stop()` in `finally`).

## 5. Prove fail-closed on bad config
```bash
# set plugins.enabled: []  in the isolated config, re-run checker
# expect {"status":"incompatible", "error":"...not enabled in config..."} and exit 1
```

## 6. Rollback constructible
- `git merge-base --is-ancestor <BASE> HEAD` → base is ancestor ⇒ `git reset --hard <BASE>` or `git revert`.
- `git status --porcelain` empty before/after → active worktree never mutated pre-install.
- Rollback recipe for the operator: `git reset --hard <BASE>` + delete
  `plugins/walter-computer-use` + remove plugin + backend keys from config.

## Gaps found (minor, non-blocking)
1. README documented no explicit rollback command (mechanism is sound; operator must deduce it).
2. No automatic `HEAD == <base>` pin asserted before `git am` (git am still fails closed on mismatch).

## Verdict
SHIP with 2 minimal pre-smoke actions: document rollback + assert base pin, then the
strict natural Safari+YouTube smoke (exactly one `computer_use(action="goal")`, one
provider request, no second request, certified direct-terminal response).
