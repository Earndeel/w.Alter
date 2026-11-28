---
name: multi-model-coder-router
category: devops
description: "Dedicated Hermes coding worker profile (hephaestus). W.Alter stays the only user-facing orchestrator; coding tasks are executed by the `hephaestus` profile, which routes models internally by task type."
tags: [coding, profile, routing, hermes, orchestrator]
---

# Coder Profile — Hermes Back-Office Coding Worker

## Purpose

Use this skill when W.Alter needs to hand off coding work to the dedicated `hephaestus` Hermes profile while remaining the sole user-facing assistant.

**Architecture:**
- `default` profile = W.Alter (orchestrator, synthesis, decisions, user interaction)
- `hephaestus` profile = coding executor (implementation, debugging, review, verification) — Greek god of forge
- **Model routing lives inside the `hephaestus` profile's `smart_model_routing` config**, not in W.Alter

## Core Rule

W.Alter decides **whether** to invoke hephaestus.
The `hephaestus` profile decides **which coding model** to use for the task.

Do NOT hardcode coding-model selection in W.Alter unless you need an emergency override.

## Profile Naming

The profile is now named `hephaestus` (Greek god of forge). Rename was done via:
```bash
hermes profile rename coder hephaestus
```
All references to "coder" in config paths, skills, and scripts should use `hephaestus`.

**Agent store:** The hephaestus agent has a SOUL.md (personnalité + workflow) and EVOLUTION.md (auto-apprentissage) at `~/.hermes/agents/hephaestus/`. After each task, use `agent_feedback.py` to log lessons. See `hermes-multi-agent-profiles` skill for full agent store architecture.

**Default model:** mimo-v2.5-pro (cheap orchestrator). Claude is routed in for specific task types.

**Kie.ai Claude provider** (`kie-claude`): Available as a provider (not a profile). Models: claude-opus-4-6, claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5. Auth: Bearer token via `KIE_API_KEY` in .env + vault. Use for coding tasks that need Claude quality — NOT as the default model (full Hermes payload is ~50K tokens, too expensive).

**Smart model routing** routes each task type to the right model:
```yaml
smart_model_routing:
  enabled: true
  routes:
    - name: frontend      → kimi-k2.6 (opencode-go)      — ui, css, react, tailwind, gsap, animation
    - name: backend       → claude-opus-4-7 (kie-claude)  — api, database, auth, worker, stripe, webhook
    - name: debug         → mimo-v2.5-pro (xiaomi)        — bug, traceback, error, fix, crash
    - name: review        → claude-sonnet-4.5 (nous)      — audit, code review, security review
    - name: quick         → deepseek-v4-flash (openrouter) — typo, rename, format, small changes
```

## How W.Alter Should Invoke It

Preferred path for normal code missions — async spawn from W.Alter:

```bash
python /root/.hermes/profiles/coder/scripts/spawn_super_coder_async.py \
  --repo /path/to/repo \
  --task-type backend-debug \
  --goal "Fix the failing webhook race" \
  --constraint "targeted changes only" \
  --acceptance "bug fixed" \
  --verify "pytest tests/test_webhook.py -q"
```

Then monitor progress with:

```bash
python /root/.hermes/profiles/coder/scripts/super_coder_status.py --mission-id <mission_id>
```

Use this as the default W.Alter behavior for coding work that may take more than a quick inline turn.

Preferred synchronous path — use the super-stack mission runner directly when W.Alter should block on the result:

```bash
python /root/.hermes/profiles/coder/scripts/run_super_coder.py \
  --repo /path/to/repo \
  --task-type backend-debug \
  --goal "Fix the failing webhook race" \
  --constraint "targeted changes only" \
  --acceptance "bug fixed" \
  --verify "pytest tests/test_webhook.py -q"
```

What the super-stack adds on top of a raw `hermes -p coder chat` call:
- runtime routing (Claude Code Sonnet/Opus vs Hermes Gemini design)
- repo-local memory from `CODER.md`
- optional repo-local config from `.hermes/coder-project.json`
- credential bundles for child runtimes
- maker/checker split
- worktree isolation
- ledger + telemetry

Low-level fallback path — use this only for direct/raw profile calls when you intentionally do not want the full work OS:

```bash
hermes -p coder chat -Q --source tool -q "<task capsule>"
```

Only add explicit `-m` / `--provider` when W.Alter needs to override the selected runtime/model for a specific mission.

## Task Capsule Template

Send only what the coding worker needs:

