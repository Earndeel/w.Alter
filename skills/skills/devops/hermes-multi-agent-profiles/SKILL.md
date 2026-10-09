---
name: hermes-multi-agent-profiles
category: devops
description: "Configure Hermes profiles as specialized workers with external routing, agent store (SOUL.md + EVOLUTION.md), and feedback loops. Greek god naming convention. Orchestrator dispatches to specialist profiles with minimal task capsules."
tags: [hermes, multi-agent, profiles, routing, kanban, orchestration]
related_skills: [coder-profile, research-profile, kanban-orchestrator, kanban-worker]
---

# Hermes Multi-Agent Profile Architecture

## Overview

Configure Hermes profiles as specialized workers that the orchestrator (default profile) dispatches to via Kanban or direct CLI calls. Each profile has its own model, skills, personality (SOUL.md), and self-improvement (EVOLUTION.md). Profiles use **Greek god names**.

## Architecture

```
W.Alter (default profile, orchestrator)
  │  mimo-v2.5-pro
  │  Full Hermes payload: system prompt + all tools + memory + skills
  │  Role: plan, route, review, integrate
  │
  ├──→ hephaestus    (mimo-v2.5-pro default, Greek god of forge)
  │    Task capsule only (~2K tokens, not 50K)
  │    40 skills: code, deploy, github, design
  │    Routing: frontend→kimi-k2.6, backend→claude-opus-4-7 (kie-claude),
  │             debug→mimo-v2.5-pro, review→claude-sonnet-4.5, quick→deepseek-v4-flash
  │
  ├──→ prometheus    (kimi-k2.6 default, Greek god of knowledge)
  │    Task capsule only
  │    Skills: arxiv, blogwatcher, polymarket, web-search
  │    Routing: deep_research→deepseek-v4-pro, web_search→mimo-v2.5-pro, quick→mimo-v2-flash
  │
  ├──→ aphrodite     (à créer, Greek goddess of beauty — design)
  └──→ ares          (à créer, Greek god of war — ops/security)
```

**Naming convention:** Profiles use Greek god names. Rename with `hermes profile rename oldname newname`.

## Key Principles

1. **Orchestrator does NOT execute** — it plans, routes, reviews
2. **Workers receive capsules** — goal + repo + constraints + acceptance, NOT the full conversation
3. **Each profile has its own model routing** — different models for different task types within a profile
4. **Skills are trimmed per profile** — coder gets code skills only, research gets research skills only
5. **Profiles have isolated memory** — each profile's Hindsight sessions are separate

## External Profile Router

**Critical:** `smart_model_routing` module does NOT exist in current Hermes (as of 2026-05-15). The config key exists but `from agent.smart_model_routing import resolve_turn_route` raises `ModuleNotFoundError`.

**Solution:** External Python router at `~/.hermes/scripts/profile_router.py` that:
- Reads `smart_model_routing.routes` from profile config.yaml
- Matches task text against keyword rules (any_keywords + exclude_keywords)
- Returns the best model + provider for the task
- Generates the full hermes CLI command

### Router Usage

```python
# From W.Alter orchestrator
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from profile_router import route_task, build_hermes_command

# Route a task
result = route_task("hephaestus", "fix le webhook stripe bug")
# → {"model": "claude-opus-4-7", "provider": "kie-claude", "route": "backend", "score": 2}

# Build command
cmd = build_hermes_command("hephaestus", "fix le webhook stripe bug", result)
# → hermes -p hephaestus chat -Q --source task --skills "" -m claude-opus-4-7 --provider kie-claude -q 'fix le webhook stripe bug'

# Execute via terminal
terminal(cmd, timeout=120)
```

### CLI Usage

```bash
# Get routing decision
python3 ~/.hermes/scripts/profile_router.py --profile hephaestus --task "fix the webhook stripe bug"

# Get hermes command
python3 ~/.hermes/scripts/profile_router.py --profile hephaestus --task "fix the webhook" --cmd

# Get JSON output
python3 ~/.hermes/scripts/profile_router.py --profile hephaestus --task "refais le hero" --json
```

## Configuring a Profile

### 1. Model + Provider

```yaml
# ~/.hermes/profiles/<name>/config.yaml
model:
  default: mimo-v2.5-pro    # cheap default for general tasks
  provider: xiaomi
```

### 2. Smart Model Routing (keywords-based)

```yaml
smart_model_routing:
  enabled: true
  routes:
  - name: frontend
    provider: opencode-go
    model: kimi-k2.6
    match:
      any_keywords: [ui, frontend, css, tailwind, react, component]
      exclude_keywords: [backend, api, database]
  - name: backend
    provider: kie-claude
    model: claude-opus-4-7
    match:
      any_keywords: [backend, api, database, auth, stripe, webhook]
  - name: quick
    provider: openrouter
    model: deepseek/deepseek-v4-flash
    match:
      any_keywords: [quick, rename, typo, format]
```

### 3. Skills Trimming

**Do NOT leave profiles with the full skill catalog.** It creates prompt bloat and wastes context.

