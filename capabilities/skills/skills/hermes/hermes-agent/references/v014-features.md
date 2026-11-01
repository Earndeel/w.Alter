# Hermes Agent v0.14.0 Features Reference (2026.5.16)

Release: 808 commits, 633 merged PRs, 165k insertions, 215 contributors.
Install: `pip install hermes-agent` (PyPI) or `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`

---

## `/handoff` — Live Session Transfer

Transfer active session (all messages, tool calls, context) to a different model, persona, or profile — without losing anything.

**Syntax:** `/handoff <target>` where target is a model name, personality, or profile.

**Use cases:**
- Debugging with a fast model → stuck → `/handoff opus` → powerful model continues with full context
- Switch profiles mid-task: `/handoff coder`
- Change persona: `/handoff formal`

**Pitfall:** This is a slash command, not a CLI flag. Must be used inside an interactive session.

---

## `hermes proxy` — OpenAI-Compatible Local Proxy

Runs a local HTTP endpoint that speaks the OpenAI API but is backed by whichever OAuth provider you're signed into (Claude Pro, ChatGPT Pro, SuperGrok).

**Syntax:** `hermes proxy` → starts `http://localhost:<port>`

**Impact:** Any tool expecting OpenAI-compatible endpoint (Codex CLI, Aider, Cline, Continue, custom scripts) works with your existing subscription. One subscription, every tool.

**Prerequisite:** Must have an active OAuth session with at least one provider.

---

## `x_search` — Native X (Twitter) Search

First-class tool for searching X without installing a skill or wiring custom integration.

**Prerequisites:** SuperGrok OAuth (`hermes auth add xai-oauth`) OR `XAI_API_KEY`. OAuth wins when both configured. Premium+ ($40/mo) includes SuperGrok — use OAuth to avoid paying for API credits.

**Setup (remote VPS):** See `references/xai-oauth-setup.md` in this skill for the full PTY + reverse tunnel + CDP flow.

**Activation:** `hermes tools` → enable `🐦 X (Twitter) Search`. Off by default.

**Config:**
```yaml
x_search:
  model: grok-4.20-reasoning
  timeout_seconds: 180
  retries: 2
```

**Parameters:** `query` (required), `allowed_x_handles`, `excluded_x_handles`, `from_date`/`to_date`, `enable_image_understanding`, `enable_video_understanding`

**Cost:** $0 with SuperGrok subscription. Paid xAI API key otherwise.

Full ecosystem overview: see `xurl` skill → `references/x-ecosystem-overview.md`

---

## Browser CDP — Connection Reuse (180x per-call overhead reduction)

`browser_console` evaluations now share one persistent Chrome DevTools Protocol WebSocket connection instead of spinning up a new DevTools session per call.

**What improved:** CDP call overhead (WebSocket handshake). Each JS evaluation / DOM query / click goes from ~2800ms (new connection) to ~100-150ms (persistent connection).

**What did NOT change:** Page load time (network-bound), rendering speed, initial CDP connection time.

**Measured benchmarks (Brave on Mac via Tailscale SSH tunnel, May 2026):**
- CDP connect (first): ~0.8s
- JS evaluate (persistent connection): 60-156ms average
- 10x sequential calls: ~1.5s total (vs ~28s old behavior)

**Impact:** Multi-step browser automation (inspect → click → read → screenshot) is dramatically faster because each step reuses the same connection. Single page loads are unchanged. PR #23226.

**Remote Mac CDP:** To use browser tools against Brave/Chrome on a remote Mac via SSH tunnel, see `playwright-cdp-browser-control` skill → "Connecting to Brave/Chrome on a Remote Mac via SSH Tunnel" section.

---

## Cross-Session 1h Claude Prompt Cache

When using Claude via Anthropic, OpenRouter, or Nous Portal, the prompt prefix (system prompt, skills, memory) caches for 1 hour across sessions.

**Effect:** Starting `/new` → first response is faster and cheaper because cache is still warm. Background memory review also hits the cache.

**PRs:** #23828, #25434, #24778

---

## Cold-Start Performance: -19 Seconds