```text
TASK TYPE: backend-debug
GOAL: Fix the failing Cloudflare webhook race in checkout flow.
REPO: /root/scena
CONSTRAINTS:
- targeted changes only
- no refactor unless required
- keep admin UI behavior unchanged
ACCEPTANCE:
- failing test reproduced
- fix implemented
- targeted tests pass
- no unrelated files changed
VERIFY:
- pytest tests/path/test_webhook.py -q
- pytest tests/path/test_checkout.py -q
```

Good capsule fields:
- task type
- goal
- repo/workdir
- exact constraints
- acceptance criteria
- verification commands
- any required credentials or deployment scope

## Recommended Workflow

1. W.Alter receives the user request.
2. W.Alter decides the task is coding-related.
3. W.Alter initializes repo-local memory/config once if needed (`init_coder_project.py`).
4. W.Alter launches the super-stack with a minimal mission spec. In native/core-integrated setups, this may be done automatically by Hermes itself instead of via a manual wrapper command.
5. The super-stack selects the best runtime and bundle for the task.
6. The maker executes in an isolated mission workspace when possible.
7. Verification commands run automatically.
8. A checker validates independently.
9. W.Alter reads the ledger/summary and synthesizes back to the user.

## Native W.Alter Auto-Route Integration

If you want coding delegation to feel built-in rather than prompt-driven, the proven Hermes-core pattern is:

- add a dedicated router module such as `agent/super_coder_autoroute.py`
- hook the decision into `AIAgent.run_conversation()` in `run_agent.py`
- when a user turn is classified as a coding mission, short-circuit normal inline answering and spawn the coder mission immediately
- return an operator-style ack containing at minimum:
  - `mission_id`
  - repo path
  - process/session handle if available
  - status command
- teach the CLI/gateway completion layer to recognize super-coder completions and summarize them without re-triggering another coding mission

Useful implementation details learned live:
- keep routing rule-based first; FR + EN keywords are enough for V1
- include a continuation heuristic so short follow-ups like `vas y` still route correctly when the immediately preceding context is clearly a code mission
- store auto-route settings in top-level Hermes config under a dedicated section such as `super_coder_autoroute`
- set `super_coder_autoroute.enabled: false` inside the `coder` profile itself to prevent recursive self-spawn loops
- default repo support is valuable for fast operator UX, but repo detection should still prefer explicit repo context when available

Recommended config shape:

```yaml
super_coder_autoroute:
  enabled: true
  default_repo: /root/projects/video-agents-factory
  run_script: /root/.hermes/profiles/coder/scripts/run_super_coder.py
  status_script: /root/.hermes/profiles/coder/scripts/super_coder_status.py
  timeout: 2400
  action_keywords: [fix, corrige, debug, implement, crée, add, refactor, review]
  context_keywords: [repo, project, code, file, bug, test, api, backend, frontend, auth, worker]
```

This pattern is preferable to relying only on a prompt instruction like “use the coder profile for code tasks”, because the routing happens in core control flow and survives wording drift.

## Verification Commands

Check the profile exists:

```bash
hermes profile show hephaestus
```

Check route resolution locally without making a full API call:

```bash
export HERMES_HOME=/root/.hermes/profiles/hephaestus
python - <<'PY'
from hermes_cli.config import load_config
from hermes_cli.runtime_provider import resolve_runtime_provider
from agent.smart_model_routing import resolve_turn_route
cfg = load_config()
runtime = resolve_runtime_provider(requested=cfg['model']['provider'])
primary = {
    'model': cfg['model']['default'],
    'api_key': runtime.get('api_key'),
    'base_url': runtime.get('base_url'),
    'provider': runtime.get('provider'),
    'api_mode': runtime.get('api_mode'),
    'command': runtime.get('command'),
    'args': list(runtime.get('args') or []),
    'credential_pool': runtime.get('credential_pool'),
}
for prompt in [
    'Debug this traceback in the failing webhook test',
    'Design a cleaner landing page layout for the admin frontend',
    'Fix the backend Cloudflare worker auth webhook race',
]:
    print(resolve_turn_route(prompt, cfg.get('smart_model_routing'), primary))
PY
```

## Kie.ai Provider Integration

The coder profile can use Kie.ai as a cheaper route to Claude models. The provider `kie-claude` is configured in both the main config and the coder profile's `providers:` section with `api_mode: anthropic_messages`.

To use: `hermes -p coder chat -m claude-opus-4-6 --provider kie-claude -q "task"`

As fallback, it's configured in `fallback_providers:` after the primary Nous provider.

## External Routing (smart_model_routing unavailable)

`smart_model_routing` module does NOT exist in current Hermes (2026-05-15 verified). Routes in config.yaml are inert YAML.

