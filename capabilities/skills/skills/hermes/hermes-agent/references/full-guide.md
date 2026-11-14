---
name: hermes-agent
description: Complete guide to using and extending Hermes Agent — CLI usage, setup, configuration, spawning additional agents, gateway platforms, skills, voice, tools, profiles, and a concise contributor reference. Load this skill when helping users configure Hermes, troubleshoot issues, spawn agent instances, or make code contributions.
version: 2.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, messaging platforms, and IDEs. It belongs to the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, DeepSeek, local models, and 15+ others) and runs on Linux, macOS, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills. When it solves a complex problem, discovers a workflow, or gets corrected, it can persist that knowledge as a skill document that loads into future sessions. Skills accumulate over time, making the agent better at your specific tasks and environment.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends (built-in, Honcho, Mem0, and more) let you choose how memory works.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Email, and 8+ other platforms with full tool access, not just chat.
- **Provider-agnostic** — swap models and providers mid-workflow without changing anything else. Credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, and the full Python ecosystem.
- **Kanban multi-agent (v0.12.0+)** — built-in durable task board with dispatcher, worker spawning, dependency graphs, and human-in-the-loop gates. See `kanban-orchestrator` and `kanban-worker` skills.
- **v0.14.0 highlights** (see `references/v014-features.md`): `/handoff` live session transfer, `hermes proxy` OpenAI-compatible local proxy, `x_search` native X search via Grok, 180x faster browser CDP (⚠️ per-call overhead only — page loads unchanged), cross-session 1h Claude prompt cache, -19s cold start, native clarify buttons on Telegram/Discord, `computer_use` cua-driver for non-Anthropic models, LSP semantic diagnostics on write, LINE + SimpleX Chat (22 platforms total), Microsoft Teams end-to-end, PyPI install, native Windows beta.

People use Hermes for software development, research, system administration, data analysis, content creation, home automation, and anything else that benefits from an AI agent with persistent context and full system access.

**This skill helps you work with Hermes Agent effectively** — setting it up, configuring features, spawning additional agent instances, troubleshooting issues, finding the right commands and settings, and understanding how the system works when you need to extend or contribute to it.

For a quick mental model of subagents vs profiles vs Kanban workers, see [`references/multi-agent-levels.md`](references/multi-agent-levels.md).
For skill bundles and how skills are loaded (two-level: index in system prompt, full content on demand), see [`references/skill-bundles-and-loading.md`](references/skill-bundles-and-loading.md).

**Docs:** https://hermes-agent.nousresearch.com/docs/

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

## Hermes Desktop App (macOS GUI)

Native macOS app for managing Hermes workspaces. Connects via SSH alias to the VPS.

### SSH Config Requirements

The app reads `~/.ssh/config` for connection profiles. Critical:
- **IdentityFile must use absolute path** — `~` expansion fails in GUI context. Use `/Users/<user>/path/to/key` not `~/path/to/key`.
- **Remove `LocalForward` lines** if ports are already in use — SSH exits 255 on bind failure, app treats as connection failure.
- **Test**: `ssh -o BatchMode=yes <alias> "echo ok"` must return exit 0.

### File Permissions (VPS side)

App connects as the SSH user (e.g., `ubuntu`), not root. If Hermes home is `/root/.hermes/`, the SSH user needs traverse+read permissions.

**Symlink**: `ln -sf /root/.hermes /home/ubuntu/.hermes`

**Permission fix**:
```bash
chmod 711 /root /root/.hermes
chmod -R g+rX /root/.hermes/skills /root/.hermes/memories /root/.hermes/sessions /root/.hermes/profiles /root/.hermes/agents /root/.hermes/workspace
chmod g+x /root/.hermes/skills /root/.hermes/memories /root/.hermes/sessions /root/.hermes/profiles /root/.hermes/agents /root/.hermes/workspace
usermod -a -G root ubuntu
```

