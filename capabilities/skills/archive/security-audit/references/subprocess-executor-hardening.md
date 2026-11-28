# Hardening a Python subprocess executor / command dispatcher (implementation pass, TDD)

Use when a codebase has a `subprocess` executor that validates an allow-list of
executable paths and then dispatches them — to make it resist executable TOCTOU,
symlink/rename races, PATH/base-env poisoning, and unsafe privilege behavior.
Same class as `contract-policy-hardening.md`: this is an **implementation pass
with behavioral tests** (fail-closed), not a read-only audit.

## Threat model (what the guard must refuse)

The dispatcher does `if path in allowlist: run([path, ...])`. Between the
allow-list check and the kernel's open of the path, a race or local actor could
substitute something else at that path: a symlink to an unexpected target, a
different file/inode via rename, a non-regular object (FIFO whose open blocks, a
directory), a file carrying privilege bits, or non-executable content — and could
poison PATH or loader/language env vars so a descendant resolves attacker code.

## Known-good hardening pattern (POSIX, macOS + Linux)

1. **Pin identity with `os.open(path, O_RDONLY|O_NOFOLLOW|O_NONBLOCK)` + `fstat`.**
   `O_NOFOLLOW` atomically refuses a symlink on the final component; `O_NONBLOCK`
   stops a swapped-in FIFO from blocking the open. Record `(st_dev, st_ino,
   S_IFMT(st_mode))` as the pinned identity.
2. **Refuse at open time** (fail closed, each with a distinct message for tests):
   - not a regular file (`not S_ISREG`)
   - executable carries privilege-escalation mode bits (the set-owner/set-group
     execute bits) → denied
   - no execute bit (`mode & 0o111` → 0)
   - open failed with `errno in (ELOOP, ENXIO, EMLINK)` → symlink denial
3. **Re-check identity immediately before dispatch**: `os.stat(path)` again,
   compare `(dev, ino, S_IFMT)` to the pinned value; mismatch → deny. Put this in
   a small method (e.g. `_identity_now(path)`) that returns the identity — it
   becomes a **test seam** for simulating the race.
4. **Refuse a world-writable parent dir** (`parent.stat().st_mode & 0o002`) — that
   is the rename-race vector. Don't walk ancestors rejecting symlinks: on Ubuntu
   `/bin` is a symlink to `/usr/bin`, so that would break `/bin/*` allow-lists.
5. **Never inherit PATH.** Leave `PATH` out of the base-env allow-list and always
   force a safe default (`/usr/bin:/bin:/usr/sbin:/sbin`). Strip loader/language
   env injection by **whitelisting** env keys (never blacklist). Dispatch by
   **absolute path with `shell=False`** so PATH can never resolve the top-level
   binary.
6. **Keep** bounded output, bounded timeout, NUL-byte rejection, and a plan-level
   env-key allow-list (e.g. a telemetry flag only).
7. **Portability note:** don't reach for the Linux-only fd-re-exec trick
   (`/proc/self/fd/…`) — it breaks macOS. The sub-microsecond residual window
   between the final re-check and Python's own open is irreducible in pure
   Python; the pin + re-check turns every practical swap into a hard denial.
   Document this honestly rather than claiming absolute atomicity.

## TDD loop (write failing tests first)

Adversarial behavioral tests (all deterministic, all exercise the real code):
- symlink at allow-listed path → denied
- allow-listed path replaced by a FIFO → denied, and no hang
- privilege bit set on a copied binary → denied
- non-executable file → denied
- file inside a `0o777` parent dir → denied
- **swap at the re-check moment**: `monkeypatch.setattr(executor, "_identity_now",
  plain_func)` where `plain_func(path)` unlinks the file, writes a new different
  inode, and returns the new identity → must deny
- poisoned `base_env={"PATH": "/tmp/evil", "LD_PRELOAD": ...}` must not reach the
  child: allow-list `/usr/bin/env` and assert `/tmp/evil` is absent from stdout
- a real allow-listed binary still runs (`returncode == 0`)

Gotchas hit writing these tests:
- **Monkeypatching a bound method**: the patch target is instance-bound, so the
  replacement must be a plain `(path) -> identity` function — NOT `(self, path)`.
  Writing `(self, path)` raises `TypeError: missing 1 required positional arg`
  the moment the executor calls it.
- Copy a real binary (`shutil.copy2("/usr/bin/true", target); chmod 0o755`) for
  allow-listed runs; `/usr/bin/env` is ideal for env-leak assertions.
- ruff bandit rules fire on adversarial fixtures: permissive `os.chmod` masks →
  `S103`, and `"/tmp/evil"` literals → `S108`. These are the *intended* attack
  surfaces: suppress file-wide with `# ruff: noqa: S103, S108` + a comment; don't
  mutate the test's intent.

## Triaging "suite regressions" that aren't yours

- A module that fails **collection** (`ImportError: cannot import name …`) aborts
  the whole run with `Interrupted: 1 error during collection`. Isolate with
  `pytest tests/ --ignore=tests/<broken>.py` and confirm the broken import lives
  in a file you never touched (pre-existing).
- Async test modules fail with `async def functions are not natively supported`
  when `pytest-asyncio` isn't installed in the ad-hoc venv — install the
  project's declared dev dependency; that is an environment gap, not a code
  regression.
- Establish the baseline (`pytest` green) *before* editing; then a red phase that
  lists exactly your new failing tests; then green after the fix.
