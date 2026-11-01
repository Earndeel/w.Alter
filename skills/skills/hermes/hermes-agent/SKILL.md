---
name: hermes-agent
description: Use when configuring, using, or extending Hermes Agent. Load operating guardrails and route to the relevant procedure.
version: 2.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent: operating guardrails and procedure routing

Hermes Agent is built by Nous Research. This entry is a routing layer, not a replacement for the procedures. The entire original manual is preserved verbatim in [references/full-guide.md](references/full-guide.md). Existing linked files remain available.

## Mandatory prerequisites

- Before configuring, modifying, troubleshooting, or advising about Hermes, identify the actual installation, interpreter, version, active profile, and relevant config. Do not infer the host from user memory or trust a stale CLI. Use current `--help`, local source, and https://hermes-agent.nousresearch.com/docs/ as authoritative references; historical examples may be stale.
- Before executing a subject's commands, load its linked procedure below with `skill_view(name='hermes-agent', file_path='references/...')`. If the subject is only in the full manual, load `references/full-guide.md` in full. Do not act from a heading or remembered commands. Read linked prerequisites required by that procedure; unrelated subjects need not be loaded.
- Verify profile and credential scope before writes. Use `get_hermes_home()` in code. Settings belong in `config.yaml`, secrets in `.env` or the documented credential store; never expose secrets or put another profile's credentials into the default profile. Verify the exact target after changes. Do not alter other profiles without permission.
- Preserve approval and safety gates. Never use `mount --bind` followed by `remount,ro`: it can make the source read-only. Desktop SSH `IdentityFile` paths must be absolute; inspect platform-specific permission instructions before changing access.
- Preserve cached system bytes and tools throughout a conversation; do not reload memories or mutate prior context. Compression is the sanctioned exception. Config/tool changes normally take effect in a new session or documented restart, not opportunistically mid-turn. Preserve message-role alternation.
- For code changes: read root and area `AGENTS.md`, audit tracked and untracked changes, use isolated worktrees and test homes, and preserve local work before updates. Verify local imports and run the checkout's official test runner. Never let tests touch production state. New tool handlers return JSON strings and require availability checks.
- Delegation config affects inline subagents only. Cron uses the job model override or session default; Kanban and spawned profile processes use their target profile. Initialize the Kanban board before use. Send workers minimal task capsules, not full orchestrator context. Do not change models/providers without authorization. The full manual retains the Kie.ai orchestrator prohibition and provider-specific routing prerequisites.
- For API hardening, read the full robustness procedure: bounded transient retries, no client-error retries except 429, sentence-aware chunking, then authorized fallback. Exercise the real result before claiming success; syntax alone is not verification.

## Subject routing

Use `skill_view(name='hermes-agent', file_path='<path>')` with these paths. When a route is absent or unclear, load `references/full-guide.md` rather than guessing.

| Subject | Required reference |
|---|---|
| Installation; CLI, sessions, setup, tools, skills, MCP, gateway, profiles and initial OAuth setup | `references/procedure-cli.md` |
| Desktop app, SSH/permissions, multi-account OAuth and credential pools | `references/procedure-desktop-auth.md` |
| Slash commands, key paths, config, image generation, providers and toolsets | `references/procedure-commands-config.md` |
| Voice, STT and TTS | `references/procedure-voice.md` |
| Spawning, delegation, profiles, cron model scope, Kanban and provider routing pitfalls | `references/procedure-orchestration.md` |
| Troubleshooting, updates, gateway lifecycle, SSH persistence and documentation lookup | `references/procedure-troubleshooting.md` |
| Contributor layout, tools, commands, tests, API robustness and core invariants | `references/procedure-contributing.md` |
| Cross-subject questions or anything not covered above | `references/full-guide.md` |
| Subagents vs profiles vs Kanban | `references/multi-agent-levels.md` |
| Skill bundles and two-level loading | `references/skill-bundles-and-loading.md` |
| v0.14 features and version-specific behavior | `references/v014-features.md` |
| Gateway media attachments for generation APIs | `references/media-inputs-for-generation.md` |
| Custom Anthropic-native provider configuration | `references/custom-anthropic-providers.md` |
| Kie.ai CLI reproduction | `references/kie-ai-hermes-cli-repro.md` |
| xAI authentication | `references/xai-auth-flow.md` |
| SSH session persistence | `references/ssh-tmux-persistence.md` |
| macOS cmux notifications | `references/cmux-notify-tui.md` |

The full manual also routes to specialized skills (including `hermes-multi-agent-profiles`, Kanban skills, and coding CLIs). Preserve those prerequisites when that workflow applies. Paths and workflows are not removed by this compact entry.
