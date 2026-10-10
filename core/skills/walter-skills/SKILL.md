---
name: walter-skills
description: Use before infra/ops work on the W.Alter VM or any task about Monsieur's projects, accounts or integrations. W.Alter (Monsieur's personal agent) keeps ~300 tested procedures (skills) for this VM, its services, APIs and projects; the hook already injects the best matches per prompt — find more and read them with the walter MCP tools skills_search / skill_read instead of re-deriving.
---

# W.Alter skills (shared catalogue)

W.Alter's procedural memory lives in one place and is shared by every runtime (Hermes, Claude Code, Codex…).
It is not loaded into your context; fetch only what the task needs.

1. `skills_search(query, context=…)` — the request in plain words, English or French (intent, service, error message); the hook may already have listed the right skills above the prompt.
2. `skill_read(name)` — read the chosen procedure fully before acting; `skill_read(name, file_path="references/…")` for linked files.
3. Follow it, adapting tool names: skills are written for Hermes (`terminal`, `read_file`, `browser_*`…);
   use your own equivalents. Steps that need Monsieur's live integrations (Telegram, Google accounts,
   calendar, his browser sessions, Bitwarden) → delegate with `ask_hermes`.
4. Memory first for anything personal: `memory_context` / `memory_search` / `person_lookup`.

5. Keep the library alive: when a skill proved wrong, outdated or incomplete while you used it, call
   `skill_patch(name, reason, …)` with the corrected SKILL.md (or one linked file) and the evidence; after solving a
   task that will recur and has no skill, call `skill_propose(name, skill_md, reason)`. Both go to drafts: the
   walter-skills curator reviews them at night (judge + checks) before they are live.

Never copy secrets from a skill or a memory into files, commands or answers — and never paste one into a skill.
