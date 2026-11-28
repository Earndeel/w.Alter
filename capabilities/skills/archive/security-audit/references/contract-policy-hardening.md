# Contract + Authorization-Policy Hardening — Verification Checklist (behavioral tests)

How to re-audit/harden a JSON request `contract.py` + capability `policy.py` the way the
W.Alter Device Node task expects. This is a *verify-and-pin* workflow: the code is often
already hardened — write behavioral tests that pin each property, don't assume you must
change source. The deliverable is a proven contract, not a diff.

Use when: "re-audit and harden the contracts/policy", "verify bounded untrusted
request fields", "fail-closed authorization". Extends the Auth & Authorization phase of
the parent security-audit skill.

## Workflow
1. **Baseline first.** Run the existing target tests (`PYTHONPATH=src python3 -m pytest tests/test_X.py tests/test_Y.py -q`) and `ruff check` BEFORE touching anything, so you know a failing suite is yours vs pre-existing.
2. **Add behavioral tests, never source-shape tests.** Assert on raised exception types/messages/codes and on *observable behavior* (e.g. two key orders producing the same digest), not on internal fields or line counts.
3. **Run targeted pytest + ruff on only the files in scope.** Confirm everything you wrote passes and lint is clean before the full run.
4. **Full suite: triage unrelated failures.** If the full run fails in files you didn't touch, verify the cause (e.g. missing `pytest-asyncio` plugin → all async tests error at collection). Report those as pre-existing/environmental, not as your regression. Don't "fix" out-of-scope files.
5. **No source change needed is a valid outcome.** If the code already satisfies every property, say so plainly — pinning it with tests is the hardening contribution.

## Input-contract properties to verify (each needs a behavioral test)
- **Unknown-field rejection** at the top level (extra key → error listing it).
- **Required/blank field rejection**: empty or whitespace-only required strings, missing identity/required text.
- **Field length bounds** (e.g. request_id 256, intent 2048) and **control-char rejection** in bounded strings.
- **Schema-version pinning**: wrong `schema_version` → `unsupported schema_version`.
- **JSON depth bound** (deep nesting rejected).
- **JSON size bound** by *canonical byte budget* — to trigger, use many mid-size strings (each under the per-string cap) whose total exceeds the budget; a single oversized string trips the string cap first, not the byte cap.
- **Node-count bound** (broad-but-shallow trees, e.g. N sub-arrays of M items, that pass per-array caps but blow the total node budget).
- **Per-array / per-object item caps** (array with too many items, object with too many fields).
- **Value canonicality**: non-finite floats (`nan`/`inf`) and out-of-int64-range ints rejected.
- **Nested `expected`-predicate validation** (non-object elements, too-many predicates).
- **Canonical arguments digest**: stable across key reordering (shallow AND nested) and across unicode; differs for different arguments. Reviewers use this for idempotency/dedup — a non-canonical digest is a correctness+security bug.

## Authorization-policy properties to verify (fail-closed)
- **Risk-class ordering matters**: assert the *highest-precedence* refusal wins. e.g. a HIGH capability refused on a platform it isn't live on must report `high_risk_disabled`, NOT `platform_not_live` — that is the fail-closed precedence (PROHIBITED > HIGH > live-check > broker-grant).
- **Prohibited refused even with a broker grant/approval.**
- **HIGH refused even with a broker grant.**
- **Live-vs-contract split**: a capability supported on a platform only via `contract_support` must still fail closed via `platform_not_live` unless it's in `live_support`. Contract support ≠ live authorization.
- **Broker-grant gates**: elevated capabilities require an explicit boolean grant; a non-bool grant state is rejected (`invalid_grant_state`).
- **Unknown capability → denied** (allow-list, fail closed).
- **Missing/blank platform → denied** (`platform_required`).
- **Platform normalization**: case-insensitive matching (`"MACOS"` == `"macos"`).
- **`all` live-support** authorizes any platform without a grant.
- **Duplicate spec names rejected** at construction (`ValueError`), even when risk/mutation are identical.
- **`list()`/enumeration is sorted and deduped.**

## Environment gotchas seen in practice
- Repo may require `PYTHONPATH=src` for imports to resolve.
- `ruff` may not be on PATH — install into a scratch venv (`python3 -m venv /tmp/venv-ruff && .../pip install ruff==<pinned>`).
- `pytest-asyncio` missing → async test modules error at collection ("Unknown pytest.mark.asyncio"), which can pollute the full-suite summary with failures in out-of-scope files. The fix is an install/dependency issue, not your code — report as environmental.
