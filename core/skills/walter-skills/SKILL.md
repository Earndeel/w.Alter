---
name: walter-skills
description: Use before infra/ops work on the W.Alter VM or any task about Monsieur's projects, accounts or integrations. W.Alter (Monsieur's personal agent) keeps ~500 tested procedures (skills) for this VM, its services, APIs and projects; find and read them with the walter MCP tools skills_search / skill_read instead of re-deriving.
---

# W.Alter skills (shared catalogue)

W.Alter's procedural memory lives in one place and is shared by every runtime (Hermes, Claude Code, Codex…).
It is not loaded into your context; fetch only what the task needs.

1. `skills_search(query)` — keywords in English or French (service name, API, project, error message).
2. `skill_read(name)` — read the chosen procedure fully before acting.
3. Follow it, adapting tool names: skills are written for Hermes (`terminal`, `read_file`, `browser_*`…);
   use your own equivalents. Steps that need Monsieur's live integrations (Telegram, Google accounts,
   calendar, his browser sessions, Bitwarden) → delegate with `ask_hermes`.
4. Memory first for anything personal: `memory_context` / `memory_search` / `person_lookup`.

Never copy secrets from a skill or a memory into files, commands or answers.