**⚠️ NEVER use `mount --bind` + `remount,ro`** — this remounts the SOURCE as read-only too, breaking the live system.

### TUI Session Orchestrator (Ctrl+X)

The Ink-based TUI (`hermes --tui`) has a session orchestrator panel (`ActiveSessionSwitcher` component) that opens with **Ctrl+X**. It lists all live sessions with their status (idle/starting/waiting/working) and model, and lets you:
- ↑↓ navigate between sessions
- Enter: switch to session / start new one
- Ctrl+N: create new live session
- Ctrl+D: close session
- Tab: change model before starting
- Ctrl+R: refresh list
- Esc: close panel

Accessible via `/sessions` slash command or the Ctrl+X hotkey. Not visible by default — must be invoked.

---

### Sections
Connections, Overview, Sessions, Workflows, Cron Jobs, Kanban, Files, Usage, Skills, Terminal

---

**Pitfalls**
- `hermes auth add` with `--type oauth` may hang on headless VMs with no browser or blocked egress to `chatgpt.com`. Use the manual device code workaround documented in `references/openai-codex-oauth-device-flow.md`.
- If the VM's IP is blocked by the OAuth provider (403 responses), run the device code flow from your local machine and copy the resulting tokens into the VM's profile `auth.json`.
- Never place a second credential directly in `~/.hermes/auth.json` when you meant `~/.hermes/profiles/<name>/auth.json`. Verify with `hermes auth list` after adding.

### Credential Pools

```
hermes auth add             Interactive credential wizard
hermes auth list [PROVIDER] List pooled credentials
hermes auth remove P INDEX  Remove by provider + index
hermes auth reset PROVIDER  Clear exhaustion status
```

### Multi-Account OAuth for the Same Provider (e.g., two OpenAI Codex accounts)

Use **profiles** to keep multiple OAuth accounts fully isolated without overwriting each other:

```bash
# Create a new profile cloned from the default
hermes profile create openai2 --clone

# Switch to it and add the second OAuth credential
hermes profile use openai2
hermes auth add openai-codex --type oauth

# Switch back to the main profile anytime
hermes profile use default
```

**Why profiles instead of credential pools on the same profile?**
- The `hermes auth add` command **appends** to the pool (it does not overwrite), but OAuth device-code flows can block on some networks (IP-level 403 from `chatgpt.com` on certain cloud providers).
- Profiles give **complete isolation**: separate `auth.json`, `config.yaml`, `.env`, sessions, skills, and memory.
- You can run both simultaneously: `hermes chat` (default profile) and `openai2 chat` (second profile).

**If the device-code flow is blocked (403 from the provider):**
- Run the OAuth flow from your **local machine** (not the cloud VM), then inject the resulting `access_token` + `refresh_token` into the target profile's `auth.json`.
- Alternatively, serve a local HTML page that performs the device-code flow in the browser via JS fetch, then copies the JSON output. See `references/openai-codex-device-flow.md`.

### Credential Pools

```
hermes insights [--days N]  Usage analytics
hermes update               Update to latest version
hermes pairing list/approve/revoke  DM authorization
hermes plugins list/install/remove  Plugin management
hermes honcho setup/status  Honcho memory integration
hermes memory setup/status/off  Memory provider config
hermes completion bash|zsh  Shell completions
hermes acp                  ACP server (IDE integration)
hermes claw migrate         Migrate from OpenClaw
hermes uninstall            Uninstall Hermes
```

---

## Slash Commands (In-Session)

Type these during an interactive chat session.

### Session Control
```
/new (/reset)        Fresh session
/clear               Clear screen + new session (CLI)
/retry               Resend last message
/undo                Remove last exchange
/title [name]        Name the session
/compress            Manually compress context
/stop                Kill background processes
/rollback [N]        Restore filesystem checkpoint
/background <prompt> Run prompt in background
/queue <prompt>      Queue for next turn
/resume [name]       Resume a named session
```

