# Test Gap Analysis for Provider/Dispatch Routing Paths

When auditing a codebase with multi-provider routing (media generation, LLM dispatch,
payment backends, etc.), generic coverage counting is insufficient. Each provider
branch may have distinct payload schemas, endpoints, error modes, and polling strategies.
A gap in one branch is a production fire waiting to happen.

## Methodology

### Step 1: Trace the dispatch decision tree
Follow one tool/action invocation from entry to provider-specific fetch:
```
tool entry → route resolution → provider dispatch (if/switch) → providerX fetch
                                                            → providerY fetch
```

Read the route resolver completely (not first 200 lines). Identify:
- The default provider (first in catalog, or hardcoded fallback)
- All other possible providers
- How route override works (DB rows, workflow step params, env vars)

### Step 2: Map existing tests onto the decision tree
For each existing test, note:
- Which provider path does it exercise?
- Does it verify the *fetch URL* (not just the response shape)?
- Does it verify the *payload shape* per-provider?
- Does it verify routing *dispatch logic* (which branch taken)?

### Step 3: Identify untested branches
A branch is untested if:
- No test sets up mocks that intercept the provider's fetch URL
- No test asserts the provider-specific payload model ID
- No test asserts the payload shape matches the provider's documented schema
- For async providers: no test verifies callback URL registration

### Step 4: Classify gaps by severity
- **P0 (RED test needed before any refactor):** Default provider path completely untested
- **P1 (RED test needed before feature work):** Non-default provider used in production but untested
- **P2 (GREEN expansion):** Edge cases within tested paths (batch, retry, timeout)

### Step 5: Propose exact assertions per gap
For each gap, name:
- **Test file:** where to add (existing or new)
- **Test name:** descriptive, behavioral
- **Mock setup:** which fetch calls to intercept, which DB rows to return
- **Assertions:** fetch URL, payload model ID, payload fields, absence of other-provider fetches

## Common Anti-Patterns

1. **Testing the response parser but not the dispatch.** A test that intercepts `queue.fal.run` and checks the parsed output tells you nothing about whether the Kie branch would have been taken instead or would have worked.

2. **Testing only the happy path of one provider.** If only Fal tests exist and Kie is the production default, the test suite is misleading — it's testing a codepath that may rarely execute.

3. **Provider-agnostic response mocks.** A mock that intercepts `any fetch to any URL` and returns a generic success is actively harmful — it passes both branches identically.

4. **Testing payload sanitizers in isolation without dispatch context.** `buildKieSeedanceVideoInput()` passing unit tests doesn't prove it's actually called when the route resolver picks 'kie'.

## Example: Scena Media Routing

### Decision tree
```
generate_image → resolveActionModelRoute('image_gen')
    → submitSingleImageGeneration(route)
        → route.provider === 'kie' ?
            YES: submitKieImageGeneration() → fetch('https://api.kie.ai/.../createTask')
            NO:  fetch('https://fal.run/...')
```

### What was tested (before audit)
| Test | Provider path exercised | Verifies fetch URL? | Verifies dispatch? |
|------|----------------------|---------------------|-------------------|
| provider-payloads.test.mjs | None (unit tests) | No | No |
| orchestration-config.test.mjs | piapi, fal | Yes (fal.run) | Partially |
| agent-communication.test.mjs | None | No | No |

### Gaps found (P0)
- **Kie image routing:** Zero tests — the production default path
- **Kie video routing:** Zero tests — the production default path
- **Kie batch routing:** Zero tests (count > 1)
- **Payload convenience builders:** `buildKieSeedanceVideoInput`, `buildKieGptImage2Input` never tested
- **Model catalog priorities:** No test verifies Kie entries appear first

### Proposed RED test assertions
See session transcript for exact assertion strings. Each test should:
1. Return `action_model_routes` with `provider: 'kie'`
2. Assert `fetch` called with `https://api.kie.ai/api/v1/jobs/createTask`
3. Assert `fetch` NOT called with `fal.run` or `queue.fal.run`
4. Assert payload `model` field matches expected Kie model ID
5. Assert payload structure matches Kie API schema (prompt, resolution, aspect_ratio, etc.)
