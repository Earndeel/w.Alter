# Test Gap Analysis via Invariant Mapping (Guard/Branch Coverage)

When auditing a codebase for test coverage gaps, the most valuable methodology is
**invariant mapping**: read every existing test, extract the invariant it proves,
then cross-reference against every conditional branch (guard, early return, error path)
in the source. Prioritize gaps by business impact, not mechanical coverage percentage.

Use this for: business logic functions (submitX, handleY, resumeZ) with guard chains,
error branches, or multi-step state transitions.

Do not use for: multi-provider dispatch routing (use `test-gap-analysis-routing-paths.md`
instead), or pure data transformation/payload-building functions where the decision tree
is flat.

## Methodology

### Step 1: Read every existing test in the target file
Don't skim. Read each test case completely (name, setup, mocks, assertions). For each:
- **What invariant does it prove?** Be specific: "HMAC auth rejects Bearer tokens"
  not "webhook auth works".
- **What source code lines does it exercise?** Map test assertions back to line
  ranges in the implementation.
- **What does it NOT cover?** Note which conditional branches the test's mock
  setup explicitly avoids.

### Step 2: Read the source function(s) completely
Identify every conditional path:
- Guard clauses (early returns with error states)
- `if/else` branches
- `try/catch` paths (success vs error)
- State-dependent paths (e.g., `if (workflowRunId)`, `if (botToken && chatId)`)
- Loop or retry logic

For each branch, classify:
- **Covered:** at least one test exercises this path
- **Uncovered:** no test's mock setup reaches this branch
- **Partially covered:** the branch is reached but the assertion doesn't verify
  the specific behavior unique to that branch

### Step 3: Build the coverage matrix
Create a table:

| Source lines | Guard/Invariant | Covered? | Existing test |
|---|---|---|---|
| L2720-2727 | media_worker_not_configured | ❌ | — |
| L2749-2756 | render_video_requires_https_inputs | ❌ | — |
| L2758-2771 | media_worker_retry_limit_reached | ❌ | — |
| L2792-2799 | media_job_tracking_failed | ❌ | — |

### Step 4: Prioritize gaps by business impact
Not all untested branches are equal. Rank by:
- **P0 (RED test needed now):** A regression here silently corrupts state, costs
  money (infinite loops, double charges), or violates a security invariant.
- **P1 (RED test needed before next feature):** A regression here degrades UX but
  is eventually detectable.
- **P2 (nice to have):** Edge cases that would be caught by monitoring or manual QA.

### Step 5: Propose the highest-value RED test
Pick the single most impactful gap. Write the test specification:
- **Exact file** and insertion point (after which existing test? line number)
- **Behavioral test name** (describes what, not how)
- **Mock setup** (which DB queries to intercept, which fetch calls to mock)
- **Assertions** (exact expected values: `assert.equal(result.error, '...')`,
  `assert.match(result.telegram_message, /.../)`)
- **Why this one first:** business impact justification
- **Test command:** exact `node --test` invocation

The test must be *writable before any code change* (true RED in TDD terms).
It must fail on the current codebase if a guard is broken, and pass once the
guard works correctly.

### Step 6: Document the RED test in the report
In the audit report, include:
1. Full test code (or pseudo-code with exact assertions)
2. Which existing test it should follow in the file
3. The exact command to run it
4. What it proves and why it's the highest-value next test

## Common Anti-Patterns

1. **Counting test cases instead of mapping invariants.** "7 tests exist" is
   meaningless. "4 of 7 guard conditions are tested; 3 silent failure paths
   have zero coverage" is actionable.

2. **Proposing complex end-to-end tests as the first RED.** A test that requires
   orchestrating 3 mock layers, 2 async callbacks, and state mutation is
   fragile. Prefer unit-level guards first — they're the foundation that makes
   end-to-end tests safe to write later.

3. **Prioritizing coverage percentage over business impact.** A 3-line early
   return for "not configured" may have higher business value (prevents silent
   failure in production) than 80 lines of parameter validation on a feature
   used by zero clients.

4. **Verifying happy-path output without verifying the guard was reached.**
   A test that returns `qa_passed=true` proves the QA logic works. It doesn't
   prove that the `render_fixable` retry loop or the `failed` status handler
   works — those branches were never reached.

## Example: Scena Media-Worker Pipeline (July 2026)

### Coverage matrix (extract)

| Source (agent.ts) | Guard/Invariant | Covered? | Test (media-worker-integration.test.mjs) |
|---|---|---|---|
| L2720-2727 | SCENA_TEMP_STORAGE missing → failure | ❌ | — |
| L2758-2771 | ≥2 composition attempts → blocked | ❌ | — |
| L1365-1379 | render_fixable → auto-retry via runAgentTurn | ❌ | — |
| L1341-1347 | current step != analyze_video_output → early return | ❌ | — |

| Source (index.ts) | Guard/Invariant | Covered? | Test |
|---|---|---|---|
| L2285-2286 | status not completed/failed → 400 | ❌ | — |
| L2276 | malformed external job ID → 400 | ❌ | — |
| L2309-2311 | bad URL prefix / decode_ok=false → 400 | ❌ | — |
| L2333-2348 | failed status → DB update + workflow record | ❌ | — |
| L2288-2289 | idempotent callback (same status) → early return | ❌ | — |

### Highest-value RED test: retry limit enforcement (P0)

The `media_worker_retry_limit_reached` guard (agent.ts L2758-2771) blocks a 3rd
composition attempt per workflow run. Without it, a `render_fixable` auto-retry
loop (L1365-1379) could submit render jobs indefinitely — real money per job.

This guard is the **safety net** that makes the render_fixable retry loop safe
to have at all. Test it first.

See the session transcript for exact test code, insertion point, and assertions.