### Configuration
```
/config              Show config (CLI)
/model [name]        Show or change model
/provider            Show provider info
/prompt [text]       View/set system prompt (CLI)
/personality [name]  Set personality
/reasoning [level]   Set reasoning (none|low|medium|high|xhigh|show|hide)
/verbose             Cycle: off → new → all → verbose
/voice [on|off|tts]  Voice mode
/yolo                Toggle approval bypass
/skin [name]         Change theme (CLI)
/statusbar           Toggle status bar (CLI)
```

### Tools & Skills
```
/tools               Manage tools (CLI)
/toolsets            List toolsets (CLI)
/skills              Search/install skills (CLI)
/skill <name>        Load a skill into session
/cron                Manage cron jobs (CLI)
/reload-mcp          Reload MCP servers
/plugins             List plugins (CLI)
```

### Info
```
/help                Show commands
/commands [page]     Browse all commands (gateway)
/usage               Token usage
/insights [days]     Usage analytics
/status              Session info (gateway)
/profile             Active profile info
```

### Exit
```
/quit (/exit, /q)    Exit CLI
```

---

## Key Paths & Config

```
~/.hermes/config.yaml       Main configuration
~/.hermes/.env              API keys and secrets
~/.hermes/skills/           Installed skills
~/.hermes/sessions/         Session transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout.

### Config Sections

Edit with `hermes config edit` or `hermes config set section.key value`.

| Section | Key options |
|---------|-------------|
| `model` | `default`, `provider`, `base_url`, `api_key`, `context_length` |
| `agent` | `max_turns` (90), `tool_use_enforcement` |
| `terminal` | `backend` (local/docker/ssh/modal), `cwd`, `timeout` (180) |
| `compression` | `enabled`, `threshold` (0.50), `target_ratio` (0.20) |
| `display` | `skin`, `tool_progress`, `show_reasoning`, `show_cost`, `bell_on_complete` (emit BEL `\x07` on background task completion — triggers cmux/iTerm2 push notifications) |
| `stt` | `enabled`, `provider` (local/groq/openai) |
| `tts` | `provider` (edge/elevenlabs/openai/kokoro/fish) |
| `memory` | `memory_enabled`, `user_profile_enabled`, `provider` |
| `security` | `tirith_enabled`, `website_blocklist` |
| `delegation` | `model`, `provider`, `max_iterations` (50) |
| `smart_model_routing` | `enabled`, `cheap_model` |
| `image_gen` | `provider` (`fal` / `openai` / `openai-codex`), `model`, `openai-codex` sub-section |
| `checkpoints` | `enabled`, `max_snapshots` (50) |

  - **Model selection for auxiliary tasks** (compression, extraction, consolidation): use the `model-benchmark-comparison` skill. It scrapes artificialanalysis.ai to find the cheapest/fastest model for a given intelligence threshold, and verifies OpenRouter availability.

### Image Generation (`image_gen`)

The `image_generate` tool is provider-pluggable. By default it falls back to **Fal.ai** (`fal`) if no provider is configured.

To use **GPT Image 2 via ChatGPT/Codex OAuth** (no `OPENAI_API_KEY` required):

```yaml
image_gen:
  provider: openai-codex
  # Optional: pick quality tier — low (~15s), medium (~40s, default), high (~2min)
  # model: gpt-image-2-medium
