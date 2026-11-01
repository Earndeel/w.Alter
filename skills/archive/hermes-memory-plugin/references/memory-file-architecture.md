# Hermes Memory File Architecture — System Prompt Injection

Hermes injects memory-related files into the system prompt at every LLM call. Understanding what goes where prevents duplication and controls token cost.

## Three-Tier System Prompt Structure

The system prompt (`agent/system_prompt.py:build_system_prompt_parts()`) is assembled in three tiers:

### 1. STABLE (cached for entire session)
- **`~/.hermes/SOUL.md`** — Agent identity, communication style, rules. Loaded via `load_soul_md()` from `agent/prompt_builder.py`. If missing, falls back to `DEFAULT_AGENT_IDENTITY` (hardcoded).
- Tool guidance blocks (MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE)
- Tool-use enforcement (model-specific operational guidance)
- Skills index (names + descriptions of installed skills)
- Environment hints (WSL, Termux, etc.)
- Platform hints (Telegram, Discord, etc.)

### 2. CONTEXT (session-stable, depends on CWD)
- **AGENTS.md** — Project dev instructions (top-level CWD only)
- **CLAUDE.md** — Project dev instructions (CWD only)
- **.cursorrules** + `.cursor/rules/*.mdc` — Project dev instructions (CWD only)
- **.hermes.md / HERMES.md** — Walks up to git root
- Caller-supplied `system_message`

### 3. VOLATILE (changes per session/turn — never cached)
- **`~/.hermes/memories/MEMORY.md`** — Operational notes. Labeled "MEMORY (your personal notes)" in system prompt. Read by `MemoryStore.format_for_system_prompt("memory")`.
- **`~/.hermes/memories/USER.md`** — User profile. Labeled "USER PROFILE (who the user is)". Read by `MemoryStore.format_for_system_prompt("user")`.
- **External memory provider** (e.g., Hindsight) — Plugin `system_prompt_block()` output. Additive to built-in.
- Timestamp + model + provider line.

## File Purposes

| File | Purpose | Char limit | Content type |
|---|---|---|---|
| `SOUL.md` | Who the agent IS | None enforced | Identity, style, rules, values |
| `USER.md` | Who the user IS | 1,375 (configurable) | Preferences, habits, corrections |
| `MEMORY.md` | Operational facts | 2,200 (configurable) | Durable facts not in config/skills |

## Configuration

In `config.yaml`:
```yaml
memory:
  memory_enabled: true       # Enable MEMORY.md injection
  user_profile_enabled: true # Enable USER.md injection
  memory_char_limit: 2200    # Max chars for MEMORY.md
  user_char_limit: 1375      # Max chars for USER.md
  nudge_interval: 10         # Turns between memory save reminders
```

## Common Pitfalls

### Duplication across files
MEMORY.md, USER.md, and SOUL.md should NOT contain overlapping content. Common mistake: putting user preferences in both MEMORY.md and USER.md, or putting agent personality in both SOUL.md and MEMORY.md. Each fact belongs in exactly one file.

### MEMORY.md as config dump
MEMORY.md is injected at every call. Putting config values (ports, IPs, provider settings) that already exist in `config.yaml` or skills wastes tokens. MEMORY.md should contain only facts that are:
1. Not derivable from config.yaml
2. Not documented in any skill
3. Durable (will still be true in 7+ days)
4. Critical (would cause the agent to make a wrong decision without them)

### Token cost awareness
Every character in SOUL.md + MEMORY.md + USER.md is injected at every LLM call. At 3 files totaling ~4,770 chars, that's ~1,200 tokens per call. For a session with 50 turns, that's 60,000 tokens of pure overhead. Keep files lean.

### SOUL.md vs system prompt defaults
If SOUL.md exists, it replaces DEFAULT_AGENT_IDENTITY entirely (not appended). If SOUL.md is missing, the hardcoded default is used. SOUL.md should contain ALL identity information — the agent won't see the default if SOUL.md is present.

### Memory store reload on compression
After context compression, `invalidate_system_prompt()` reloads MEMORY.md and USER.md from disk. Any `memory` tool writes during the session are persisted to `memory.json` and picked up on the next rebuild.

## Source Code References

| File | Function | What it does |
|---|---|---|
| `agent/system_prompt.py:60` | `build_system_prompt_parts()` | Assembles the 3-tier system prompt |
| `agent/system_prompt.py:287` | `build_system_prompt()` | Joins tiers into final string |
| `agent/system_prompt.py:306` | `invalidate_system_prompt()` | Rebuilds after compression |
| `agent/prompt_builder.py:1313` | `load_soul_md()` | Reads SOUL.md from HERMES_HOME |
| `agent/agent_init.py:969` | Memory store init | Loads MEMORY.md + USER.md via MemoryStore |
| `tools/memory_tool.py` | `MemoryStore` | Reads/writes memory.json, formats for system prompt |
