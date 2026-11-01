---
name: hermes-memory-plugin
category: devops
description: Guide for creating custom MemoryProvider plugins for Hermes Agent, including the ABC interface, plugin structure, and integration patterns.
tags: [hermes, memory, plugin, lancedb, embeddings]
created: 2026-04-04
---

# Creating Custom Memory Plugins for Hermes Agent

Hermes uses a pluggable `MemoryProvider` system for long-term memory. Plugins live in `plugins/memory/<name>/` and are activated via `memory.provider` in `config.yaml`.

## Plugin Structure

```
plugins/memory/<name>/
├── __init__.py          # <Name>Provider(MemoryProvider) implementation
├── embedder.py          # Embedding backend (API key, OAuth, or local)
├── store.py             # Vector/metadata storage (LanceDB, SQLite, etc.)
├── retriever.py         # Search logic (vector similarity, keyword fallback)
├── plugin.yaml          # Plugin metadata (name, version, description, hooks)
└── README.md            # Setup instructions
```

**CRITICAL: Directory name MUST use underscores** (`lancedb_gemini`), not hyphens. Python imports require it.

## MemoryProvider ABC Interface

Import: `from agent.memory_provider import MemoryProvider`

### Required Methods

| Method | Description |
|--------|-------------|
| `name` (property) | Short identifier, e.g. `"lancedb-gemini"` |
| `is_available()` | Quick check (no network) -- config/creds/deps OK? |
| `initialize(session_id, **kwargs)` | Called at startup. `kwargs` includes `hermes_home`, `platform`, `agent_context`, `agent_identity`. Connect DB, load models. |
| `get_tool_schemas()` | Return list of OpenAI function-calling schemas. Each: `{"name": "...", "description": "...", "parameters": {...}}` |
| `handle_tool_call(tool_name, args, **kwargs)` | Dispatch tool calls. Must return JSON string. |

### Recommended Methods

| Method | Purpose |
|--------|---------|
| `system_prompt_block()` | Static text injected into agent system prompt. Return empty string to skip. |
| `prefetch(query, session_id="")` | Return cached recall results for context injection. |
| `queue_prefetch(query, session_id="")` | Queue background recall for NEXT turn. |
| `sync_turn(user, assistant, session_id="")` | Persist a completed turn. Non-blocking. |
| `shutdown()` | Clean exit -- flush queues, close connections. |
| `on_session_end(messages)` | Extract facts from full conversation at session end. |
| `on_memory_write(action, target, content)` | Mirror built-in memory writes. |
| `get_config_schema()` | Config fields for `hermes memory setup` wizard. |
| `save_config(values, hermes_home)` | Write config to JSON. |

## Lifecycle

1. **Detection**: `is_available()` called for each plugin at startup
2. **Activation**: If `memory.provider` matches plugin name, `initialize()` is called
3. **Prefetch**: Before each API call, `prefetch()` injects recall context
4. **Queue**: After each turn, `queue_prefetch()` backgrounds next recall
5. **Sync**: After each turn, `sync_turn()` stores conversation data
6. **Tools**: Agent tools from `get_tool_schemas()` are exposed to the model
7. **Session end**: `on_session_end()` extracts session insights
8. **Shutdown**: `shutdown()` cleans up resources

## Implementation Notes