```

Prerequisites:
1. Sign in with `hermes auth add openai-codex --type oauth` (stores OAuth token in the credential pool)
2. The `image_gen` toolset must be enabled (`hermes tools enable image_gen`)

Model selection precedence (first hit wins):
1. `OPENAI_IMAGE_MODEL` env var (`gpt-image-2-low`, `gpt-image-2-medium`, `gpt-image-2-high`)
2. `image_gen.openai-codex.model` in config.yaml
3. `image_gen.model` in config.yaml (when it's a valid tier ID)
4. Default: `gpt-image-2-medium`

Aspect ratios map to OpenAI sizes:
- `landscape` → 1536x1024
- `square` → 1024x1024
- `portrait` → 1024x1536

Generated images are saved to `$HERMES_HOME/cache/images/` and the tool returns the local file path.

**Note:** If `image_generate` fails with `"FAL_KEY environment variable not set"` or `"Authentication is required"`, it means either Fal.ai is the active provider and the key is missing/expired, or the `image_gen.provider` key is missing from config.yaml entirely. Set `provider: openai-codex` to route through Codex auth instead.

Full config reference: https://hermes-agent.nousresearch.com/docs/user-guide/configuration

### Providers

18 providers supported. Set via `hermes model` or `hermes setup`.

| Provider | Auth | Key env var |
|----------|------|-------------|
| OpenRouter | API key | `OPENROUTER_API_KEY` |
| Anthropic | API key | `ANTHROPIC_API_KEY` |
| Nous Portal | OAuth | `hermes auth add nous --type oauth` |
| OpenAI Codex | OAuth | `hermes auth add openai-codex --type oauth` |
| GitHub Copilot | Token | `COPILOT_GITHUB_TOKEN` |
| DeepSeek | API key | `DEEPSEEK_API_KEY` |
| Hugging Face | Token | `HF_TOKEN` |
| Z.AI / GLM | API key | `GLM_API_KEY` |
| MiniMax | API key | `MINIMAX_API_KEY` |
| Kimi / Moonshot | API key | `KIMI_API_KEY` |
| Alibaba / DashScope | API key | `DASHSCOPE_API_KEY` |
| Kilo Code | API key | `KILOCODE_API_KEY` |
| Custom endpoint | Config | `model.base_url` + `model.api_key` in config.yaml |

Plus: AI Gateway, OpenCode Zen, OpenCode Go, MiniMax CN, GitHub Copilot ACP.

- **Kie.ai provider setup** (`references/kie-ai-provider-setup.md`): Claude models via Kie.ai as a provider (not profile). Bearer auth, api_mode requirement, cost awareness.
- **xAI Voice Agent API** (`walter-voice-architecture` skill, `references/xai-voice-agent-api.md`): Real-time S2S voice agent via WebSocket (`wss://api.x.ai/v1/realtime`), $3/hr, with X Search + web_search + code_exec in voice loop. Custom voice cloning available. Hermes supports xAI for TTS (`tts.provider: xai`) and STT (`stt.provider: xai`) but not yet for realtime voice agent.
- **Third-party Anthropic-compatible endpoints** (Kie.ai, Azure, DashScope): see [`references/third-party-anthropic-provider.md`](references/third-party-anthropic-provider.md) for the exact `api_mode` config, API key resolution, and a known streaming workaround.

**Custom data ingestion endpoints** (mobile devices, IoT, external services → JSONL → Hindsight): see [`references/custom-data-ingestion.md`](references/custom-data-ingestion.md) for the full pattern including HTTP server, Cloudflare tunnel exposure, iOS Shortcut, and Hindsight cron pipeline.

- **xAI / SuperGrok** — OAuth or API key | `XAI_API_KEY` | `hermes auth add xai-oauth --type oauth` |

**xAI setup (Premium+ includes SuperGrok):**
```bash
# OAuth (opens browser — must run on a machine with a browser, not headless VPS)
hermes auth add xai-oauth --type oauth

# Or API key (from https://console.x.ai/)
hermes auth add xai --type api-key

# Then enable x_search
hermes tools enable x_search
```

OAuth requires a browser. On headless VPS: run `hermes auth add xai-oauth --no-browser` to get a device code URL, or run the auth from your local machine and copy `auth.json`.

