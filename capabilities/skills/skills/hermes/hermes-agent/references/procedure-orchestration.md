## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### Delegation Model vs Cron Jobs — CRITICAL DISTINCTION

**`delegation.model` in config.yaml ONLY affects `delegate_task` subagents.** It does NOT affect:
- **Cron jobs** — they use the session's default model (or `model` if set on the job)
- **Kanban workers** — they use the model configured in the **worker's profile** config
- **Interactive sessions** — they use the profile's `model.default`

Common mistake: changing `delegation.model` thinking it will reduce cron job costs. It won't. Cron jobs always run with `model=default` unless overridden per-job.

To control costs per component:
| Component | Config location |
|-----------|----------------|
| Cron jobs | Job-level `model` field, or profile's `model.default` |
| delegate_task | `delegation.model` in config.yaml |
| Kanban workers | Target profile's `model.default` |
| Main session | Profile's `model.default` |

### Multi-Profile Architecture

Hermes profiles can act as **specialized workers** in a multi-agent team. Each profile has:
- Its own model and provider (`config.yaml`)
- Its own `smart_model_routing` (routes different task types to different models)
- Its own skills (enabled/disabled per profile)
- Its own memory (sessions, hindsight bank)
- Its own auth credentials

**Orchestrator pattern:** `default` profile = user-facing orchestrator (routes, plans, reviews). Worker profiles (`coder`, `research`, etc.) receive **minimal task capsules** — not the full Hermes payload.

**Task capsule principle:** When spawning a worker, send ONLY what it needs:
```
TASK TYPE: backend-debug
GOAL: Fix the webhook race in checkout
REPO: /root/scena
CONSTRAINTS: targeted changes only
VERIFY: pytest tests/test_webhook.py -q
```
This keeps token cost low (~2K vs ~50K for full payload), especially important when using expensive models like Claude via Kie.ai.

**Kanban init required:** Run `hermes kanban init` to create the SQLite board. The dispatcher runs inside the gateway process and ticks every 60s. Without init, `kanban_create` will fail silently.

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry

---

### Free Model Fallback Pattern

When using free-tier models (Kimi K2.6 :free, DeepSeek V4 Flash :free, etc.) for delegation or main model, configure a fallback chain so rate-limited requests recover automatically.

**Config recipe:**
```yaml
delegation:
  model: moonshotai/kimi-k2.6:free    # Free tier
  provider: openrouter
  api_key: ''                          # Uses OPENROUTER_API_KEY from .env
fallback_providers:
  - model: xiaomi/mimo-v2.5-pro       # Paid, reliable, no rate limit
    provider: gitlawb
  - model: deepseek/deepseek-v4-pro   # Second fallback
    provider: openrouter
agent:
  api_max_retries: 7                   # More retries for transient 429s
```

**How Hermes handles 429s (the retry pipeline):**
1. API call returns 429 → `classify_api_error()` → `FailoverReason.rate_limit`
2. `jittered_backoff(attempt, base_delay=5s, max_delay=120s)` — decorrelated jitter prevents thundering herd
3. Retry up to `api_max_retries` times
4. If retries exhausted → `_try_activate_fallback()` → switches to next `fallback_providers` entry
5. Fallback model handles the request transparently

**Key distinction:** Retry/backoff handles TEMPORARY rate limits (concurrent request throttling, ~20 req/min). It does NOT help with DAILY QUOTA caps (~50 req/day without credits on OpenRouter free tiers). For daily quotas, the fallback is the real safety net.

**Pitfall:** Changing `delegation.model` requires `/reset` (new session) to take effect — the current session caches the old model. Verify with `delegate_task` after reset.

**OpenRouter free tier limits (as of May 2026):**
- ~20 requests per minute (temporary, retryable)
- ~50 requests per day without credits (hard cap, falls back needed)
- ~1000 requests per day with $10 credit added
- Rate limits are UPSTREAM (Moonshot/DeepSeek), not OpenRouter — multiple API keys won't help

## Multi-Agent & Kanban (v0.12.0+)

Hermes v0.12.0 introduced a built-in Kanban system for durable multi-agent workflows. It replaces ad-hoc `delegate_task` chains with a SQLite-backed task board, automatic dispatcher, and profile-based worker assignment.

Load the dedicated skills for deep documentation:
- **`kanban-orchestrator`** — decomposition playbook, specialist roster, anti-temptation rules for routing work
- **`kanban-worker`** — lifecycle, handoff patterns, retry diagnostics, pitfalls

### Quick Kanban Setup

```bash
hermes kanban init
hermes kanban create "Research pricing" --assignee research --body "..."
hermes kanban create "Draft memo" --assignee default --parent <id>
```

### Key Concepts