**Workaround:** External router at `~/.hermes/scripts/profile_router.py`:
```python
import sys; sys.path.insert(0, '/root/.hermes/scripts')
from profile_router import route_task, build_hermes_command
result = route_task("hephaestus", "fix the webhook stripe bug")
cmd = build_hermes_command("hephaestus", "fix the webhook stripe bug", result)
terminal(cmd, timeout=120)
```

Current hephaestus routes: frontend→kimi-k2.6, backend→claude-opus-4-7 (kie-claude), debug→mimo-v2.5-pro, review→claude-sonnet-4.5 (nous), quick→deepseek-v4-flash.

## Skills Trimmed (2026-05-15)

Coder profile trimmed from 82 to 40 skills. See `hermes-multi-agent-profiles` skill for the full architecture.

## Pitfalls

- **smart_model_routing is inert** — use external profile_router.py script instead.
- **delegate_task caches model at session start** — config changes need /reset.
- Do not switch the sticky active profile to `hephaestus`; W.Alter should remain on `default`.
- Do not put user-facing conversation policy inside `coder`.
- Do not force a model from W.Alter unless you intentionally want to override the coder's internal routing.
- Do not inject the full Hermes conversation into the coding worker — pass a minimal task capsule instead.
- If you change `smart_model_routing` behavior in Hermes core, re-test the `coder` profile route table immediately.
- Do not assume `smart_model_routing` exists just because tests or config reference it. First import-check `agent.smart_model_routing`; if the module is absent, treat the route table as inert and use an external dry-run router/policy until the module or adapter is restored.
- A route being present in `config.yaml` does NOT mean the model is actually usable on the current account tier. Verify live availability.
- If `anthropic/claude-sonnet-4.5` or `anthropic/claude-opus-4.7` are configured on Nous free tier, they may 404 and silently trigger fallback.
- If Kimi debug routing starts failing with 401/exhausted credentials, debug tasks may silently fall back to another provider/model.

## Live Validation Checklist

Use this after changing the coder profile or credentials:

1. Confirm profile metadata:

```bash
hermes profile show coder
```

2. Confirm route resolution logic:

```bash
export HERMES_HOME=/root/.hermes/profiles/coder
python - <<'PY'
from hermes_cli.config import load_config
from hermes_cli.runtime_provider import resolve_runtime_provider
from agent.smart_model_routing import resolve_turn_route
cfg = load_config()
runtime = resolve_runtime_provider(requested=cfg['model']['provider'])
primary = {
    'model': cfg['model']['default'],
    'api_key': runtime.get('api_key'),
    'base_url': runtime.get('base_url'),
    'provider': runtime.get('provider'),
    'api_mode': runtime.get('api_mode'),
    'command': runtime.get('command'),
    'args': list(runtime.get('args') or []),
    'credential_pool': runtime.get('credential_pool'),
}
for prompt in [
    'Debug this traceback in the failing webhook test',
    'Design a cleaner landing page layout for the admin frontend',
    'Review this PR for security issues',
    'Fix the backend Cloudflare worker auth webhook race',
]:
    print(prompt)
    print(resolve_turn_route(prompt, cfg.get('smart_model_routing'), primary))
PY
```

3. Confirm the provider/model is actually available, not just configured:
- run a smoke call with `hermes -p coder chat -Q --source tool -q ...`
- inspect `/root/.hermes/profiles/coder/sessions/session_<id>.json` and check the stored `model`
- inspect `/root/.hermes/profiles/coder/logs/agent.log` for `Fallback activated:` lines

4. If the main Nous Claude route is suspected broken, test it directly against the inference API before trusting the config.

Known live state observed on 2026-05-15:
- `smart_model_routing` module does NOT exist in current Hermes version (`No module named 'agent.smart_model_routing'`). Route table is configured in YAML but completely inert.
- Without routing, coder falls back: tries default model → if fails → fallback_providers chain (openrouter deepseek-v4-pro)
- Both test sessions ran on `deepseek/deepseek-v4-pro` via openrouter, NOT the configured default
- coder profile (now `hephaestus`) verified working: `hermes -p hephaestus chat -Q --source test -q "task"` succeeds in ~30s
- Kie.ai Claude provider works via `hermes -p hephaestus chat -m claude-opus-4-6 --provider kie-claude -q "task"` but takes ~15-20s due to large payload (47 tools + system prompt)
- `delegate_task` model is cached at session start — changing `delegation.model` mid-session has no effect until `/reset`

## Coder Work OS Patterns to Assimilate

To make the `coder` profile feel closer to a strong coding OS, prioritize these patterns over prompt bloat:

1. **Repo-local memory**
   - Load a small per-repo memory file before coding runs.
   - Preferred filenames:
     - `CODER.md`
     - `.hermes/coder-rules.md`
   - Keep only durable coding context there:
     - project architecture
     - test/lint/build commands
     - conventions
     - risky files / migration rules
     - deployment guardrails

     ## Coding Optimization Skills

     Loaded by default in hephaestus sessions, inherited by all super_coder sub-agents:

     - **ponytail** — Minimalist coding lens. Reduces code output by ~54% via YAGNI + reuse + one-liner ladder. Benchmarks: 12 features, Haiku 4.5, -54% code, -20% cost, -27% time. Commands: `/ponytail ultra` (aggressive), `/ponytail off`. **Never load on W.Alter** — conflicts with exhaustive majordome style.
     - **pxpipe-planning-proxy** — Fable 5 planning via PNG-compressed system prompt, DeepSeek V4 execution. For one-shot high-level planning where Anthropic cache doesn't apply.

     Together they form a complementary pair: pxpipe compresses input (planning), Ponytail compresses output (code generation).

2. **Minimal task capsule**
   - Never inject the full Hermes conversation into `coder`.
   - Pass only:
     - task type
     - goal
     - repo/workdir
     - likely files
     - constraints
     - acceptance criteria
     - verification commands
     - return format

3. **Maker / checker split**
   - Separate implementation from verification.
   - Minimum V2 roles:
     - `maker` — reads, edits, implements
     - `checker` — runs tests/review/validation independently
   - Do not trust the implementer alone to declare success.

4. **Workspace isolation**
   - Prefer isolated execution per coding mission:
     - separate Hermes session
     - separate git worktree for risky or multi-file changes
   - Isolation reduces context drift and cross-task contamination.

5. **Hook-style automatic verification**
   - After edits, automatically run the smallest relevant verifier:
     - JS/TS: lint or targeted tests
     - Python: ruff/pytest where available
     - repo-specific checks from repo memory files
   - Dangerous shell actions should stay gated.

6. **Structured operator output**
   - `coder` should always return:
     - Summary
     - Files changed
     - Verification run
     - Risks / follow-ups
   - Prefer machine-friendly structure when the caller will post-process results.

7. **Session continuation / forkability**
   - Preserve compact run artifacts so W.Alter can:
     - continue a task
     - retry with a different model/runtime
     - fork an earlier attempt without reloading the whole conversation

8. **Tight tool scopes**
   - Scope tools to the mission.
   - Example:
     - review → read + bash
     - implementation → read/edit/write/bash
     - UI QA → add browser only when needed

9. **Context-budget discipline**
   - Long coding runs degrade when overloaded.
   - Prefer:
     - fresh session per task
     - repo memory file
     - minimal capsule
     - explicit summaries between phases

10. **Telemetry-driven routing**
   - Track which runtime/model actually succeeded for:
     - debug
     - backend
     - review
     - design
   - Update routing policy from results, not vibes.

## Recommended V2 Shape

Practical target architecture:
- W.Alter = orchestrator
- `coder-maker` = implementation worker
- `coder-checker` = verification worker
- repo-local memory = persistent project context
- isolated session/worktree per mission
- structured result returned to W.Alter

This is usually more valuable than trying to mimic a hidden monolithic prompt.

## Concrete V2 Files

Current concrete work-OS files under the live profile:
- `/root/.hermes/profiles/coder/scripts/run_coder_mission.py`
- `/root/.hermes/profiles/coder/scripts/run_super_coder.py`
- `/root/.hermes/profiles/coder/scripts/init_repo_memory.py`
- `/root/.hermes/profiles/coder/scripts/init_coder_project.py`
- `/root/.hermes/profiles/coder/templates/CODER.md.template`
- `/root/.hermes/profiles/coder/templates/task-capsule.template.md`
- `/root/.hermes/profiles/coder/templates/coder-project.template.json`
- `/root/.hermes/profiles/coder/coder_stack.json`
- `/root/.hermes/profiles/coder/WORK_OS.md`
- `/root/.hermes/profiles/coder/SUPER_STACK.md`

Typical usage:

```bash
python /root/.hermes/profiles/coder/scripts/init_coder_project.py --repo /path/to/repo
python /root/.hermes/profiles/coder/scripts/run_super_coder.py \
  --repo /path/to/repo \
  --task-type backend-debug \
  --goal "Fix the failing webhook race" \
  --constraint "targeted changes only" \
  --acceptance "bug fixed" \
  --verify "pytest tests/test_webhook.py -q"
```

