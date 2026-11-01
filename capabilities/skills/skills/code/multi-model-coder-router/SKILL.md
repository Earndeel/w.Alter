---
name: multi-model-coder-router
description: "Build a Hermes coding system where W.Alter orchestrates specialized coding workers with minimal context capsules, scoped credentials, model routing by task type, and mandatory verification. Also covers: coder profile."
version: 1.0.0
author: Hermes Agent
license: MIT
---

# Multi-Model Coder Router

Use this when designing a Hermes-based coding assistant that should feel like a strong full-stack engineer without inheriting the full Hermes payload.

## Goal

Separate orchestration from execution:
- W.Alter (or the main agent) stays the planner/orchestrator
- Coding workers receive only the minimum task context needed
- Model/agent choice is routed by task type
- Credentials are granted by capability scope, not dumped globally
- Verification is mandatory before declaring success

## Core Architecture

Do NOT build one giant all-purpose coder subagent with all memory, all tools, and all secrets.

Instead build four layers:
1. **Orchestrator** — receives the user request, decomposes the work, chooses the worker, grants scopes, verifies output
2. **Task router** — maps task type to the best worker/model/agent runtime
3. **Capability broker** — grants only the credentials and tools needed for that mission
4. **Worker** — executes in an isolated session/worktree with a minimal context capsule

## Why This Pattern

A single giant coding agent tends to fail by:
- carrying too much irrelevant context
- using the wrong model for the wrong task
- exposing too many credentials to every run
- mixing planning, coding, deploy, and review into one blurry role

The orchestrator/worker split produces better routing, lower prompt bloat, safer credential access, and easier debugging.

## Recommended Worker Roles

Start with a small set of specialists instead of dozens of personas:
- **design/frontend worker**
- **backend/architecture worker**
- **debugging/root-cause worker**
- **review/verification worker**
- **deploy/ops worker** (optional, often separate for safety)

Two roles are mandatory even in V1:
- **maker** — writes/fixes code
- **checker** — verifies/reviews/tests independently

## Minimal Context Capsule

Never inject the full Hermes prompt or full conversation by default.

Each worker should receive a compact task capsule containing only:
- `goal` — exact mission
- `repo_path` or `workdir`
- `task_type` — frontend/backend/debug/review/deploy/etc.
- `project_stack` — minimal stack summary
- `likely_files` — likely files/directories to inspect first
- `constraints` — product/architecture guardrails
- `acceptance_criteria` — what counts as done
- `verification_commands` — tests/lint/build/checks to run
- `tool_scope` — allowed toolsets for this mission
- `credential_scope` — allowed secrets/capabilities for this mission
- `return_format` — exact expected output shape

### Example Capsule

```json
{
  "goal": "Fix checkout webhook race on Cloudflare Worker",
  "repo_path": "/root/scena",
  "task_type": "debug-backend",
  "project_stack": ["cloudflare-worker", "d1", "stripe", "admin-ui"],
  "likely_files": [
    "workers/api/src/index.ts",
    "workers/api/src/stripe.ts",
    "tests/webhook/*.ts"
  ],
  "constraints": [
    "No broad refactor",
    "Targeted changes only",
    "If admin UI changes are needed, propose before deploy"
  ],
  "acceptance_criteria": [
    "Webhook processed exactly once",
    "Existing tests still pass",
    "New regression test added if appropriate"
  ],
  "verification_commands": [
    "npm test",
    "npm run lint"
  ],
  "tool_scope": ["terminal", "file", "browser"],
  "credential_scope": ["stripe-webhook", "cloudflare-worker-staging"],
  "return_format": "summary + files changed + verification results + risks"
}
```

## Model Routing Strategy

Start rule-based. Do not begin with a learned router.

Suggested V1 mapping:
- **UI/design/spec exploration** → Gemini / Claude Opus
- **backend architecture / high-judgment refactor** → Claude Opus
- **mechanical edits / test generation / broad file sweeps** → Gemini Flash or Sonnet-class model
- **debugging / log-heavy root cause analysis** → Kimi or Sonnet-class model
- **deploy / ops execution** → strong terminal-capable agent with tightly scoped deploy credentials

