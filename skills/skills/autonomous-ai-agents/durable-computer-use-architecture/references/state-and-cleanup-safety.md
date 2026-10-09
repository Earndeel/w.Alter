# State and Cleanup Safety

This reference governs cleanup around Hermes stateful installations and mixed
checkouts. It is intentionally stricter than ordinary cache cleanup because
`state.db` contains durable session and tool-call history.

## Decision sequence

1. **Run tests before cleanup.** Use `scripts/run_tests.sh`; record the real
   result before deleting anything.
2. **Resolve the active home.** Use `get_hermes_home()` in Python or
   `hermes config path`. Do not infer the active database from the current
   working directory, a Git status entry, or a filename search.
3. **Classify the candidate.** For `state.db`, inspect only path, owner,
   permissions, and size. Confirm whether the running code resolves that exact
   path. Never open, copy, hash, truncate, or delete a state database merely
   because it is empty, untracked, or located inside a repository.
4. **Preserve mixed-checkout work.** If `git status --short` shows unrelated
   changes or untracked files, do not run broad repository cleanup, hard reset,
   or a global stash. Cleanup scope must name exact generated artifacts.
5. **Remove only disposable generated files.** Examples are bytecode caches
   created by the current verification (`__pycache__`) and explicitly known
   test-runner caches. Do not include session databases, auth files, config,
   logs, or user-created research/code files in a generic cleanup glob.
6. **Verify without recreating caches.** Run the post-update checker with
   `PYTHONDONTWRITEBYTECODE=1`, then confirm the exact disposable paths are
   absent and the active Hermes state path remains present.
7. **Report the boundary.** State what was removed, what was deliberately left,
   and whether live AX/TCC validation was performed. “Plugin healthy” is not
   evidence that a remote Mac desktop accepted a real action.

## Safe verification shape

```bash
# Read-only metadata; do not read the databases.
python3 -c 'from hermes_constants import get_hermes_home; print(get_hermes_home())'
python3 -c 'from pathlib import Path; import stat; p=Path("..."); print(p.exists(), stat.filemode(p.stat().st_mode) if p.exists() else None, p.stat().st_size if p.exists() else None)'

# Tests before cleanup.
scripts/run_tests.sh tests/tools/test_computer_use_*.py

# Remove only exact, user-authorized generated-cache paths with a narrowly
# scoped cleanup operation. Never include the active state database path.

# Post-clean verification without bytecode writes.
PYTHONDONTWRITEBYTECODE=1 python3 ~/.hermes/scripts/check-walter-computer-use.py
```

Replace the example paths only after resolving them from the active profile and
confirming they are generated caches. Never substitute the active
`get_hermes_home()/state.db` path into the cleanup operation.

## Recovery rule

If a state file was touched accidentally, stop immediately, do not restart
services or run migrations, and verify the active database path and backup
state before taking any further action. A repo-local placeholder and the live
profile database are different objects only when the active-home resolution
and code path have been explicitly confirmed.
