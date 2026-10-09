---
name: security-audit
description: Systematic read-only security audit methodology — data layer, auth, multi-tenancy, webhooks, billing, encryption, SSRF.
version: 1.0.0
tags: [security-audit, code-review, data-layer, webhooks, encryption, multi-tenancy]
---

# Security Audit

Systematic read-only security audit of a codebase. Produces a structured report with file:line citations, severity classification, and proof-vs-suspicion tagging.

## When to Use

- User asks for a security audit, code audit, or vulnerability assessment
- Auditing data layer, auth, multi-tenancy, webhooks, billing, or encryption
- "Read-only" or "ne modifie aucun fichier" is specified
- Pre-deployment security review of a backend service

## Constraints

- **Read-only**: Never modify, patch, or write files during the audit
- **Never print secrets**: Redact tokens, API keys, credentials in all output
- **Cite file:line**: Every finding must include exact file path and line number
- **Distinguish proof from suspicion**: Label each finding `Preuve` (direct code evidence) or `Suspicion` (pattern-based concern, missing validation, inferred risk)

## Methodology

Execute in this order — each phase informs the next:

### Phase 1 — Surface Exploration
- List project structure: `search_files(target='files')` with glob patterns
- Identify config files: `wrangler.toml`, `.env`, `config.yaml`, CI/CD configs
- Map the codebase: DB schemas, API routes, auth modules, webhook handlers, billing code
- Read the router/dispatcher to understand all entry points

### Phase 2 — Data Layer
- Read ALL migration files and schema definitions
- Check: foreign keys, indexes, column types (REAL vs INTEGER for money), sensitive columns (tokens, secrets)
- Verify multi-tenant isolation: every table that holds per-tenant data must JOIN or WHERE on tenant/client ID
- Look for: plaintext secrets in schema, missing constraints, missing audit columns

### Phase 3 — Authentication & Authorization
- Read auth module(s) end-to-end
- Check: password hashing algorithm, session token design, CSRF protection, OAuth flows
- Verify: every admin/privileged route has auth check BEFORE business logic
- Look for: raw secret comparisons, missing rate limiting on login, token lifetime issues, hardcoded fallback keys

### Phase 4 — Webhooks (Inbound & Outbound)
- Map all webhook endpoints from the router
- For each inbound webhook: is there signature verification? idempotency? replay protection? rate limiting?
- For each outbound webhook: is the URL validated (HTTPS enforced, no private IPs)? timeout set?
- Look for: unauthenticated callbacks, cross-tenant job matching via loose queries, SSRF vectors

### Phase 5 — Billing & Credits
- Trace the full lifecycle: purchase → credit → consumption → refund
- Check: atomicity of credit operations, idempotency on webhook-triggered refunds
- Verify: credit check BEFORE resource allocation, ledger entries for every mutation
- Look for: race conditions, double-spend, double-refund, float rounding issues

### Phase 6 — Encryption & Secrets
- Map all secrets: environment variables, DB columns, config files
- Verify: encryption at rest for sensitive DB columns, proper key derivation, unique IVs
- Check: hardcoded fallback keys, key reuse across contexts, key exposure in logs/errors/admin APIs
- Look for: `substring(0, N)` exposure, debug endpoints returning keys, fallback to predictable values

### Phase 7 — Deployability & wiring (daemons, CLIs, control planes)
For any codebase that ships a service, daemon, or CLI, verify the system can actually
run end-to-end — a library that is never wired into a runnable process is not deployable:
- **Resolve every declared entrypoint.** Map every console script / entry point in
  `pyproject.toml`/`setup.py` (e.g. `walter-node = "pkg.cli:node_main"`) to a real `module:symbol`.
  An entrypoint whose module is absent = the daemon can never start AND the test suite
  errors at collection (`ModuleNotFoundError`). Confirm the module file actually exists.
- **Label library-only vs wired code.** `grep` for the orchestration constructors
  (`NodeService(`, `BrokerService(`, `UnixRpcServer.start`, `serve_forever`) *outside* the
  `tests/` tree and any `__main__`/launcher. If they appear **only in tests**, there is no
  production wiring — no code anywhere binds store + service + server into a process.
- **Include *silently disabled* seams in the wiring map.** Grep the *wiring constructors*
  (e.g. `build_x_handler`, `start_x_server`) for optional parameters — not just the class.
  A service hook defaulted to `None` (e.g. `verifier: Verifier | None = None`) that the CLI
  wiring never passes means a documented capability (postcondition verification) is fully
  implemented + unit-tested but **silently non-functional in the shipped daemon**. That is
  often the single highest-value finding of a wiring audit. Also watch for *two parallel
  duplicate designs* of the same route (e.g. an `execv`-to-ssh shim that is the live Hermes
  path vs. a library `McpStdioSession` SSH/MCP wrapper that nothing outside tests
  constructs): label which route the docs actually describe and confirm only it is reachable.
  Distinguish three buckets in the report: **executable** (reachable from an entrypoint),
  **interface/source seam** (defined + tested, never constructed by any daemon/CLI), and
  **dead-end wiring** (reachable but authorizer-denied).