**Key facts (verified May 2026):**
- X Premium+ ($40/mo) includes SuperGrok access
- SuperGrok OAuth works with `x_search` — no API key needed, $0 cost
- x_search model: `grok-4.20-reasoning` (configurable in config.yaml under `x_search:`)
- x.ai/api news confirmed: "Connect Grok to Hermes Agent" and "Use Grok in OpenClaw" both reference X Premium subscription as valid auth

Full provider docs: https://hermes-agent.nousresearch.com/docs/integrations/providers

### Toolsets

Enable/disable via `hermes tools` (interactive) or `hermes tools enable/disable NAME`.

| Toolset | What it provides |
|---------|-----------------|
| `web` | Web search and content extraction |
| `browser` | Browser automation (Browserbase, Camofox, or local Chromium) |
| `terminal` | Shell commands and process management |
| `file` | File read/write/search/patch |
| `code_execution` | Sandboxed Python execution |
| `vision` | Image analysis |
| `image_gen` | AI image generation |
| `tts` | Text-to-speech |
| `skills` | Skill browsing and management |
| `memory` | Persistent cross-session memory |
| `session_search` | Search past conversations |
| `delegation` | Subagent task delegation |
| `cronjob` | Scheduled task management |
| `clarify` | Ask user clarifying questions |
| `moa` | Mixture of Agents (off by default) |
| `x_search` | X/Twitter search via xAI Grok (off by default, needs SuperGrok OAuth or XAI_API_KEY) |
| `homeassistant` | Smart home control (off by default) |

Tool changes take effect on `/reset` (new session). They do NOT apply mid-conversation to preserve prompt caching.

---

## Voice & Transcription

### STT (Voice → Text)

Voice messages from messaging platforms are auto-transcribed.

Provider priority (auto-detected):
1. **Local faster-whisper** — free, no API key: `pip install faster-whisper`
2. **Groq Whisper** — free tier: set `GROQ_API_KEY`
3. **OpenAI Whisper** — paid: set `VOICE_TOOLS_OPENAI_KEY`

Config:
```yaml
stt:
  enabled: true
  provider: groq         # local, groq, openai, gemini
  local:
    model: base          # tiny, base, small, medium, large-v3
  groq:
    model: whisper-large-v3-turbo
  gemini:
    model: gemini-3.1-flash-lite
```

**Recommended STT strategy (tested):**

| Priority | Provider | Model | Speed | Quality |
|----------|----------|-------|-------|---------|
| Primary | Groq | whisper-large-v3-turbo | ~0.9s | Clean, no rich punctuation |
| Fallback | Gemini | gemini-3.1-flash-lite | ~3s | Full punctuation, filler words, tone |

- Groq Whisper: fast, clean output but strips hesitations and rich punctuation
- Gemini 3.1 Flash Lite: slower but more faithful to oral speech (ponctuation, "euh", "tu vois", ton)
- Both are free. Use Groq for real-time, Gemini for archival fidelity.
- Fallback logic: if Groq returns empty/error/timeout → Gemini automatically.

### TTS (Text → Voice)

| Provider | Env var | Free? | Notes |
|----------|---------|-------|-------|
| Gemini TTS | `GEMINI_API_KEY` | Yes | `gemini-3.1-flash-tts-preview`, voice `Algenib` — deep butler voice, monotone, sarcastic. Best fit for W.Alter persona. Config: `tts.provider: gemini` + `tts.gemini.voice: Algenib` + `tts.gemini.system_prompt` for style control. |
| Edge TTS | None | Yes | Good free option. Change voice: `tts.edge.voice` in config.yaml. Available voices: run `edge-tts --list-voices`. |
| ElevenLabs | `ELEVENLABS_API_KEY` | Free tier | High quality, $206/1M chars. Expensive. |
| OpenAI | `VOICE_TOOLS_OPENAI_KEY` | Paid | gpt-4o-mini-tts model |
| Kokoro (local) | None | Free | Local 82M param model, install needed |
| Fish Audio | `FISH_AUDIO_API_KEY` | Free tier | |

