# Auditing agent tool-result classification / terminal-reply enforcement

Read-only review pattern for a change that classifies *tool results* as terminal and
may return a user-facing reply **directly** (no second model call) or force a text-only
continuation. Verified on the Hermes agent "Direct Terminal Reply" micro-lot; generalizes
to any codebase where a tool contract decides whether the turn keeps running.

## What this class of change does
A tool produces a structured result; a classifier decides it is *terminal* (turn's tool
phase over), then either:
- (a) **direct-reply** — returns a producer-certified `user_message` to the user with **no
  second provider call**, or
- (b) **text-only fallback** — sends the model one more call with `tools=[]` so it cannot
  legally emit another tool call, or
- (c) non-terminal → behaves exactly as before.

## Verification checklist (map each to file:line)

1. **No second model call on the certified path.**
   - Find the direct-reply branch AFTER tool execution; confirm it `break`s out of the loop
     before any next API call is reachable.
   - The gate must be `safe_to_return is True` (implies terminal), not just "terminal".
   - Tests MUST assert `len(requests)==N` (single provider call) AND final_response == the
     certified message — a unit test that only checks the text without counting calls can
     hide an extra model round-trip.
   - Cross-check against a real smoke run (1 request / 0 second call) — don't trust the
     test alone.

2. **Text-only fallback for uncertified / sensitive terminals.**
   - Whatever strips tools (`tools_for_api = [] `) must trigger for ANY terminal result,
     not only certified-safe ones, so a sensitive/uncertified terminal still can't spawn a
     tool call.
   - Verify the runtime striker is per-instance and reset at the next turn boundary —
     otherwise tools stay disabled across turns (state leak).

3. **Non-terminal unchanged.** Identify the *gate* that keeps pre-existing behavior intact.
   Here it was `completion_known is True`: only newly-producer-flagged results carry that
   field, so all legacy actions are automatically non-terminal. Grep which tools actually
   emit the gate key — if many tools emit `status: success/confirmed/done` + true gate, the
   classifier is too broad and will kill legitimate multi-tool batches. Verify a
   non-terminal test keeps tools on the *subsequent* call.

4. **No internal message/error/stack-trace/secret leak.**
   - Raw `message` and `error` fields must NEVER reach a direct return — only a separate
     `user_message` that survived a classifier filter.
   - Look for defense-in-depth: producer certifies `safe_to_return` at the tool boundary
     AND the classifier re-filters (rejects if `error` present, if status ∈
     {error,failed,internal_error,exception}, if message non-str, or if deny-pattern
     regexes match: traceback, stack trace, api key/token/secret/password=, PRIVATE KEY).
   - Check BOTH the direct-return path AND any empty-text fallback that substitutes
     `user_message` — the fallback must use the already-classifier-filtered field, never
     the raw one.
   - Note honestly: deny-pattern regexes are a heuristic backstop, not a guarantee (bare
     tokens, creds-in-URLs slip through). The real protection is explicit producer
     certification + error-status rejection.

5. **Generic contract, not tool-specific.** The consume side (loop) must not import the
   specific tool. A different tool emitting the same contract should hit the same
   direct-reply / tools=[] behavior. Verify with a test using a *second* tool.

6. **No cross-subsystem impact.** Confirm the change sits downstream of routers/intent
   selectors (they run before classification), and that capture/AX/first-video/skills
   paths aren't touched. The completion-known gate also isolates them.

7. **Tests probative.** Good suite asserts: direct reply is 1 call; internal-error and
   secret-style messages are NOT returned even with safe_to_return=True (forces tools=[];
   2 calls, clean final text); legacy `message`-only is NOT a direct-reply capability;
   terminal blocks later sibling batch calls; non-terminal keeps tools across calls.
   Look for gaps (e.g. empty-model-text fallback, cross-turn state reset) and note them as
   minors.

8. **Regression / concurrency / state.**
   - Per-instance state, first-wins for the recorded terminal result, reset at turn start.
   - A terminal result in a batch skips the *remaining* sibling calls (synthetic "skipped"
     results) — confirm that's intended, not a surprise drop.
   - Watch statuses newly classified terminal (e.g. `verify_state` returning `satisfied`
     closes the tool phase) — fine when it's a final check, but flag if a capture→verify→
     act sequence is expected.

## Read-only test hygiene
Run with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider` so the audit
doesn't write `__pycache__`/`.pytest_cache`. Run the targeted scope files plus the
adjacent router/AX/backend regression files; a full-dir run may time out on large suites —
split into targeted subsets.
