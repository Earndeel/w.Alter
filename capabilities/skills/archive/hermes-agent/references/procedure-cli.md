## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Interactive chat (default)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard
hermes setup

# Change model/provider
hermes model

# Check health
hermes doctor
```

---

## CLI Reference

### Global Flags

```
hermes [flags] [command]

  --version, -V             Show version
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --pass-session-id         Include session ID in system prompt
```

No subcommand defaults to `chat`.

### Chat

```
hermes chat [flags]
  -q, --query TEXT          Single query, non-interactive
  -m, --model MODEL         Model (e.g. anthropic/claude-sonnet-4)
  -t, --toolsets LIST       Comma-separated toolsets
  --provider PROVIDER       Force provider (openrouter, anthropic, nous, etc.)
  -v, --verbose             Verbose output
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --source TAG              Session source tag (default: cli)
```

### Configuration

```
hermes setup [section]      Interactive wizard (model|terminal|gateway|tools|agent)
hermes model                Interactive model/provider picker
hermes config               View current config
hermes config edit          Open config.yaml in $EDITOR
hermes config set KEY VAL   Set a config value
hermes config path          Print config.yaml path
hermes config env-path      Print .env path
hermes config check         Check for missing/outdated config
hermes config migrate       Update config with new options
hermes auth add             Add a credential to the provider pool (OAuth or API key)
hermes auth list [PROVIDER] List pooled credentials
hermes auth remove P INDEX  Remove by provider + index
hermes auth reset PROVIDER  Clear exhaustion status
hermes logout               Clear stored auth
hermes doctor [--fix]       Check dependencies and config
hermes status [--all]       Show component status
```

### Tools & Skills

```
hermes tools                Interactive tool enable/disable (curses UI)
hermes tools list           Show all tools and status
hermes tools enable NAME    Enable a toolset
hermes tools disable NAME   Disable a toolset

hermes skills list          List installed skills
hermes skills search QUERY  Search the skills hub
hermes skills install ID    Install a skill
hermes skills inspect ID    Preview without installing
hermes skills config        Enable/disable skills per platform
hermes skills check         Check for updates
hermes skills update        Update outdated skills
hermes skills uninstall N   Remove a hub skill
hermes skills publish PATH  Publish to registry
hermes skills browse        Browse all available skills
hermes skills tap add REPO  Add a GitHub repo as skill source
```

### MCP Servers

```
hermes mcp serve            Run Hermes as an MCP server
hermes mcp add NAME         Add an MCP server (--url or --command)
hermes mcp remove NAME      Remove an MCP server
hermes mcp list             List configured servers
hermes mcp test NAME        Test connection
hermes mcp configure NAME   Toggle tool selection
```

### Gateway (Messaging Platforms)

```
hermes gateway run          Start gateway foreground
hermes gateway install      Install as background service
hermes gateway start/stop   Control the service
hermes gateway restart      Restart the service
hermes gateway status       Check status
hermes gateway setup        Configure platforms
```

Supported platforms: Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeCom, API Server, Webhooks, Open WebUI.

Platform docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/

#### Inbound media for generation workflows

When the user wants to send media for Kie.ai/Fal.ai/image/video generation, see `references/media-inputs-for-generation.md`. Short version: Telegram/gateway attachments are cached as local paths under `~/.hermes/cache/...`; external generation APIs usually require public URLs, so upload/proxy the cached file first (Fal upload, Kie upload, or R2/CDN) before placing it in fields like `first_frame_url`, `reference_image_urls`, or Fal `image_urls`.

### Delegation vs Cron Jobs vs Kanban

| Mechanism | Model source | When to use |
|-----------|-------------|-------------|
| `delegate_task` | `delegation.model` in config.yaml | Quick parallel subtasks (minutes) |
| Cron jobs | Session `model.default` (NOT delegation.model) | Scheduled recurring tasks |
| Kanban | Profile's own `model.default` | Long-running, durable, multi-profile work |

**Critical:** `delegation.model` does NOT affect cron jobs. Cron jobs always use the main `model.default`. Changing `delegation.model` only impacts `delegate_task` calls, and requires a `/reset` to take effect in the current session.

For full multi-agent architecture including the autonomous execution loop (plan → dispatch → evaluate → iterate → report), SOUL.md/EVOLUTION.md agent patterns, and the external profile router, see `hermes-multi-agent-profiles` skill.

### Sessions

```
hermes sessions list        List recent sessions
hermes sessions browse      Interactive picker
hermes sessions export OUT  Export to JSONL
hermes sessions rename ID T Rename a session
hermes sessions delete ID   Delete a session
hermes sessions prune       Clean up old sessions (--older-than N days)
hermes sessions stats       Session store statistics
```

### Cron Jobs

```
hermes cron list            List jobs (--all for disabled)
hermes cron create SCHED    Create: '30m', 'every 2h', '0 9 * * *'
hermes cron edit ID         Edit schedule, prompt, delivery
hermes cron pause/resume ID Control job state
hermes cron run ID          Trigger on next tick
hermes cron remove ID       Delete a job
hermes cron status          Scheduler status
```

### Webhooks

```
hermes webhook subscribe N  Create route at /webhooks/<name>
hermes webhook list         List subscriptions
hermes webhook remove NAME  Remove a subscription
hermes webhook test NAME    Send a test POST
```

### Profiles

```
hermes profile list         List all profiles
hermes profile create NAME  Create (--clone, --clone-all, --clone-from)
hermes profile use NAME     Set sticky default
hermes profile delete NAME  Delete a profile
hermes profile show NAME    Show details
hermes profile alias NAME   Manage wrapper scripts
hermes profile rename A B   Rename a profile
hermes profile export NAME  Export to tar.gz
hermes profile import FILE  Import from archive
```

### Multiple OAuth Accounts for the Same Provider

Hermes supports multiple concurrent OAuth accounts for the same provider via **credential pools** + **profiles**.

**Approach 1 — Isolated profiles (recommended for separate contexts)**

```bash
# Create a second profile cloned from default
hermes profile create openai2 --clone

# Switch to it and run auth (stored in ~/.hermes/profiles/openai2/auth.json)
hermes profile use openai2
hermes auth add openai-codex --type oauth

# Switch back to main profile anytime
hermes profile use default
```

Each profile has its own `auth.json`, `config.yaml`, sessions, skills, and memory. Use this when the accounts serve different purposes (e.g., one for personal coding, one for SaaS billing).

**Approach 2 — Credential pool within a single profile (rotation / fallback)**

```bash
# Add a second credential to the same provider pool
hermes auth add openai-codex --type oauth
hermes auth list openai-codex   # shows [0] first-account, [1] second-account
```

Hermes rotates through the pool based on `credential_pool_strategies`:

```yaml
credential_pool_strategies:
  openai-codex: fill_first    # use [0] until exhausted, then [1]
  # alternatives: round_robin, weighted
```

Use this when you want automatic fallback (e.g., primary account hits rate limit → auto-switch to secondary).