**Sending voice on Telegram bot API:** Use `POST https://api.telegram.org/bot<TOKEN>/sendVoice` with multipart/form-data. Fields: `chat_id`, `voice` (OGG file), `caption` (optional text).

**Gemini Live API alternative:** Gemini 3.1 Flash Live and Gemini 2.5 Flash Live provide native bidirectional audio streaming (STT + LLM + TTS in one model) via WebSocket. Pricing: $0.10/1M input tokens, $0.40/1M output tokens — extremely cheap (~$0.003/conversation). SDK: `google-genai`. Replaces the entire STT(Groq)+LLM(OpenRouter)+TTS(Edge) pipeline with a single real-time voice call. Model names: `gemini-3.1-flash-live`, `gemini-2.5-flash-live`.

**Gemini TTS config example (Algenib butler voice):**
```yaml
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Algenib
    system_prompt: 'Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.'
```

Voice commands: `/voice on` (voice-to-voice), `/voice tts` (always voice), `/voice off`.

---

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

### Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `pip install faster-whisper` or set API key
3. Restart gateway: `/restart`

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes auth add <provider> --type oauth` — re-authenticate OAuth providers
3. `hermes auth list <provider>` — verify credentials are present and healthy
4. Check `.env` has the right API key

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** `/restart` reloads gateway config
- **Code changes:** Restart the CLI or gateway process

### Updating Hermes with local modifications
If you run `hermes update` while the git checkout at `~/.hermes/hermes-agent` has uncommitted changes, the update will fail or overwrite your work. Always audit first:

```bash
cd ~/.hermes/hermes-agent
git status --short          # see modified + untracked files
git diff --stat             # scope of changes
```

If you have modifications you want to keep:

```bash
git stash push -m "description"
hermes update
git stash pop               # rebase your changes onto latest main
```

If `stash pop` produces conflicts, resolve them manually before restarting Hermes. Untracked files (e.g., new plugins, scripts) survive `hermes update` untouched, but verify they don't conflict with newly-added upstream files.

Common local modifications to preserve:
- `agent/context_compressor.py` — smart threshold strategies
- `gateway/run.py` — gateway hygiene hooks
- `tools/*.py` — provider-specific robustness patches
- `plugins/` — custom memory backends or integrations

### Gateway issues
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `/skill name` or `hermes -s name`

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

### Gateway watchdog crash loop (systemd)

A `hermes-watchdog.sh` wrapper that loops `hermes gateway run --replace` will crash-loop silently if:
1. Hermes overwrites `gateway.pid` with JSON (`{"pid": N, "kind": "hermes-gateway", ...}`) instead of a bare PID
2. The watchdog reads JSON, `kill -0` fails, it thinks the process is dead, spawns another
3. The new gateway fails with "Telegram bot token already in use" (exit 0 = conflict, not error)
4. `Restart=on-failure` doesn't fire because exit code is 0

**Symptom**: gateway restarting every 10-20 seconds in journalctl, Telegram disconnects every few minutes.

**Fix**: Replace the watchdog wrapper with a direct systemd service:
```ini
# /etc/systemd/system/hermes-agent.service
[Service]
Type=simple
ExecStart=/root/.local/bin/hermes gateway run
Restart=always
RestartSec=15
```
Key: `Restart=always` (not `on-failure`), no `--replace` flag (let systemd own the lifecycle), no watchdog wrapper. The `--replace` flag causes the gateway to exit 0 on conflict, which `Restart=on-failure` ignores.

### Background task notifications not arriving over SSH

When connecting to a remote Hermes instance via SSH, background task notifications (`notify_on_complete`) are delivered to the terminal PTY where the TUI runs. If the SSH connection drops, the PTY dies and notifications are lost — even if you're using a client-side SSH multiplexer like `cmux` (macOS) or SSH `ControlMaster`, which preserve TCP but not terminal state.

**Fix:** Run tmux on the **server side** so Hermes TUI survives SSH disconnects. Full recipe in `references/ssh-tmux-persistence.md` — includes the `.bashrc` auto-attach snippet, daily workflow, and pitfalls (`.bashrc` write protection, server reboot recovery).

For macOS **cmux** push notifications specifically (not just session persistence), see `references/cmux-notify-tui.md` — covers the OSC 777 escape-sequence path, the `allow-passthrough` pitfall, and the frontend/backend event wiring.

Quick check:
```bash
# See if Hermes is running on bare SSH PTYs (fragile) or inside tmux (safe)
ps -eo pid,tty,cmd | grep hermes | grep -v grep
# pts/* = bare SSH PTY → at risk
# tmux   = inside tmux → safe
```

---

## Where to Find Things

| Looking for... | Location |
|----------------|----------|
| Config options | `hermes config edit` or [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Available tools | `hermes tools list` or [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Slash commands | `/help` in session or [Slash commands reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) |
| Skills catalog | `hermes skills browse` or [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `hermes model` or [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Kie.ai repro notes | `references/kie-ai-hermes-cli-repro.md` |
| Platform setup | `hermes gateway setup` or [Messaging docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) |
| MCP servers | `hermes mcp list` or [MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) |
| xAI auth (SuperGrok/API key) | `references/xai-auth-flow.md` |
| Profiles | `hermes profile list` or [Profiles docs](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) |
| Cron jobs | `hermes cron list` or [Cron docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Memory | `hermes memory status` or [Memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) |
| Env variables | `hermes config env-path` or [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| CLI commands | `hermes --help` or [CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) |
| Gateway logs | `~/.hermes/logs/gateway.log` |
| Session files | `~/.hermes/sessions/` or `hermes sessions browse` |
| Source code | `~/.hermes/hermes-agent/` |

---

## Contributor Quick Reference

For occasional contributors and PR authors. Full developer docs: https://hermes-agent.nousresearch.com/docs/developer-guide/

### Project Layout

```
hermes-agent/
├── run_agent.py          # AIAgent — core conversation loop
├── model_tools.py        # Tool discovery and dispatch
├── toolsets.py           # Toolset definitions
├── cli.py                # Interactive CLI (HermesCLI)
├── hermes_state.py       # SQLite session store
├── agent/                # Prompt builder, compression, display, adapters
├── hermes_cli/           # CLI subcommands, config, setup, commands
│   ├── commands.py       # Slash command registry (CommandDef)
│   ├── config.py         # DEFAULT_CONFIG, env var definitions
│   └── main.py           # CLI entry point and argparse
├── tools/                # One file per tool
│   └── registry.py       # Central tool registry
├── gateway/              # Messaging gateway
│   └── platforms/        # Platform adapters (telegram, discord, etc.)
├── cron/                 # Job scheduler
├── tests/                # ~3000 pytest tests
└── website/              # Docusaurus docs site
```

Config: `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys).

### Adding a Tool (3 files)

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add import** in `model_tools.py` → `_discover_tools()` list.

**3. Add to `toolsets.py`** → `_HERMES_CORE_TOOLS` list.

All handlers must return JSON strings. Use `get_hermes_home()` for paths, never hardcode `~/.hermes`.

### Adding a Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `cli.py` → `process_command()`
3. (Optional) Add gateway handler in `gateway/run.py`

All consumers (help text, autocomplete, Telegram menu, Slack mapping) derive from the central registry automatically.

### Agent Loop (High Level)

```
run_conversation():
  1. Build system prompt
  2. Loop while iterations < max:
     a. Call LLM (OpenAI-format messages + tool schemas)
     b. If tool_calls → dispatch each via handle_function_call() → append results → continue
     c. If text response → return
  3. Context compression triggers automatically near token limit
```

### Testing

```bash
source venv/bin/activate  # or .venv/bin/activate
python -m pytest tests/ -o 'addopts=' -q   # Full suite
python -m pytest tests/tools/ -q            # Specific area
```

- Tests auto-redirect `HERMES_HOME` to temp dirs — never touch real `~/.hermes/`
- Run full suite before pushing any change
- Use `-o 'addopts='` to clear any baked-in pytest flags

### Commit Conventions

```
type: concise subject line

Optional body.
```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

### API Robustness Patterns

When hardening a tool function that calls an external HTTP API (TTS, image gen, STT, etc.), apply these layers in order of priority. The goal: the function never fails for transient reasons and handles input of any size.

**1. Retry with exponential backoff (mandatory first layer)**

Wrap the HTTP call in a retry loop. 3 attempts is usually enough. Backoff: 2s, 4s, 8s for timeouts/5xx; 4s, 8s, 16s for 429 rate limits. Do NOT retry on 4xx client errors except 429.

```python
import time as _time
max_retries = 3
for attempt in range(max_retries):
    try:
        response = requests.post(endpoint, json=payload, timeout=120)
    except requests.exceptions.Timeout:
        if attempt < max_retries - 1:
            wait = 2 * (2 ** attempt)
            logger.warning("Timeout (attempt %d/%d), retrying in %ds...", attempt+1, max_retries, wait)
            _time.sleep(wait)
            continue
        raise RuntimeError(f"API timed out after {max_retries} attempts")
    except requests.exceptions.ConnectionError as e:
        # Same pattern — retry, then raise on final attempt
        ...
    if response.status_code >= 500:
        # Retry on server errors
        ...
    elif response.status_code == 429:
        # Retry with doubled backoff (4s, 8s, 16s)
        ...
    elif response.status_code == 200:
        break
    else:
        break  # 4xx client errors: fail fast
```

Use `response.json()` parsing inside a try/except KeyError/IndexError to surface malformed responses cleanly.

**2. Automatic text chunking (for length-limited APIs)**

If the API has an input length limit (Gemini TTS: ~3000 chars, ElevenLabs: 5000 chars), add a chunking wrapper that:
- Splits at sentence boundaries (`.!?…`) using `re.split(r'(?<=[.!?…])\s+', text)`
- For sentences exceeding the limit, further split by word boundaries
- Generates audio/image per chunk, concatenates with ffmpeg/ImageMagick
- Short inputs pass through directly (no overhead)

Do NOT chunk by fixed character count — sentence-boundary splitting preserves natural pauses. Place chunking logic in a separate `_generate_X_chunked()` wrapper so the base function stays clean.

**3. Provider fallback (last resort)**

If all retries + chunking fail, fall back to an alternative provider (e.g., Gemini TTS → Edge TTS). Wrap the primary call in try/except, catch the broadest Exception, log the error, and route to the fallback. Raise a combined error only if the fallback is also unavailable.

```python
try:
    _generate_primary_chunked(text, output_path, config)
except Exception as primary_err:
    logger.warning("Primary failed (%s), falling back to secondary...", primary_err)
    try:
        _import_secondary()
    except ImportError:
        raise RuntimeError(
            f"Primary failed and secondary unavailable. Primary error: {primary_err}"
        ) from primary_err
    _generate_secondary(text, output_path, config)
```

**Testing the robustness:** after patching, test with `python3 -c "import ast; ast.parse(open('tools/tts_tool.py').read()); print('Syntax OK')"` then run a real call with a long text to verify chunking and fallback fire correctly.

### Key Rules

- **Never break prompt caching** — don't change context, tools, or system prompt mid-conversation
- **Message role alternation** — never two assistant or two user messages in a row
- Use `get_hermes_home()` from `hermes_constants` for all paths (profile-safe)
- Config values go in `config.yaml`, secrets go in `.env`
- New tools need a `check_fn` so they only appear when requirements are met
