# HMAC Audit Chain Hardening (implementation + adversarial TDD)

Class: hardening a tamper-evident, HMAC-SHA256-linked audit/event log persisted
in SQLite. Applies to any "append-only hash chain" (audit trails, event
ledgers, lifecycle logs). Approach is fail-closed + strict TDD: write the
behavioral tests first (red), implement, green, `ruff`.

## The chain it protects

Each entry hash is HMAC over the *serialized* prior state:

```
entry_hash = HMAC-SHA256(key, f"{prev_hash}|{operation_id}|{timestamp}|{payload_json}")
genesis prev_hash = "0" * 64     # "nothing came before"
```

With the key correctly held (32 random bytes, persisted 0o600), no one can
forge a row or splice the chain without the key. `verify()` walks rows in
`rowid` order, checks each `prev_hash == prior entry_hash` (chain link) and
each recomputed hash via `hmac.compare_digest` (constant-time). Key insight:
**verify must recompute over the stored payload JSON verbatim, not over a
re-parsed object** — the stored string is the canonical form, so tampering any
field breaks the digest deterministically.

## Hardening checklist (each item = a behavioral test)

1. **Canonical JSON before hashing.** `json.dumps(payload, sort_keys=True,
   ensure_ascii=True)` with a FIXED separator tuple (`(",", ":")`), so the same
   logical payload always hashes identically and whitespace games can't alias
   values. `_canonical_json()` computes size from the serialized bytes.

2. **Reject non-finite floats — explicitly.** `json.dumps` by default emits
   `NaN` / `Infinity` (invalid JSON) instead of erroring. Pass `allow_nan=False`
   AND walk the payload checking `math.isfinite(x)` so a NaN smuggled inside a
   dict/list raises `ValueError` with a clean message, not malformed output.

3. **Reject non-canonical payload structure.** Non-string dict keys and
   unsupported types (`set`, objects) must raise — `json.dumps` would otherwise
   coerce integer keys to strings, silently canonicalizing attacker-chosen keys.
   Check `isinstance(key, str)` per key; raise on any other type.

4. **BOUND THE PAYLOAD, before AND after redaction.** This is the non-obvious
   one. Redaction changes size in BOTH directions: a long secret shrinks to
   `[REDACTED]` (11 chars), but a payload full of tiny secrets stays small
   *before* redaction (each `"sk"`) and explodes *after* (each becomes the full
   `[REDACTED]` token). Enforce `max_size` / `max_depth` / `max_nodes` on the
   raw payload, then AGAIN on the redacted payload, so inlining secrets can't
   bypass the cap. Make the three bounds constructor params with sane defaults
   (e.g. 256KB / depth 32 / 10K nodes) so tests can shrink them.

5. **Define depth/node metrics precisely.** Node count = the root *plus every*
   dict/list/scalar value (top-level dict is 1 node; `{"a":1,"b":2}` is 3).
   Depth = max container nesting, top-level dict = depth 1
   (`{"a":{"b":[1,2,3]}}` → depth 3). Count during a recursive walk; the depth
   bound also prevents unbounded recursion on crafted deep payloads.

6. **Validate operation IDs — reject the field delimiter.** In the HMAC message,
   `|` is the field separator. An operation_id containing `|` lets an attacker
   blur the boundary between operation_id / timestamp / payload fields in the
   signed string. Reject `|`, control chars (`<0x20`, `0x7F`), empty, and
   over-length ids. Same reasoning applies to any user-supplied string that goes
   into a `delimiter.join(...)` before signing.

7. **File safety on key AND DB.** Key and sqlite DB both:
   - created with mode `0o600` (chmod after connect too),
   - refuse symlinks — check `path.is_symlink()` and open with `O_NOFOLLOW`
     (protects the classic symlink-swap / write-through attack),
   - **refuse hardlinks — `stat(follow_symlinks=False).st_nlink > 1` raises.**
     A second hardlink to the key inode is invisible to `is_symlink()` but lets
     an attacker mutate the key/DB through an alias; the nlink check closes it.
   - Re-check nlink AFTER `sqlite3.connect` (the DB file is created there) —
     one check before connect misses a DB created by the open.

## Redaction (preserve, don't regress)

- Recursive: recurse into nested dicts AND lists; match sensitive keys
  case-insensitively (`token`, `password`, `secret`, `api_key`,
  `authorization`, `cookie`, `clipboard`, `text`).
- Return a NEW object; never mutate the caller's input.
- Guard against cyclic structures (a dict containing itself) so recursion
  doesn't blow the stack — `id()`-based cycle detection raising `ValueError`.
- Redact BEFORE hashing and storage so secrets never hit the ledger.

## Adversarial tests to include

- Row payload tamper → `verify()` returns `ok=False`, entry listed.
- Chain-link break (prev_hash overwritten) → detected.
- Wrong key reopen → `verify()` fails (entries signed under key A illegible
  under key B). Add a `wrong-key-fails-verification` test.
- NaN / ±Inf / negative-Inf payloads → raise.
- Non-string key, unsupported type (set) → raise.
- Over-size / over-depth / over-node payloads → raise (with small custom bounds).
- **Redaction-enlargement**: payload under size-cap before redaction, over after
  → raise. Prove it by asserting `payload_metrics(raw)[0] < payload_metrics(redacted)[0]`.
- Empty / pipe / control-char / over-long operation_id → raise.
- Symlink key, symlink DB, hardlink key, hardlink DB → all raise.
- DB file created 0o600.

## TDD mechanics notes

- Confirm red first by running the suite and seeing a *collection* error (bare
  `ImportError` for the not-yet-existing functions) — that's your red, before
  writing any implementation.
- If `pyproject.toml` sets core `addopts = "-q"`, a `-v` flag is overridden and
  verbose PASSED/NODE lines won't render; read the summary line instead
  ("N passed in …"). Count via the pytest collection line.
- Run `ruff check` on both `src` and `tests` — watch for an unused-import flag
  on a module you `import`ed for a helper you never called.