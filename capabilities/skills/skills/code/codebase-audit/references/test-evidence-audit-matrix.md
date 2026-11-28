# Test-Evidence Audit Matrix

Use when the ask is "audit tests and evidence for <stack>: which flows are covered, which are not, cite exact file:line." Read-only. Deliverable is a matrix, not a code change.

## Method

1. **Inventory every test case with line numbers in one pass:** search each test dir for `^\s*(async\s+)?def test_|^class Test` (content mode) — gives filename + start-line per case without reading files whole. Count functions and parametrized cases by running the suite.
2. **Run the canonical suites live** (repo venv; plugin test under the host app's venv; host's own related tests). Record counts/skips/exit. Check `.git` + CI presence: green with neither is an unpinned manual snapshot — say so.
3. **Map flows → tests, keep a "NOT proven" column.** Group test functions by the flow they prove; for reachable source paths never exercised, list them as NOT proven with `source.py:line`.
4. **Prove negatives by grep.** For any claim ("capture-integrity marking is tested"), grep the test file for the specific function names / field names (`_mark_capture_integrity`, `capture_valid`, ...). Zero hits = untested; state it.
5. **Skepticism passes (high-value checks):**
   - **"E2E" label vs automation:** grep for pytest markers `e2e|live|smoke`, then grep for real transport (`socket.connect|asyncio.open_connection|subprocess.*ssh|create_connection`). Zero hits ⇒ "E2E"/"smoke-tested" is a manual run, not automation. Cross-check every "Delivered"/"Implemented" doc row against what a test actually spawns.
   - **Extension/plugin seams:** these are often proven as two *separate* unit tests (host registry test + plugin `register()` test) with no discovery→factory integration test. Check explicitly whether the seam is closed (`discover_plugins(force=True) → get_backend_factory(name)`); usually it is not.
   - **Documented invariants enforced at the wrong layer:** e.g. "privileged broker must not run from a user-writable checkout" may only be enforced by subprocess-executor ownership checks, not daemon startup. Grep the daemon validation path for the check before crediting the claim; name the layer + test that actually enforces it.
   - **Host baseline ≠ plugin behavior:** host tests passing do not cover the plugin's own marking/wiring code.
6. **Deliver:** current-run-status block (what ran green today), Flow × Proven(file:line) × NOT-proven matrix, and a claim-vs-reality table (skill/README/roadmap "Delivered" rows vs what tests prove).

## Worked example — Walter Computer Use stack (snapshot 2026-08-12, Linux, run as root)

Scope: `/root/walter-computer-use` (repo), `/root/.hermes/plugins/walter-computer-use` (plugin), `/root/.hermes/hermes-agent/tests/tools/test_computer_use*.py` (host).

- **Status:** repo 335 passed + ruff clean; host computer_use suite 179 passed; plugin 13 passed. No `.git`, no CI — green is a manual snapshot.
- **Strongly proven (unit/contract):** grants (`tests/test_approvals.py`), idempotency (`tests/test_store.py:61-117`, node `test_node.py:156,244,272`), HMAC audit chain/tamper (`test_audit.py:178-209,253-312`), executor allowlist/ownership (`test_executor.py`), node/broker fail-closed policy (`test_node.py`, `test_broker.py:135-459`), plugin safe-window `select()` (`test_walter_computer_use.py:23-106`) and bounded recovery loop (`:157-283`).
- **NOT proven (verified gaps):**
  - Plugin `_mark_capture_integrity` (`plugin/__init__.py:272-298`) — zero tests (grepped).
  - safe-window→capture wiring (`__init__.py:342-366` `list_windows→select→exact capture`) — `select()` unit-tested alone; capture() only exercised on the exact-target branch.
  - No test spawns real SSH or connects to a remote (0 grep hits) — ssh argv asserted only; transport tests use a local fake MCP server (`tests/helpers/fake_mcp_server.py`).
  - Broker user-writable-checkout invariant not auto-tested at daemon level (`cli.py:240-253` validates socket + peer UIDs only); executor-level ownership tests don't close it.
  - No automated physical-Mac E2E — every "E2E"/"smoke-tested" row (README:14, operations.md:32-57, roadmap:14) is manual; live macOS validation still on the plan (docs/plans/2026-08-06:67-75).
  - Plugin discovery→factory seam never integration-tested; `capture_strategy` config key and unknown-strategy RuntimeError untested.