- **Check policy-live vs adapter-implemented dead-ends.** An adapter may implement a
  capability the policy marks `contract_support`-only (not in `live_support`, or empty
  `live_support`) ⇒ authorization denies it at runtime (`platform_not_live`, even with a
  grant, because the live check precedes the grant check). Safe but unreachable — report as
  a wiring dead-end, not a vuln. Read the policy `live_support` tuple per capability, not
  just the adapter's `compile()`.
- **`--check` may still write state.** Config/dry-run builders often construct the real
  store/audit/key objects before returning — "check" means *no socket*, not *no state
  written*. If the audit covers what a validator modifies, note these side effects.
- **Run the suite read-only** to honor the no-modify rule:
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider` (suppresses
  `__pycache__` and `.pytest_cache` writes). Count tests per file with
  `grep -cE '^def test_'` and total items without a second collection run.
- **Reproduce the documented dev workflow** in the intended venv (`uv sync && pytest`).
  A *different* venv that lacks the package installed (e.g. a "hardened" venv with only
  pytest) yields `ModuleNotFoundError` on every test module and aborts before collection —
  that is a **reproducibility/CI blocker**, not a code failure. Report it as such.
- **Detect a mid-build / incomplete tree.** `find -newermt` / mtimes: if files were written
  minutes apart during the audit, the tree is mid-build. A test file written before the
  module it imports is a pending-work signal, not a regression.
- **Trace privileged/stateful paths for dead-on-arrival slices.** If an elevated flow needs
  a grant/approval token, verify an **issuance** RPC actually exists — exposure of only a
  *consumption* method (`broker.execute`) with no issuance method makes the whole elevated
  slice impossible end-to-end (fail-safe but non-functional). Check state-machine terminal
  statuses: a terminal `REFUSED` keyed on an idempotency key can permanently lock retries.

### Phase 8 — Report
Structure the final report as:

```
# 🛡️ RAPPORT D'AUDIT SÉCURITÉ — PROJECT

**Périmètre** : path (lecture seule)
**Date** : YYYY-MM-DD

## 1. COUCHE DONNÉES (schema, migrations, isolation)
## 2. AUTHENTIFICATION & MULTI-TENANCY
## 3. WEBHOOKS (entrants/sortants, SSRF)
## 4. FACTURATION & CRÉDITS (quotas, idempotence)
## 5. CHIFFREMENT & SECRETS

## 📊 SYNTHÈSE DES RISQUES
| # | Gravité | Problème | Fichier:Ligne |
|---|---------|----------|---------------|