```yaml
skills:
  disabled:
    - skill-to-disable-1
    - skill-to-disable-2
    # ... list ALL skills to disable
    # Only skills NOT in this list will be active
```

**Approach:** Use a whitelist. List all installed skills, identify the ~30-40 relevant ones, disable everything else.

### 4. Providers (Third-Party)

Add third-party providers at the profile level:

```yaml
providers:
  kie-claude:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages
    key_env: KIE_API_KEY
    default_model: claude-opus-4-6
    models: [claude-opus-4-6, claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5]
```

## Kie.ai as Provider (Not Profile)

**Do NOT create a profile for Kie.ai.** It's a provider that gives access to Claude models at different pricing. Configure it in `providers:` section of profiles that need Claude access.

```yaml
# In config.yaml (global) or profile config.yaml (per-profile)
providers:
  kie-claude:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages
    key_env: KIE_API_KEY
    default_model: claude-opus-4-6
    models:
    - claude-opus-4-6
    - claude-sonnet-4-6
    - claude-opus-4-7
    - claude-haiku-4-5
```

Auth: `KIE_API_KEY` in `.env` and vault. Key uses Bearer auth (not x-api-key).

## Delegation vs Cron vs Kanban

| Mechanism | Model source | Scope |
|-----------|-------------|-------|
| `delegate_task` tool | `delegation.model` in config.yaml | Quick inline subtasks (minutes) |
| Cron jobs | Session default model (`model.default`) | Scheduled tasks |
| Kanban workers | Profile's own model | Long-running, durable tasks |

**Pitfall:** `delegation.model` does NOT affect cron jobs. Cron jobs use `model.default`. Changing `delegation.model` has zero impact on scheduled tasks.

**Pitfall:** `delegate_task` caches the model at session start. Changing `delegation.model` in config.yaml requires a `/reset` (new session) to take effect.

## Task Capsule Format

Always pass minimal context to workers:

```
TASK TYPE: backend-debug
GOAL: Fix the webhook Stripe race condition in checkout flow
REPO: /root/scena
CONSTRAINTS:
- targeted changes only
- no refactor unless required
ACCEPTANCE:
- failing test reproduced
- fix implemented
- tests pass
VERIFY:
- pytest tests/test_webhook.py -q
```

**Never** pass the full Hermes conversation to a worker. The worker has its own system prompt, tools, and skills.

## Creating New Profiles

```bash
# Clone from default
hermes profile create design --clone

# Switch and configure
hermes profile use design
hermes model  # pick the right model

# Edit config
hermes config edit  # set routing, skills, providers

# Switch back to default
hermes profile use default
```

## Agent Store (Organic Agents with Self-Improvement)

```
~/.hermes/agents/
├── _library/              ← 186 Agency-Agents templates (16 divisions)
│   ├── engineering/       ← 29 agents (backend, frontend, SRE, security...)
│   ├── design/            ← 8 agents (UI, UX, brand...)
│   ├── marketing/         ← 30 agents
│   ├── specialized/       ← 41 agents (legal, compliance, HR...)
│   └── ... (13 more divisions)
├── hephaestus/            ← SOUL.md + EVOLUTION.md
├── prometheus/            ← SOUL.md + EVOLUTION.md
├── aphrodite/             ← (à créer)
└── ares/                  ← (à créer)
```

**SOUL.md** = personality + workflow + critical rules + model routing table
**EVOLUTION.md** = auto-appended learning log after each task

The library is a **knowledge reservoir** — profiles consult .md files for domain expertise when needed.

### SOUL.md Structure

```markdown
# Agent Name — Role

## Identity
Who I am, how I communicate, my philosophy.

## Workflow
1. RECEIVE task capsule
2. READ existing code/context
3. PLAN in 3 lines
4. IMPLEMENT
5. VERIFY
6. REPORT

## Model Routing
| Task Type | Model | Provider | Why |
|-----------|-------|----------|-----|
| backend   | claude-opus-4-7 | kie-claude | Complex logic |

## Critical Rules
- NEVER commit without verification
- ALWAYS handle edge cases

## Self-Improvement
After each task, update EVOLUTION.md with lessons learned.
```

### Feedback Loop

After each task, update the agent's EVOLUTION.md:

```bash
python3 ~/.hermes/scripts/agent_feedback.py feedback \
  --agent hephaestus \
  --task "fix webhook stripe" \
  --type backend \
  --model claude-opus-4-7 \
  --provider kie-claude \
  --result success \
  --time "3min" \
  --lesson "Stripe webhooks need retry on 5xx" \
  --action "Added retry rule to SOUL.md"
```

If the action contains permanent keywords (always, never, rule, workflow change), it auto-appends to SOUL.md.

### Importing Agency-Agents Templates

```bash
# Clone and extract relevant agents
git clone --depth 1 https://github.com/msitarzewski/agency-agents.git /tmp/agency-agents
cp /tmp/agency-agents/engineering/engineering-senior-developer.md ~/.hermes/agents/_library/
# ... pick the agents relevant to your profiles
```

Then fuse the template's personality with your Hermes config into a SOUL.md.