Important: use telemetry to refine routing later:
- success rate
- wall-clock time
- number of repair loops
- rollback/revert rate
- user satisfaction

Do not rely forever on intuition about which model is “best” for a task.

## Capability Broker Pattern

Do NOT expose all credentials to every coding worker.

Grant capability bundles per mission, for example:
- `code-only`
- `github-maintainer`
- `cloudflare-staging-deploy`
- `cloudflare-prod-deploy`
- `stripe-readonly`
- `stripe-webhook-write`
- `browser-authenticated-session`

The orchestrator decides which bundle to grant.
Workers should never self-select unrestricted secrets.

## Isolation Rules

Every coding mission should run in one of these:
- separate git worktree
- separate Hermes profile/session
- separate external coding agent runtime (Claude Code, Codex, etc.)

Isolation reduces:
- context pollution
- edit conflicts
- accidental state leakage between tasks
- credential overexposure

## Verification Pipeline

Never accept “done” from the implementer alone.

Recommended flow:
1. Orchestrator classifies the task
2. Orchestrator builds the minimal context capsule
3. Worker implements the change
4. Verification worker runs checks/review/tests
5. Optional deploy worker executes deployment if authorized
6. Orchestrator summarizes result and unresolved risks

At minimum, require:
- implementation evidence
- verification command results
- explicit list of files changed
- known risks or follow-ups

## Good V1 Product Shape

If you want a reusable system inside Hermes, create a tool or wrapper concept like:
- `spawn_coder(...)`
- `route_coding_task(...)`

Useful inputs:
- `goal`
- `repo_path`
- `task_type`
- `preferred_outcome`
- `tool_scope`
- `credential_scope`
- `verification_commands`
- `ui_change_requires_approval`
- `effort`
- `routing_policy`

Backend responsibilities:
- classify task
- choose runtime/model/worker
- create worktree/session isolation
- inject minimal capsule only
- grant scoped credentials only
- run verification
- return structured result

## Practical Recommendation

V1 should usually be hybrid, not purely Hermes-internal:
- W.Alter as orchestrator
- Hermes internal subagents for some tasks
- external coding runtimes (Claude Code, Codex, etc.) when they are stronger for a specific task
- one routing layer on top

This gives real multi-model behavior immediately without forcing all capabilities into one monolithic subagent prompt.

## Router Brain / Dry-Run Policy Pattern

Use this same architecture when the task is broader than coding: routing normal Hermes/W.Alter user turns across direct answers, web research, memory usage, coder profile, reviewer/checker profile, and delegate_task orchestration.

Recommended V1 implementation order:
1. Audit the live config/profile/tool state first: main config, profiles, `delegate_task`, coder profile scripts, and any `smart_model_routing` imports/modules.
2. Create an additive policy file (YAML/JSON) outside core code first, e.g. `~/.hermes/config/router_brain.yaml`.
3. Create a dry-run classifier CLI that only reads the policy and emits a decision JSON. It must not spawn agents, edit config, call models, or touch gateway/core behavior.
4. Include safe telemetry JSONL from day one: route name, confidence, mode, profile, model selection, query hash, redacted preview, signals, warnings. Never log raw queries or secrets.
5. Add a self-check command that validates referenced paths and marks optional missing modules as warnings, not hard failures.
6. Only after dry-run smoke tests pass should you consider a core/gateway integration hook.

Good route families for a general Router Brain V1:
- `simple.weather` / realtime lookup → direct, web tool only, memory off
- `research.web` → direct with web, small memory budget
- `multi_step.orchestrator` → delegate_task orchestration with current child limits
- `coding.coder_async` → coder profile / super-stack async mission
- `review.checker` → checker/review path, sync if useful
- `simple.general` → direct answer, no tools/memory for short low-risk prompts
- `fallback.default` → current main model, gated memory, no orchestrator