### Embedding Backends
- **Gemini Embedding 2** (`gemini-embedding-2-preview`): 3072-dim via `?key=API_KEY`. Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2-preview:embedContent`. Payload: `{"model": "models/gemini-embedding-2-preview", "content": {"parts": [{"text": "..."}]}}`. Response: `{"embedding": {"values": [...]}}`. Latence ~0.9s.
- **Local fallback**: `pip install fastembed` + `BAAI/bge-base-en-v1.5` (768-dim, works offline)
- Always provide local fallback when API embedding fails
- **Noms invalides** : `text-embedding-004` et `text-embedding-002` retournent 404 — seul `gemini-embedding-2-preview` et `gemini-embedding-001` existent

#### Switch Embedder: Local → API (ou l'inverse)
Pour basculer d'un backend d'embedding à un autre, MODIFIER ces fichiers dans l'ordre :
1. `embedder.py` : Remplacer la classe (garder nom `LocalEmbedder` pour compatibilité imports)
2. `store.py` : Rendre `vector_dim` dynamique (paramètre `__init__`, pas constante hardcodée)
3. `__init__.py` : Lire `api_key` depuis config.json, passer `vector_dim=self._embedder.dimension` au store
4. `config.json` : Ajouter `"api_key"` et changer `"embed_model"`
5. Supprimer `$HERMES_HOME/<plugin>/memories.lance/` (schema dimension mismatch sinon)
6. Redémarrer gateway — la table sera recréée avec la bonne dimension au premier `add()`

### LanceDB 0.30 API
- `table.update(where="...", values={})` -- **keyword-only**, not positional
- `table.delete("where clause")` -- positional WHERE string
- `table.add(data=[{...}])` -- list of dicts
- `table.to_lance().to_table().to_pylist()` -- retrieve all rows
- Vectors must be `list[float]` with matching dimension (768)
- Schema requires `pa.list_(pa.float32(), DIM)` for vector column
- **CRITICAL:** `update()` `values` dict must contain **native Python types** (`int`, `float`, `str`), **NOT** SQL expressions like `"column + 1"`. LanceDB 0.30 does not evaluate SQL expressions in values.
- **CRITICAL:** Always initialize `values` dict (`values = {}`) before the update block; uninitialized variable errors will crash the plugin.
- **CRITICAL for `update()`:** values dict must contain NATIVE Python types (`int`, `float`, `str`), NOT SQL expressions like `"column + 1"`. LanceDB 0.30 no longer evaluates SQL in values -- pass the computed integer/float directly.

### Hermes Source Location

Single source: `/root/.hermes/hermes-agent/` -- used by both gateway and CLI.
There is NO `/root/hermes/code/hermes-agent/` copy (removed). Ignore any outdated docs about dual copies.

### Dependencies
- The gateway venv (`/root/.hermes/hermes-agent/venv/`) often has NO pip -- install first: `python -m ensurepip --upgrade`
- Then: `venv/bin/python -m pip install lancedb google-auth fastembed`
- The venv is Python 3.11.15, not system Python
- Core deps for vector stores: `lancedb`, `pyarrow`, `google-auth`
- Core deps for local embeddings: `fastembed`

### Config Integration
- Plugin config goes in `$HERMES_HOME/<plugin-name>/config.json`
- Secrets go to `$HERMES_HOME/.env` as `PLUGIN_API_KEY=xxx`
- Activation: `hermes config set memory.provider <name>` or edit `memory.provider` in `config.yaml`

### Tool Schemas Example
```python
MEMORY_RECALL_SCHEMA = {
    "name": "memory_recall",
    "description": "Search long-term semantic memory...",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "probe", "stats"]},
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["action"],
    },
}
```

### Pitfalls
1. **OAuth vs API Key**: gemini-embedding-2-preview requires standard API key (AIza...), NOT OAuth tokens from Google CLI. Use `?key=` URL param.
2. **Hyphen in module name**: Python can't import `lancedb-gemini` -- use `lancedb_gemini`
3. **Thread safety**: Use locks for shared state (prefetch results, model loading)
4. **Non-blocking**: All I/O should be background threads -- never block the agent loop
5. **JSON return**: `handle_tool_call()` MUST return a JSON string, not a dict.
6. **`_extract_facts` regex**: The original regex `^[A-Z][\w\s]+?[:]` only matches `UPPERCASE: value` lines. Use a multi-strategy approach: (a) broadened KEY:VALUE pattern accepting mixed case and accents, (b) declarative sentence extraction with anti-filler word filtering (greetings, bullets, meta-commentary, questions, exclamations). Without this fix, sync_turn stores ZERO facts.
7. **`on_session_end` must capture both roles**: Original only captured user messages with personal pronouns and <300 chars. Enhanced version captures user preferences AND all extracted assistant facts via `_extract_facts`.
8. **`on_memory_write` hook**: Implement this to sync the built-in `memory` tool writes into LanceDB vector store. Without it, the two memory systems are completely disconnected.

### Gateway Restart for Plugin Activation
After installing new deps or plugins, restart gateway:
```bash
kill -9 $(pgrep -f 'hermes.*gateway')
rm -f /root/.hermes/gateway_state.json /root/.hermes/gateway.pid
nohup /root/.local/bin/hermes gateway run --replace > /root/.hermes/gateway.log 2>&1 &
```

### Critical Pitfalls
1. **Secret sandboxing**: Never use `execute_code` or `terminal()` to write tokens to `.env` -- the Hermes sandbox replaces sensitive values with `***`, corrupting the file. Always use `python3 << 'PYEOF'` heredoc blocks for raw secret writes.

2. **Session contamination via group_sessions_per_user**: When `group_sessions_per_user: true` in config.yaml, ALL platforms (CLI, Telegram, etc.) share the same conversation session. The CLI's diagnostic/work context bleeds into Telegram responses. Set `group_sessions_per_user: false` to give each platform its own isolated session. When fixing Telegram issues, also close stale sessions: `UPDATE sessions SET ended_at=?, end_reason='cleanup' WHERE ended_at IS NULL`.

2. **Gateway state.json caches errors**: Even after fixing config, old errors persist. Always delete `gateway_state.json` before restart. The state file is also contradictory -- can show `state: connected` AND an error simultaneously. Trust `exit_reason: None` (no error).

3. **`execute_code terminal()` has no `background` parameter**: Use `terminal()` directly or `os.system()`. `signal.kill()` doesn't exist -- use `os.kill(pid, signal.SIGKILL)`.

### hermes update & Custom Plugin Survival
`hermes update` uses `git stash push --include-untracked` before pulling, then `git stash apply` after. This preserves untracked files (like custom plugins in `plugins/memory/<name>/`). The stash is kept for manual review — check with `git stash list` after updates.

### Built-in Memory vs Plugin Memory
Hermes has TWO independent memory systems:
1. **Built-in**: `~/.hermes/memories/MEMORY.md` + `USER.md` + `~/.hermes/SOUL.md` — always active, text-based, injected into the system prompt via `MemoryStore` in `tools/memory_tool.py`. SOUL.md goes in the **stable** tier (cached), MEMORY.md and USER.md go in the **volatile** tier (reloaded on compression).
2. **Plugin**: `plugins/memory/<name>/` — optional, activated by `memory.provider` in config.yaml, handles semantic/vector search

Both run simultaneously. The plugin is additive — it never disables the built-in system.

See **`references/memory-file-architecture.md`** for the full three-tier system prompt injection architecture, file purposes, char limits, and common pitfalls (duplication, config dumps, token cost).

### .env Corruption Pattern (Line Number Prefixes)
The `.env` file can get corrupted where every line gets a literal line number prefix: `354|GEMINI_API_KEY=***`. This happens when `read_file()` output (which adds `LINE_NUM|` prefixes) is accidentally written back to `.env`. The sanitizer `_sanitize_env_lines()` does NOT fix this pattern.

**Detection**: `grep -c '^[0-9]*|' ~/.hermes/.env` — if > 0, file is corrupted.

**Fix**: Strip prefixes with regex: `re.match(r'^(\d+)\|(.*)', line)`.

**Prevention**: NEVER pipe `read_file()` output directly into `write_file()` for `.env`. Use `terminal()` with Python heredoc for raw writes.

### Gemini Embedding API
- Model: `text-embedding-004`
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=API_KEY`
- Task types: `RETRIEVAL_DOCUMENT` (storing), `RETRIEVAL_QUERY` (searching)
- Supports `outputDimensionality`: 768-3072
- Payload: `{"model": "models/text-embedding-004", "content": {"parts": [{"text": "..."}]}, "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": 3072}`
- Response: `{"embedding": {"values": [float, ...]}}`

4. **Duplicate keys in .env**: Hermes may write both commented and uncommented versions of the same key. Replace ALL occurrences.

5. **Compression provider must host the model**: `auxiliary.compression.provider` in config.yaml must be a provider that actually serves the configured model. Example: `provider: groq` + `model: gemini-3.1-flash-lite` silently fails because Groq has no Gemini models. Symptom in logs: `No auxiliary LLM provider for compression — summaries will be unavailable`. Middle turns get dropped without summary. Always verify provider model availability before configuring.