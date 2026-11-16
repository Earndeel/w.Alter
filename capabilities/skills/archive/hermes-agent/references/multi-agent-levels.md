# Hermes Multi-Agent Levels — Subagents vs Profiles vs Workers

When users ask "what's the difference between subagents, profiles, and workers", give this mental model:

## 3 Levels

```
┌─────────────────────────────────────┐
│  User conversation (default profile) │
│  = the main agent the user talks to  │
└──────────┬──────────────────────────┘
           │
  ┌────────┴────────┐
  ▼                 ▼
┌──────────┐  ┌─────────────────┐
│ Subagent │  │ Profile (worker) │
│(delegate)│  │ (hermes -p name) │
└──────────┘  └─────────────────┘
```

### 1. Subagent (`delegate_task`) — quick, disposable
- Spawns inside the current session, separate conversation context
- Gets a goal, works, returns a summary
- **Duration**: seconds to minutes
- **Model**: `delegation.model` in config.yaml
- **Use**: "go fetch this", "analyze this file", "fix this bug"
- No memory, no persistence, dies after completion

### 2. Profile (`hermes -p coder`) — permanent isolated agent
- Full Hermes instance with own config, model, skills, memory
- Runs in separate process (often via tmux or gateway)
- **Duration**: hours/days
- **Model**: that profile's own `config.yaml → model.default`
- **Use**: long autonomous tasks, different model needed (e.g. Claude for code)

### 3. Worker (Kanban) — profile + SQLite orchestration
- A profile that receives tasks from the Kanban dispatcher
- Dispatcher ticks every 60s, spawns `hermes -p <profile> chat -q "work kanban task <id>"`
- **Advantage**: crash recovery, audit trail, dependency graphs
- **Overhead**: SQLite, 60s latency, not in TUI

## Model Scope (critical pitfall)

| Component | Model source |
|-----------|-------------|
| `delegate_task` (inline) | `delegation.model` in config.yaml |
| Cron jobs | Session `model.default` (NOT delegation.model) |
| Kanban workers | Worker profile's own `model.default` |
| Spawned `hermes -p <name>` | That profile's config |

**Common mistake**: changing `delegation.model` thinking it affects cron jobs or Kanban. It does not.

## Decision tree

- Quick parallel subtask (minutes) → `delegate_task`
- Need different model (Claude for code) → profile
- Long-running, must survive crash → Kanban
- Scheduled recurring → cron job
