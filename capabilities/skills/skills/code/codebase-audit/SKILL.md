---
name: codebase-audit
description: Use when the user asks you to audit, review, or assess a codebase read-only — quality review, production readiness, architecture audit, security assessment, or gap analysis. You do NOT modify files.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [audit, review, read-only, code-review, quality, architecture]
    related_skills: [code-review, plan, systematic-debugging]
---

# Codebase Audit (Read-Only)

Deep, structured read-only audit of a codebase. No modifications allowed. All findings cite files and line numbers.

## When to Use

- User asks for "audit", "review qualité", "production readiness", "architecture assessment", "gap analysis", "dette technique"
- User specifies "lecture seule", "ne modifie aucun fichier", "read-only"
- Before a major refactor to establish baselines
- Post-incident root cause analysis of structural issues
- Vendor/third-party code assessment
- Conversational agent / LLM harness audit (ReAct loops, Telegram bots, voice agents) — see `references/conversational-harness-audit.md`
- **Frozen-artifact / release-bundle review** (a `.tar.gz` "lot" deliverable with pre-stated pass counts — reproduce everything yourself in an isolated copy; never replay the parent's claims). Full verification ladder incl. the determinism/anti-fabrication byte-compare: `references/frozen-artifact-independent-review.md`
- **Benchmark / metric-evidence audit** (a bundle asserting pass counts, latency percentiles, preservation/reduction %, equal call counts, and a green suite — adversarial honesty check) — reproduce every number, test gates for vacuousness/tautology, catch schema-drift-through-import-context, sweep artifacts for PII: `references/benchmark-evidence-audit.md`
- **Candidate-lot / plugin-upgrade gate audit** (a git-tracked candidate that must prove no V1-core mutation, no new model-facing surface, isolation/fail-open/boundedness, and exact-object seam return): `references/plugin-candidate-gate-audit.md`
- **Phase / roadmap delta-matrix audit** (audit a staged plugin or product against an abstract "phases A–M" / "Lots 2.x" list — produce an existing/reusable/missing matrix, a version target, safe E2E scenarios, and blockers; handles absent phase specs, remote-VPS→remote-mac transport, and the aggregate-smoke attestation pitfall): `references/phase-delta-matrix-audit.md`

Don't use for: line-by-line PR review (use `code-review`), writing new features, fixing bugs.

## Methodology

### 1. Cartography (structure scan)
- Run `find` excluding `.git`, `node_modules`, `dist`, `.wrangler`, cache dirs
- Identify the repository root and key directories (src, tests, docs, config, scripts)
- Count files per category (source vs test vs config vs doc)
- Note the build system, package manager, framework
- **Establish a content baseline early.** If the tree has no `.git` (or you suspect concurrent edits), snapshot source+test file hashes *before* deeper reading so you can later prove nothing changed under you:
  `find src tests -name '*.py' -exec md5sum {} \; | sort -k2 > /tmp/audit_baseline.txt` — re-run it at the end and diff. If it shows mutation, the tree is a moving target: qualify every finding as *as-of-now*, re-run the full test suite once at the end, and flag the instability as a production-readiness finding (no pinned baseline ⇒ not reproducible/CI-able).
- **Verify the suite state once up front** (`pytest -q`, `ruff check src tests`) so later
  findings reference a known-good or known-broken starting point, and re-verify at the end.
  On a strict read-only audit, run the suite without writing cache/bytecode:
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider` (suppresses
  `__pycache__` and `.pytest_cache`) so "no files modified" stays literally true even when
  tests must still be executed.

### 2. API / Backend Audit
- Read the main entrypoint (router, server, worker handler)
- Trace one critical request path end-to-end
- Check: route resolution mechanism, middleware, error handling, CORS, auth
- Check: input validation, rate limiting, secret management
- Check: response shapes, error codes, status consistency
- Identify: circular dependencies, god objects, missing abstractions

### 3. Data Layer
- Read all schema files (SQL, migrations, ORM models)
- Count tables, indexes, foreign keys
- Check: migration versioning, seed data consistency with code
- Check: column types, constraints, default values
- Flag: duplicated schemas, ad-hoc schema changes without migration files

### 4. Frontend / UI Audit
- Identify: framework (or lack thereof), bundler, CSS approach
- Check: component reuse vs duplication, state management
- Check: error handling in fetch calls, loading states, empty states
- Flag: stale/conflicting page versions (e.g. `index-v2.html` vs `index.html.bak`)

### 5. Test Suite
- Count test files and test cases
- Map test coverage to critical flows
- Identify: which critical flows have NO tests (gaps)
- Assess: test infrastructure quality (mocks, helpers, fixtures)
- Check: can tests run without external dependencies?
- **For multi-provider routing codebases:** use the provider dispatch gap analysis methodology in `references/test-gap-analysis-routing-paths.md` — trace each tool invocation from entry through route resolution to per-provider fetch calls, map existing tests onto the decision tree, and identify untested provider branches. Generic coverage counting misses that the default provider path may be entirely untested while the fallback path has full coverage.
- **For business-logic functions with guard chains, error branches, and state transitions:** use the invariant mapping methodology in `references/test-gap-analysis-invariant-mapping.md` — read every existing test, extract the invariant each proves, cross-reference against every conditional branch in the source, prioritize gaps by business impact, and propose a specific RED test with exact assertions. Guard counting beats coverage percentages.
- **For test/evidence audits where the ask is "which flows are covered and what is NOT proven":** inventory every test function with line numbers, run the canonical suites live, and build a Flow × Proven(file:line) × NOT-proven evidence matrix with the skepticism passes in `references/test-evidence-audit-matrix.md` — verify "E2E" labels mean real automation (grep markers + real transport connections), prove plugin/extension-side negatives by grep, and check that documented invariants are enforced at the layer claimed.

### 6. Scripts, Docs, CI/CD
- Check: `package.json` scripts (test, build, deploy, lint)
- Check: CI config files (`.github/workflows/`, `wrangler.toml` envs)
- Check: documentation coverage (README, ARCHITECTURE, CONTRIBUTING, OpenAPI specs)
- Check: deployment configuration (environments, secrets, DNS)

### 7. Cross-Cutting Concerns (Coherence)
- Compare code constants with database seeds — flag divergences
- Compare documentation claims with actual code behavior
- Check: package.json dependencies vs actual imports (phantom deps)
- Check: environment variable references across configs and code

### 7bis. Model-Facing Tool Surface Diffs (schema + dispatcher + backend)

When the review covers a diff that adds or changes a model-facing tool (LLM tool schema,
dispatcher/entry point, backend implementation — e.g. the `computer_use` tool family),
the generic checklist misses most real defects. Review the contract end-to-end:

- **Schema ↔ dispatcher cross-reference is the #1 check.** Grep the tool's JSON schema
  properties and verify every key the dispatcher reads via `args.get(...)` / `args[...]`
  is declared there. An action in the enum whose required property is missing from the
  schema is **dead-on-arrival**: the LLM is only given the schema, so it can never supply
  the argument. Real catch: `open_url` was advertised in the action enum but its `url`
  property was never added to the schema — every model call returned the "requires a
  non-empty `url`" validation error while all tests passed (see below).
- **Test the tool entry point, not just the backend.** Unit tests hitting
  `backend.some_action(...)` directly bypass the schema and prove nothing about the
  model-facing contract. Insist on at least one test through the real entry point
  (e.g. `handle_computer_use({"action": ...})`) so schema gaps surface.
- **Approval classification.** Every new mutating action must be in the
  destructive/approval-gated set; read-only actions in the safe set. Verify the gate runs
  *before* dispatch, and that any central bypass/approval hook fails closed (exception →
  fall through to the local deny path, never implicit allow).
- **Fail-closed direction of new guards.** Unknown geometry → refuse raw coordinates;
  unknown backend name → structured refusal; invalid frame → omit image but keep AX
  elements; driver error → error result, not silent success. Check each new `if/except`
  returns refuse/deny on the unknown branch.
- **Parallel routes must not undercut validation.** If one action validates an input
  (e.g. `open_url` accepts only http(s)/about:blank) but a sibling action forwards the
  same input unvalidated (e.g. `launch_app.urls`), the validation is a token control —
  flag it even when approval-gated.
- **Bounded pass-throughs.** Array/int args forwarded to a backend/driver should be
  bounded (count/max/min) and type-checked (reject bools for ints) in the dispatcher
  before `json.dumps`, not only in the backend.
- **Silently-ignored params.** `capture_after`-style flags honored on some actions but
  silently dropped on new ones is a real finding — either honor them or return a signal
  that they were ignored.

### 8. Report Structure
Deliver a single comprehensive report in the user's preferred language:
1. **Architecture** — physical structure, deployment topology, dominant patterns
2. **Component-by-component** — ✅ strengths, ⚠️ debt, 🔴 risks for each layer
3. **Test Coverage** — total count, critical gaps with specific flow names
4. **CI/CD & Docs** — what exists, what's missing
5. **Coherence Issues** — numbered table of inconsistencies found
6. **Prioritized Recommendations** — P0 (blocking), P1 (critical debt), P2 (improvements)
7. **Executive Summary** — 3-sentence bottom line

Every finding cites `file:line` references. Recommendations are actionable (not "improve X" but "add Y to file Z").

## Pitfalls

1. **Auditing breadth without depth.** Reading first 200 lines of every file produces shallow findings. Pick 5-8 key files and read them completely.
2. **Missing file-level citations.** "The auth is weak" is useless without `auth.ts:45-67`. Every finding must pin a location.
3. **Recommending without prioritization.** A flat list of 20 recommendations is noise. P0/P1/P2 triage is mandatory.
4. **Skipping test gap analysis.** The most valuable audit finding is often "flow X has zero coverage." Explicitly name untested critical flows.
5. **Not checking DB seed vs code constants.** This consistently catches the highest-impact bugs (preset divergence, wrong provider configs).
6. **Trusting a single mid-audit pass on a mutable tree.** Without VCS, files can change while you read — a failing test you cite may have been fixed (or a new one introduced) by the time you write the report. If the baseline hash diff flags movement, say so explicitly and re-verify the suite at the end; never present prose findings as stable contract truth for a tree with no pinned baseline.
7. **Using `git diff --stat` as the read-only proof on a non-git tree.** If there is no `.git`, that command errors out and proves nothing. Use the hash baseline from step 1 instead — an empty start/end diff is the no-git equivalent of a clean `git status`.
8. **Trusting "E2E"/"Delivered" labels without proof.** A roadmap or skill "Delivered" row claiming e.g. "macOS E2E smoke test" may rest on a one-off manual run with zero automation. Grep for e2e/live pytest markers and real transport spawns (`socket.connect|asyncio.open_connection|subprocess.*ssh|create_connection`); zero hits means the label is a manual smoke test — say so, don't repeat the claim. Green tests today with no git/CI is an unpinned snapshot, not a gate.
9. **Crediting a documented invariant as enforced when it lives at the wrong layer.** E.g. "a privileged broker must not run from a user-writable checkout" may only be enforced by the subprocess executor's ownership checks, not by daemon startup validation — read the daemon's validation path before crediting the claim, and name which layer (and which test) actually enforces it.
- **Trusting an in-repo test to prove an architecture claim.** A guard test that asserts "no app markers / no web imports" only proves itself; grep the runtime independently. Likewise, a simulation harness that mints its own success events passes by construction — confirm honesty flags (`live_execution_performed=false`, `evidence_class`, `synthetic:`) and, for a frozen bundle, regenerate committed artifacts and byte-compare (see `references/frozen-artifact-independent-review.md`).
- **Treating host-app baseline tests as covering the plugin's own behavior.** The host's capture-integrity or backend-registry tests passing do not exercise a plugin's `_mark_capture_integrity` / strategy-wiring code. Prove plugin-side coverage by grepping the plugin test file for the plugin's own function names — zero hits is a finding.
- **Counting a tested-but-unwired component as shipped.** A feature that is implemented, unit-tested, and green can still be absent from the production path: grep the *wiring constructors* (`build_*_handler`, `start_*_server`, `register_*`) for optional params defaulted to `None` and for class constructions outside `tests/`. A `verifier=None`-style default that the daemon wiring never overrides silently disables a documented capability (e.g. postcondition verification) while the README still advertises it. Classify findings as **executable / interface-or-source seam / dead-end wiring** and report reachability explicitly.

## Verification Checklist

- [ ] Full file tree enumerated (excluding build artifacts)
- [ ] At least 8 key source files read completely (not just first 200 lines)
- [ ] Every finding has file:line citation
- [ ] Test gaps table names specific untested flows
- [ ] DB schema compared against code constants for divergence
- [ ] Recommendations triaged P0/P1/P2
- [ ] No files modified — `git diff --stat` is empty (on a non-git tree: start/end source hash baseline is identical)
- [ ] Suite state captured at start AND end (pytest + ruff), movement flagged if they differ
- [ ] Report is in the user's language
