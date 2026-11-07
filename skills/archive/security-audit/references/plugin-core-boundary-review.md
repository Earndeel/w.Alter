# Plugin/Core Boundary Disentanglement Review (read-only)

Bounded second-opinion audit of a refactor that pulls a domain feature (e.g. a "Walter"
device-control backend) OUT of a core agent and INTO an external plugin. Goal: prove the
core stayed generic + fail-closed, no business logic leaked, and registration/unload/
rollback are safe. No long suites, no writes. Verdict exactly `SHIP` or `BLOCK`; if any
point is not provable by static reading, BLOCK.

## Scope discipline
- Inspect ONLY the designated paths: the clean-replay git tree (base + the lot's commits),
  the bundle's `plugin/` dir, README, FINAL_REPORT. State them up front.
- `git status --short` must be clean; `git log --oneline` must show exactly base + the
  declared commits. Record these as the replay's identity proof.
- Production core only: `git diff <base> HEAD -- <prod dirs>` **excluding tests**. Use
  `git diff --name-only` then `--stat` to list the prod fileset before reading it.

## Required verification points (with proof commands)

### 1. Plugin/Core boundary
- `git diff --name-only <base> HEAD` → split into prod-core vs tests vs plugin files.
  The plugin must live OUTSIDE the core tree (in the bundle, not the repo).

### 2. No business logic in core
- Forbidden-symbol scan of the **production-only diff**:
  `git diff <base> HEAD -- <prod dirs> | grep -inE 'walter|safari|youtube|open_url|verify_state|parse_...|execute_...'`
- Then scan the **whole working tree** (not just diff) to catch leaks and — critically —
  to classify non-diff hits as **pre-existing and unrelated** (e.g. `web_server.py` opening
  the dashboard URL, `youtube-transcript-api` in lazy_deps). A core grep hit that is in the
  diff is a leak; one that is pre-existing outside the diff is a false positive — say so.
- Business symbols must appear ONLY under `plugin/`, with a quoted symbol list.

### 3. Security: registration / unload / profile scope
- Registration registry must be **per-profile scoped**: check the scope key resolves to
  `hermes_home_key()` (not a global). Grep `scope_key = ...` in the plugin manager.
- Reserved names rejected (e.g. `cua`/`noop` cannot be shadowed) and duplicate registration
  detected — check the register helper for a reserved-set and an idempotency CAS.
- Unload must be **reverse-order, ownership-ledger, identity-conditional** (`unregister`
  only deletes when `bucket.get(name) is factory`), so a later generation is never removed
  accidentally. Check the dispose walk disposes in `reversed(order)`.

### 4. Terminal direct-reply contract (fail-closed, no second LLM unless certified)
- Direct reply (zero provider continuation) must be gated EXCLUSIVELY on a producer-certified
  flag chain: `safe_to_return is True` AND `terminal` AND a redaction-clean `user_message`
  AND no `error`. Verify the classifier re-filters the producer's claim (defense in depth).
- If not certified, the fallback must be a **text-only** continuation with **no tool schema**:
  `tools_for_api = [] if _terminal_tool_result is not None else agent.tools`. Verify no path
  lets tools reopen after terminal (grep for the empty-tools assignment in the loop).
- Any residual `setattr(...)` in the core diff must be on `self` (instance state, e.g.
  `_last_capture_geometry`), never on a core module/class (that would be monkey patching).

### 5. No monkey patch in plugin
- `grep -nE 'setattr\(|__setattr__|(agent|tools|hermes_cli)\.[A-Za-z_]+\.\s*=' <plugin>`
  The plugin should only import core symbols to SUBCLASS (backend) or read config, and call
  host-provided registration seams — never assign into core modules. `register()` should
  raise `RuntimeError` if a required seam is missing (fails closed on an old host).

### 6. Rollback / cutover fail-closed
- README/report must document: clean-worktree apply, staging plugin beside active,
  backup of source+plugin+config, atomic switch only after gates, rollback of all three
  together on any deviation, and a fail-closed upgrade rule (never patch dirty checkout).
- Prove the bundle patches are exactly present on the replay: for each patch run
  `git apply --check --reverse <patch>` in the clean tree → "REVERSE-CLEAN" means the patch
  is byte-applied (no drift between bundle and replay).

## Pitfalls
- `git diff --stat <base> HEAD` per-file counts are your size evidence (e.g. 935+/36− prod).
  Report core size separately from plugin size to show the plugin absorbed the bulk.
- Don't rerun the project's broad suite; the task is bounded static review. A separate
  "broad test run not yet final" note is a non-blocking note, not a BLOCK, for a code review.
- Non-blocking behavioral notes (e.g. the core diff tightens V1 capture/geometry guards
  that technically alter base behavior) belong in "notes non bloquantes", not findings.
- Cite exact `file:line`/symbols for every claim; a claim without a citation is unprovable
  → BLOCK per the fail-closed rule.

## Report shape
Lead with `## Verdict : SHIP|BLOCK`, then per-verification-point proof (each citing paths/
symbols), then "Notes non bloquantes", then "Fichiers créés/modifiés: Aucun" and
"Problèmes rencontrés: Aucun".