## 🔧 MESURES PRIORITAIRES
1. ...
```

Use these severity levels:
- 🔴 **CRITIQUE** : exploitable, perte de données/d'argent, compromission de secrets
- 🟡 **MODÉRÉ** : mauvaise pratique, risque conditionnel, défense en profondeur
- 🟢 **FAIBLE** : amélioration souhaitable, impact minimal

Tag each finding:
- **Preuve** : code visible qui démontre le problème (ex: `fetch(userUrl)` sans validation)
- **Suspicion** : pattern à risque sans exploit direct confirmé (ex: absence de rate limiting)

## Pitfalls

- **Don't audit what you can't read**: If a file is too large, use pagination. Never skip a route handler or auth module.
- **Secrets in search results**: `search_files` with `pattern='secret|token|api_key'` may match redacted output. Always verify against the actual file with `read_file`.
- **D1/SQLite specifics**: CHECK constraints are enforced, FOREIGN KEY requires `PRAGMA foreign_keys = ON`, TEXT columns can hold anything — type safety is at application level.
- **Cloudflare Workers specifics**: No filesystem access, all state in D1/KV/R2. `ctx.waitUntil()` for async work. Secrets via `wrangler secret put`, accessed as `env.SECRET_NAME`.
- **Don't confuse schema files**: Multiple `.sql` files may define the same tables (initial vs migration vs reference copies). The canonical production schema is what `wrangler.toml` points to.
- **Admin route naming**: Hyphens vs underscores matter — check the actual route definitions, don't guess.

## Reference

See `references/scena-audit-2026-07.md` for a complete audit example with pattern recognition across data layer, auth, webhooks, billing, and encryption findings.

For a deployability check of a shipped daemon/CLI/control plane — resolve declared entrypoints to real modules, grep for production wiring vs. library-only code, reproduce the documented dev workflow in the intended venv, detect mid-build trees by mtime, and spot dead-on-arrival privileged slices (issuance method missing) — see `references/device-node-e2e-review-2026-08.md`.

For a *verify-and-pin* hardening pass on an untrusted-input JSON request contract + fail-closed authorization policy (not read-only audit — tests are expected), see `references/contract-policy-hardening.md`: the full checklist of bounded-field / JSON depth-size-node / canonical-digest / unknown-field / risk-ordering / duplicate-spec properties, each verified with a behavioral test, plus how to triage pre-existing env failures out of your result.

For an *implementation* hardening pass on a Python subprocess/command dispatcher (TOCTOU, symlink/rename races, PATH & env poisoning, privilege bits — fail-closed with adversarial TDD tests), see `references/subprocess-executor-hardening.md`.

For an *implementation* hardening pass on a tamper-evident HMAC-SHA256 audit/hash chain in SQLite (canonical JSON, non-finite/canonical rejection, payload bounds enforced before AND after redaction, operation-id field-delimiter attack, key+DB 0o600 + symlink/hardlink safety, wrong-key verification), see `references/hmac-audit-chain-hardening.md`.

For an *adversarial re-verification* audit of a fully-hardened Unix-socket JSON-RPC control plane (does the hardening hold in the shipped wiring?) — proof checklist for grant digest recomputation vs client-supplied value, kernel-only peer identity, socket chown+0600 ownership, error sanitization on BOTH the error and result channels, subprocess TOCTOU/env, SSH manifest rewriting, and the fail-closed-unavailable-vs-regression classification rule (stale-test/dropped-feature signal) — see `references/device-node-adversarial-audit-2026-08.md`.

For a *wiring-vs-seam* audit pass on the same control plane (all 335 tests green) — the
three-bucket executable / interface-source-seam / dead-end-wiring classification with the
specific unimplemented-verifier finding, policy-live vs adapter-implemented dead-ends
(empty `live_support`), the `--check`-writes-state side effect, cross-store hardening
asymmetry (audit-parent not hardened), and the read-only pytest flags used — see
`references/device-node-wiring-seam-audit-2026-08.md`.

For a read-only review of a change to an agent's *tool-result classification / terminal-
reply enforcement* (direct-reply vs text-only tools=[] fallback vs non-terminal) — the
no-second-model-call check, defense-in-depth (producer `safe_to_return` certification +
classifier re-filter of error/status/deny-patterns), the `completion_known` gate that
isolates new behavior from legacy actions, internal-leak paths in direct and empty-text
fallbacks, and the regression/state checklist — see
`references/agent-tool-result-classification-review.md`.

For an *out-of-process shadow/sidecar observer* audit — proving a telemetry/replay module
can never affect a hot production path — see `references/sidecar-shadow-isolation-audit.md`:
prove isolation by IMPORT-CLOSURE of the ExecStart chain (not repo layout), zero backend/
SSH/action counters, sqlite `mode=ro` URI, correlation/cursor/quarantine/idempotence with
the decisive second-poll-0/0 evidence, systemd `diff` + `RestrictAddressFamilies=AF_UNIX`/
oneshot-no-Restart confinement, secrets-absent (runtime identity_ref vs private key), the
must_fix-vs-suggestion discipline, and the machine-validated flat JSON deliverable.

## Checklist (sidecar/shadow isolation quick pass)

- [ ] Import closure of the daemon entrypoint (ExecStart module → imports) contains NO
      subprocess/backend/SSH/call_tool/capture/vision — backend/SSH code lives only in
      modules that tests/benchmarks import, outside the poll loop.
- [ ] Poll result counters (`additional_backend_calls`, `failures_affecting_v1`,
      clicks/keystrokes/screenshots/vision/device_actions) all 0 in code AND report.
- [ ] DB open via `file:...?mode=ro` URI; state.db size/mtime unchanged during run.
- [ ] Events exclusive-create (`open("x")`) + atomic cursor (`.tmp`→`replace`); a real
      second poll shows 0/0 (idempotence). Malformed pairs quarantined (cursor advances);
      unpaired result blocks (fail-closed) — note permanent-stall risk as suggestion.
- [ ] Installed systemd unit `diff` == deploy; `Type=oneshot`, no `Restart=`,
      `NoNewPrivileges`, `ProtectSystem=strict`, `RestrictAddressFamilies=AF_UNIX`,
      `ReadWritePaths` narrowed to the spool, `UMask=0077`. `ActiveState=inactive/dead`
      is normal for an already-run oneshot.
- [ ] No secrets in code/docs; device store holds a runtime `identity_ref`, never a key.
- [ ] must_fix ONLY when a stated invariant is actually violated; documented+tested design
      choices are suggestions. must_fix ⇒ `passed=false`.
- [ ] Deliver the flat machine-validated JSON (`passed/must_fix/suggestions/verified/
      tests/summary`) with empirical `verified` evidence strings.