Routing implementation lessons:
- Keep V1 rule-based and deterministic. Learned routing can come later from telemetry.
- Let explicit policy priority dominate lexical score. Review prompts often contain `code`, `backend`, or `repo`; without priority dominance they get misrouted to implementation.
- Do not put platform/product nouns (`cloudflare`, `stripe`, `api`, `backend`, `worker`) alone in the coder route. They also appear in research prompts like “cherche docs Cloudflare”. Route coder on action/error words (`debug`, `fix`, `bug`, `failing test`, `implement`, `patch`, `repo`) plus context.
- Add negative phrases for web routes (`sans chercher`, `sans internet`, `no web`, `without internet`) so explicit “do not search” requests do not trigger research.
- For CLI smoke tests with accented text, prefer Python `subprocess.run([...])` argv or `--query-file` over shell-embedded JSON strings; shell escaping can turn `météo` into a non-matching escaped sequence.
- If `agent.smart_model_routing` is imported by tests/config but the module is absent, record it as a self-check warning and avoid depending on it until restored.

Minimal verification matrix:
- météo/simple → weather route
- latest docs/search/source request → research route
- workflow/plusieurs étapes/planifie → orchestrator route
- debug/fix repo bug → coder async route with `dry_run.executed=false`
- review/audit/security review → checker route
- long no-route prompt → fallback route
- synthetic token in prompt → redacted from JSON and telemetry

## Anti-Patterns

Avoid these:
- sending the full Hermes system payload to every coder worker
- using one model for every coding task
- giving Stripe + Cloudflare prod credentials to all jobs
- letting workers choose arbitrary secret scopes themselves
- coupling deploy authority directly to normal coding authority
- declaring success without independent verification

## 3-Phase Rollout

### Phase 1
- 3 worker profiles: design, backend, debug
- rule-based routing
- minimal task capsule
- credential scopes
- mandatory verification

### Phase 2
- support multiple runtimes: Hermes subagents, Claude Code, Codex, etc.
- worktree/profile/session isolation
- scorecards per model and task type

### Phase 3
- learned routing from actual performance
- policy engine for risk/cost controls
- budget-aware routing
- persistent technical memory per worker type

## Key Principle

The best coding agent is usually not the one with the biggest prompt.
It is the one with:
- the right model
- the right tools
- the right credential scope
- the right amount of context
- the right verification loop

## Vérifier une intégration fournisseur jusque dans les routes ordinaires

Après l’ajout d’un fournisseur, vérifier une route sans imposer de modèle ni de fournisseur : `walter-router route 'Raisonnement complexe' --task general --level L3`. Répéter via MCP `walter_route(request="Raisonnement complexe", task="general", level="L3")`. Un appel avec `provider` imposé ne prouve pas que les consommateurs ordinaires utilisent la nouvelle intégration.

Pour les routes texte, imposer l’invariant suivant après le classement effectif : `provider == execution[0].provider` si une route existe ; sinon, ne conserver aucun fournisseur périmé. Calculer ce résumé après l’application des abonnements, quotas et critères de disponibilité. Après une exécution avec secours, lire `routed.provider` pour identifier le fournisseur réellement utilisé.

Résoudre la racine avec `walter path router`. Pour diagnostiquer une contradiction entre résumé et exécution, examiner `serve/routes.py`, `serve/named.py` et `serve/agent_view.py`. Examiner `serve/execution.py` pour expliquer l’ordre des fournisseurs. Vérifier les indicateurs courants, notamment `probe_ok`, avant d’attribuer cet ordre au prix : un fournisseur moins cher peut passer après un fournisseur disponible lorsque sa sonde échoue.

Ajouter des tests de non-régression couvrant une priorité d’abonnement, un changement d’ordre et l’absence de route. Vérifier les parcours ordinaires et nommés, puis refaire les lectures CLI et MCP. Exécuter `walter-router docs --check` si les descriptions ou références générées changent. Pour une nouvelle intégration d’exécution, valider aussi un appel réel avec outil et le streaming ; une décision de routage seule ne valide pas le transport.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **coder-profile** — The `hephaestus` Hermes coding-worker profile in practice: invocation, task capsule template, Kie provider integration, external routing, live validation checklist.
  Read `references/merged-coder-profile/coder-profile.md`.