## Task Orchestrator (Autonomous Execution Loop)

When a profile receives a complex task, it should **not** execute linearly. Instead, use the orchestrator at `~/.hermes/scripts/task_orchestrator.py` which implements:

```
PLAN → DISPATCH → EVALUATE → ITERATE → REPORT
```

### How it works

1. **Plan**: Split task into subtasks (on `+`, `et`, `then`, numbered lists)
2. **Route**: Each subtask → best model via keyword matching
3. **Execute**: Each subtask via `hermes -p <profile> chat -m <model> --provider <provider> -q <task>`
4. **Evaluate**: Check output for success/failure signals
5. **Escalate**: If fail → retry with better model (chain: mimo → claude-opus → claude-sonnet)
6. **Loop**: Max N iterations until all subtasks pass
7. **Evolution**: Update EVOLUTION.md with results
8. **Report**: Return structured JSON to caller

### Usage

```bash
# From W.Alter or any orchestrator
python3 ~/.hermes/scripts/task_orchestrator.py \
  --task "Fix webhook Stripe + add retry + add tests" \
  --profile hephaestus \
  --max-iterations 3 \
  --json
```

### Escalation Chain

```
Attempt 1: default model (mimo-v2.5-pro)
  ↓ fail
Attempt 2: specialized model (claude-opus-4-7 or kimi-k2.6)
  ↓ fail
Attempt 3: review model (claude-sonnet-4.5)
  ↓ fail
Report to W.Alter: "blocked, needs human input"
```

## Credential Pool Sync

When creating a new profile, its `auth.json` starts empty. Credentials from the main profile must be synced:

```python
import json
main = json.load(open('/root/.hermes/auth.json'))
profile_auth = {'credential_pool': {}, 'version': main.get('version', 1)}

for provider, creds in main.get('credential_pool', {}).items():
    if creds and len(creds) > 0:
        profile_auth['credential_pool'][provider] = creds

json.dump(profile_auth, open('/root/.hermes/profiles/<name>/auth.json', 'w'), indent=2)
```

**Pitfall:** Each profile has its own `auth.json`. If prometheus has `opencode-go: 0 keys`, kimi-k2.6 will return 401. Always sync credentials after creating a profile.

## SOUL.md Injection into Orchestrator

The task orchestrator must inject the agent's SOUL.md into the prompt, otherwise the agent loses its personality and rules:

```python
soul_path = AGENTS_DIR / profile / "SOUL.md"
soul_context = ""
if soul_path.exists():
    soul_context = f"[AGENT PERSONALITY]\n{soul_path.read_text()[:2000]}\n\n"

prompt = f"{soul_context}[TASK]\n{desc}"
```

**Why 2000 chars max:** The SOUL.md can be 6-7KB. Truncating avoids token overflow while preserving the most critical identity/rules sections.

## Evaluation Fix: File Content Verification

The orchestrator's `evaluate_result()` must verify **actual file content**, not just output keywords. The old approach marked tasks as PASS when the output contained "success" or "pass" even if no files were produced.

**Fixed approach:**
1. Extract file paths from output using regex patterns
2. Check if files exist and have content
3. If task mentions "test", verify files contain `def test_` / `assert` / `pytest`
4. If files are empty or missing → verdict=fail regardless of output signals

```python
# In evaluate_result():
if "test" in subtask_desc.lower():
    has_test_evidence = bool(re.search(r'(def test_|assert |pytest|unittest)', output_lower))
    has_file_tests = verify_files_for_tests(output)
    if not has_test_evidence and not has_file_tests:
        return {"verdict": "fail", "reason": "no test evidence in output or files"}
```

## Pitfalls

- **smart_model_routing is inert** — module doesn't exist in current Hermes. Use external router script.
- **delegate_task uses cached config** — changes require session restart (`/reset`). Changing `delegation.model` or `delegation.provider` in config.yaml has zero effect until the session restarts.
- **delegation.provider must match an existing provider** — if `delegation.provider` is set to a name that doesn't exist in `providers`, the child agent gets `Invalid API Key` because no credentials are found. Verify with: `grep -A6 '^delegation:' ~/.hermes/config.yaml` and ensure the provider exists. Fix: change to the correct provider name (e.g., `xiaomi` → `gitlawb`) and restart session.
- **Full skill catalog on profiles = bloat** — trim to ~30-40 relevant skills per profile.
- **Kie.ai uses Bearer auth, not x-api-key** — curl test confirms this.
- **Profile auth.json is separate** — credentials must be synced from main auth.json after profile creation.
- **Keyword substring matching causes false positives** — 'ui' matches 'fonction'. Use whole-word matching via `re.findall(r'\w+', text)` in the router.
- **Evaluation keyword-only is too permissive** — verify actual file content, not just "pass"/"success" in output.
- **Orchestrator timeout** — each subtask takes 50-90s via hermes CLI. A 4-subtask task needs 300s+ timeout. Set `--max-iterations 1` for quick tests.
- **SOUL.md not injected** — if orchestrator doesn't inject SOUL.md, agent loses personality and rules. Always inject first 2000 chars.