Launch optimizations:
- Skills cache on disk
- Heavy adapters (Feishu, QQ, Yuanbao, Teams, fal_client) lazy-load on first use
- Model catalogs from disk cache first
- `hermes doctor` checks run in parallel
- `chat -q` skips welcome banner
- `hermes tools` All-Platforms: 14s → <1.5s

---

## Native Clarify Buttons (Telegram + Discord)

When the agent uses the `clarify` tool with multiple-choice options, it now shows platform-native buttons on Telegram and Discord instead of asking the user to type a number.

**PRs:** #24199, #25485

---

## `computer_use` cua-driver Backend

Computer Use (agent controlling mouse/keyboard to drive GUI apps) now works with non-Anthropic providers.

**Before:** Locked to Anthropic SDK.
**After:** Any vision-capable model (GPT-5, Gemini, Grok-vision) can drive your desktop.

**Features:** Focus-safe operations, auto-refresh on `hermes update`.

**Mac support:** Works on macOS, BUT requires direct display access. For Mac ↔ VPS setups without installing Hermes on the Mac: use the **LaunchAgent HTTP server approach** (see `mac-computer-use-ssh` skill). A Python HTTP server runs in the user's GUI session as a LaunchAgent, serving screenshots via `screencapture` and accepting click/type commands via `cliclick`. The VPS connects through an SSH tunnel. This bypasses the TCC Screen Recording block that affects SSH sessions.

**PRs:** #21967, #24063

---

## LSP Semantic Diagnostics on Write

When the agent uses `write_file` or `patch`, Hermes runs a real language server against the edited file and surfaces new errors before the next turn.

**Catches:** Type errors, undefined symbols, missing imports — actual semantic analysis, not just linting.

**PRs:** #24168, #25978

---

## Per-Turn File-Mutation Verifier

After every turn that wrote/edited files, the agent gets a footer summarizing what changed on disk (file paths, line counts, delta). Catches silent write failures.

**PR:** #24498

---

## 2 New Messaging Platforms

- **LINE** — LINE Messaging API (huge in Japan, Korea, Taiwan)
- **SimpleX Chat** — Privacy-focused decentralized messenger, no user IDs

Total: **22 messaging platforms**.

**PRs:** #23197, #26232

---

## Microsoft Teams — End-to-End

Full stack: Graph auth + webhook listener + pipeline runtime + outbound delivery.

**PRs:** #21922, #21969, #22007, #22024

---

## 9 New Optional Skills

| Skill | Category | Description |
|---|---|---|
| Hyperliquid | blockchain | Perp + spot trading via SDK + REST API |
| Yahoo Finance | finance | Live market data, fundamentals, historicals |
| api-testing | devops | REST + GraphQL debug recipes |
| EVM multi-chain | blockchain | Ethereum + L2s + Base in one skill |
| darwinian-evolver | research | Evolutionary prompt/skill tuning |
| osint-investigation | security | OSINT recipes for people/domains/orgs |
| pinggy-tunnel | devops | Expose local services to public internet |
| watchers | devops | Poll RSS/HTTP JSON/GitHub via cron `no_agent` |
| Notion overhaul | productivity | May 2026 Developer Platform update |

Optional skills location: `optional-skills/` in repo.

---

## Other Notable Changes

- **`/subgoal`** — append criteria to active `/goal` mid-run
- **`vision_analyze` returns raw pixels** to vision-capable models (no text-summary roundtrip)
- **Discord channel history backfill** (default on) — agent reads recent history before responding
- **Clickable URLs** (OSC8 hyperlinks) in any terminal
- **Zed ACP Registry** — one-click install via `uvx`
- **OpenRouter Pareto Code router** with `min_coding_score` knob
- **NovitaAI** as new model provider
- **`huggingface/skills`** as trusted default skills tap
- **Brave Search (free tier) + DuckDuckGo** as web-search providers
- **Sudo brute-force block** + 3 dangerous-command bypasses closed
- **Tool error sanitization** — errors sanitized before re-injection into model context
- **Provider rename** Alibaba Cloud → Qwen Cloud (config keys unchanged)
- **Native Windows support** (early beta) — cmd.exe + PowerShell without WSL
