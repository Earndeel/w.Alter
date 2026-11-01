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

