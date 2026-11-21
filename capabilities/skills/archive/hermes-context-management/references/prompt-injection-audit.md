# Prompt Injection Payload Audit & Cleanup

Use this when Hermes context feels bloated, duplicated, or the user asks what is injected on every call.

## Real injection layers

Hermes builds the system prompt in `agent/system_prompt.py` as three tiers:

1. **Stable tier**
   - `~/.hermes/SOUL.md` if present, otherwise `DEFAULT_AGENT_IDENTITY`
   - Hermes help guidance
   - tool guidance blocks for enabled tools (`memory`, `session_search`, `skill_manage`, Kanban, computer_use)
   - model-family operational guidance
   - skills index (`build_skills_system_prompt`)
   - environment/platform hints

2. **Context tier**
   - caller-provided `system_message`
   - cwd/project context files via `build_context_files_prompt`:
     - `AGENTS.md` / `agents.md` in cwd
     - `CLAUDE.md` / `claude.md` in cwd
     - `.cursorrules` and `.cursor/rules/*.mdc`
     - nearest `.hermes.md` / `HERMES.md` walking toward git root

3. **Volatile tier**
   - `~/.hermes/memories/MEMORY.md` when `memory.memory_enabled=true`
   - `~/.hermes/memories/USER.md` when `memory.user_profile_enabled=true`
   - external memory provider system prompt block, e.g. Hindsight
   - date/model/provider/session metadata

The final prompt is cached per agent session and rebuilt after compression invalidation. File edits may require `/reset`, new CLI session, or gateway restart to appear immediately.

## Correct file responsibilities

| File | Belongs here | Does not belong here |
|---|---|---|
| `SOUL.md` | Agent identity, tone, communication rules, persona | User preferences, infrastructure, secrets |
| `USER.md` | Durable user preferences, habits, product/business constraints | Agent identity, ports, provider config, secrets |
| `MEMORY.md` | Durable operational facts not easily discoverable elsewhere | Secrets/tokens, volatile IPs, task progress, duplicate config, long procedures |
| Skills | Reusable procedures, troubleshooting recipes, known pitfalls | One-off session notes |
| `config.yaml` / `.env` / vault | Settings and secrets | Prose memory |
| Hindsight/session_search | Long history and recall | Small always-needed facts |

## Audit workflow

1. Measure sizes for `SOUL.md`, `USER.md`, `MEMORY.md` and scan for duplicate terms.
2. Check current cwd context files before blaming memory bloat.
3. Classify every line by responsibility before editing.
4. Back up the three files before rewriting.
5. Remove secrets from memory; store only pointers such as “token in vault”.
6. Replace volatile facts with discovery instructions when needed: e.g. “inspect container IP after restart”.
7. Restart gateway or start a fresh session to verify the new payload.

## Good cleanup target

Keep injected memory compact:
- `SOUL.md`: identity/style only, roughly 1–1.5k chars.
- `USER.md`: user preferences and durable constraints, roughly 0.8–1.4k chars.
- `MEMORY.md`: operational facts, roughly 0.5–1.5k chars.

Do not compress by deleting important user preferences; move them to the right layer instead. The goal is fewer duplicates, not amnesia — a distinction agents are famously proud of missing.