| Concept | What it means |
|---------|---------------|
| **Task** | SQLite row with title, body, assignee profile, status (`todo` → `ready` → `claimed` → `done`) |
| **Parents** | `parents=[...]` gates promotion — children stay `todo` until all parents reach `done` |
| **Dispatcher** | Gateway subprocess ticking every 60s: reclaims stale claims, promotes ready tasks, spawns `hermes -p <assignee> chat -q "work kanban task <id>"` |
| **Workspace** | `scratch` (tmp, GC'd), `dir:<path>` (persistent shared), or `worktree` (git worktree) |
| **Runs** | Each execution attempt is a run. History preserved across retries. Crash detection via `/proc/<pid>/status` |
| **Block / Unblock** | Worker calls `kanban_block(reason=...)` to pause for human input. Operator `/unblock` resumes. |

### Integration with Existing Profiles

If you already use profiles (e.g., `coder`, `research`, `ops`), Kanban assigns tasks to profiles directly. The dispatcher discovers profiles under `HERMES_HOME`, so multi-profile setups work without extra configuration.

Typical workflow:
1. `default` (or a dedicated `planner` profile) creates the task graph
2. `research` and `coder` work on parallel tasks
3. `reviewer` gates before completion
4. `ops` deploys the approved artifact

### Curator (Background Skill Maintenance)

`hermes curator` runs on the gateway cron ticker (default 7-day cycle) to grade, consolidate, and prune your skill library. It writes reports to `logs/curator/run.json` + `REPORT.md` and archives low-value skills.

```bash
hermes config set auxiliary.curator.enabled true
hermes config set auxiliary.curator.model "gemini/gemini-3.1-flash-lite"
hermes curator status       # rank skills by usage
```

### When to Use Kanban vs delegate_task

| | `delegate_task` | Kanban |
|-|-----------------|--------|
| Duration | Minutes | Hours/days |
| Durability | Lost on crash | Survives restart |
| Human loop | No built-in | Block/unblock native |
| Audit trail | None | SQLite forever |
| Parallelism | Sequential | Fan-out/fan-in via parents |

Use `delegate_task` for quick reasoning subtasks inside one session. Use Kanban when work spans profiles, needs review gates, or must survive crashes.

---

## Multi-Agent Model Routing — Pitfalls

**`delegation.model` scope is narrow.** It ONLY applies to `delegate_task` subagents spawned within a session. It does NOT affect:
- **Cron jobs** — they use the job's own `model` field, or fall back to the session's main `model.default` (NOT `delegation.model`). Check with: session metadata `model=default`.
- **Kanban workers** — they use the assigned profile's own `model.default`, not the orchestrator's delegation config.
- **Spawned Hermes processes** (`hermes -p <profile> chat`) — they use the target profile's config.

Common mistake: changing `delegation.model` thinking it will reduce cron job costs. It won't. Cron jobs always run on the main model or their own override.

**Profiles vs delegation vs Kanban — distinct systems:**

| System | What it is | Model used | Duration | Survives crash |
|--------|-----------|------------|----------|----------------|
| `delegate_task` | In-process subagent | `delegation.model` | Minutes | No |
| Kanban | SQLite task board + dispatcher | Worker profile's model | Hours/days | Yes |
| Profile spawn | `hermes -p <name> chat` | That profile's model | Hours | No |
| Cron job | Scheduled session | Job's model or main model | Minutes | N/A |

**Custom providers with `api_mode: anthropic_messages`**: If the provider URL doesn't match auto-detection patterns (must end with `/anthropic`, be `api.kimi.com/coding`, etc.), the `api_mode` field in the `providers:` section of config.yaml is essential. Without it, the provider falls back to `chat_completions` which will fail for Anthropic-native APIs. See `references/custom-anthropic-providers.md`.

### Delegation vs Cron vs Kanban — What Uses What Model

A common misconception: changing `delegation.model` affects cron jobs. **It does not.**

| Mechanism | Which model? | Config location |
|-----------|-------------|-----------------|
| `delegate_task` (inline tool) | `delegation.model` | `config.yaml → delegation` |
| Cron jobs (agent-based) | Session default model | `config.yaml → model.default` |
| Cron jobs (with `model` override) | Job-specific model | `cronjob create --model` |
| Kanban workers | Worker profile's model | `profiles/<name>/config.yaml → model.default` |
| Kanban dispatcher spawn | Profile model | `hermes -p <profile> chat -q ...` |

The `delegation.model` setting ONLY applies to `delegate_task` calls made by the agent during a conversation. Cron jobs always create fresh sessions using the session's default model (or the job's override). Kanban workers use whatever model their assigned profile has.

To change the model cron jobs use: change `model.default` in the main config, or set `--model` per cron job.
To change the model Kanban workers use: change `model.default` in the worker profile's config.

### Claude via Kie.ai — Tool, Not Orchestrator

Kie.ai provides Claude models (opus-4-6, opus-4-7, sonnet-4-6, haiku-4-5) via `api_mode: anthropic_messages`. It is configured as a provider (`kie-claude`) in both the main config and the coder profile.

**Critical**: Do NOT use Claude via Kie.ai as the main orchestrator model. The full Hermes payload (system prompt + 47 tools + memory + skills) is ~50K tokens, costing ~$0.50 per call. Use it as a **tool** for specific high-value tasks via the coder profile, which sends only a minimal task capsule (~2K tokens, ~$0.02 per task).

- Orchestrator: mimo-v2.5-pro (cheap, handles full payload)
- Coding tasks: Claude via Kie.ai via coder profile (minimal capsule)
- Quick tasks: deepseek-v4-flash (fast, cheap)