If you are inside the `coder` profile interactively, quick commands are available:

```text
/initcoder --repo /path/to/repo
/supercoder --repo /path/to/repo --task-type backend-debug --goal "Fix the failing webhook race" --verify "pytest tests/test_webhook.py -q"
```

The super mission runner now provides:
- repo-local memory loading from `CODER.md` or `.hermes/coder-rules.md`
- optional repo-local project config from `.hermes/coder-project.json`
- runtime routing across Claude Code and Hermes/Gemini based on task type
- scoped credential bundles for child runtimes
- maker/checker split with separate runtime selection per role
- worktree isolation when the repo is git-backed
- a mission ledger under `/root/.hermes/profiles/coder/ledger/<mission_id>/`
- telemetry under `/root/.hermes/profiles/coder/telemetry/`
- structured run artifacts for resume/audit

## Lean Skill Scope for the Coder Profile

Do NOT leave the `coder` profile with the full global skill catalog enabled.
That creates prompt bloat and weakens routing quality.

Use `skills.disabled` inside `~/.hermes/profiles/coder/config.yaml` to keep the coder profile lean.

Recommended enabled set for the live coder profile:
- `claude-code`
- `cloudflare-pages-deploy`
- `cloudflare-worker-deploy-curl`
- `code-review`
- `multi-model-coder-router`
- `codex`
- `design-frontend-specialization`
- `github-auth`
- `github-code-review`
- `github-pr-workflow`
- `github-repo-management`
- `gsap-frontend`
- `hermes-agent`
- `hyperframes-video-rendering`
- `multi-model-coder-router`
- `multi-model-coder-router`
- `requesting-code-review`
- `scena-auth-client-sync-debug`
- `scena-video-factory`
- `stripe-dynamic-checkout`
- `subagent-driven-development`
- `systematic-debugging`
- `telegram-mini-app`
- `test-driven-development`
- `writing-plans`

Everything else should stay disabled unless the coder profile has a specific recurring need for it.

**Design specialization**: The `design-frontend-specialization` skill provides a systematic workflow for frontend design tasks using Motion (motion.dev) and 21st.dev community components. It should be loaded for any task involving UI, layout, CSS, frontend components, animations, or visual design.

## Task Orchestrator (Autonomous Execution Loop)

For complex multi-step tasks, use `~/.hermes/scripts/task_orchestrator.py` which:
1. Plans subtasks from the task description
2. Routes each subtask to the best model (via keyword matching)
3. Executes via `hermes -p hephaestus chat`
4. Evaluates results (keyword-based — see pitfall below)
5. Escalates on failure (mimo → claude-opus → claude-sonnet)
6. Loops until satisfied (max N iterations)
7. Updates EVOLUTION.md automatically
8. Returns structured JSON report

```bash
python3 ~/.hermes/scripts/task_orchestrator.py \
  --task "Fix webhook Stripe + add retry + tests" \
  --profile hephaestus \
  --max-iterations 3 \
  --json
```

**Pitfall — evaluation is too permissive:** The orchestrator uses keyword matching (`success`, `pass`, `✅`) to judge results. A subtask can be marked PASS even if no actual deliverable was produced (e.g., "add tests" → agent says "done" → PASS, but no tests exist). Always verify actual file content after execution, not just the agent's self-reported status.

## Agent Store (SOUL.md + EVOLUTION.md)

The hephaestus agent has:
- `~/.hermes/agents/hephaestus/SOUL.md` — personality, workflow, critical rules, routing table
- `~/.hermes/agents/hephaestus/EVOLUTION.md` — auto-appended learning log after each task
- `~/.hermes/agents/_library/` — 186 Agency-Agents templates for domain expertise

After each task, use `agent_feedback.py` to log lessons:
```bash
python3 ~/.hermes/scripts/agent_feedback.py feedback \
  --agent hephaestus --task "fix webhook" --type backend \
  --model claude-opus-4-7 --provider kie-claude \
  --result success --time "3min" \
  --lesson "Stripe webhooks need retry on 5xx" \
  --action "Added retry rule to SOUL.md"
```

See `hermes-multi-agent-profiles` skill for full architecture.

## When to Update This Skill

Patch this skill whenever:
- the `hephaestus` profile route table changes materially
- the invocation command changes
- the routing logic moves out of `smart_model_routing`
- the default coding models/providers change
- the `hephaestus` work OS changes materially (repo memory, maker/checker split, hooks, worktree policy, structured outputs)
- the task orchestrator evaluation logic is improved
- new agent store patterns emerge from EVOLUTION.md entries
