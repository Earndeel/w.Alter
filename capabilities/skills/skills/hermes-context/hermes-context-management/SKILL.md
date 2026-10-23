---
name: hermes-context-management
category: devops
description: Diagnose and fix Hermes Agent context bloat -- analyze payload composition, compression failures, session contamination, and optimize token usage.
created: 2026-04-04
updated: 2026-05-22
---

# Hermes Agent Context Management & Compression Debug

## Architecture de Compression

Deux composants distincts :

1. **`agent/context_compressor.py`** -- Compression LIVE d'une session en cours
   - Sert via `call_llm` (auxiliary_client) avec le `summary_model` du config
   - Se déclenche quand `total_tokens > context_length * threshold`
   - Prune old tool results puis resume middle avec LLM summary
   
2. **`trajectory_compressor.py`** -- Batch post-traitement de JSONL pour training
   - Utilise `google/gemini-3-flash-preview` par defaut
   - Tokenizer: `moonshotai/Kimi-K2-Thinking`
   - NE PAS confondre avec le compresseur de session live

## Diagnostic Rapid

```python
import sqlite3, json

db = '/root/.hermes/state.db'
conn = sqlite3.connect(db)
c = conn.cursor()

# Session overview
c.execute("SELECT id, source, message_count, tool_call_count, ended_at FROM sessions ORDER BY started_at DESC LIMIT 10")
print("=== RECENT SESSIONS ===")
for row in c.fetchall():
    status = "OPEN" if row[4] is None else "CLOSED"
    print(f"  {str(row[0])[:30]}... | {row[1]:8} | msgs={row[2]:3} | tools={row[3]:3} | {status}")

# Message composition
session_id = 'YOUR_SESSION_ID'
c.execute("""
    SELECT role, count(*), avg(length(content)) as avg_len, 
           max(length(content)) as max_len, sum(length(content)) as total
    FROM messages WHERE session_id = ? GROUP BY role
""", (session_id,))
print(f"\n=== MESSAGE COMPOSITION for {session_id} ===")
total_chars = 0
for row in c.fetchall():
    total_chars += row[4]
    print(f"  {row[0]:12} | count={row[1]:4} | avg_len={row[2]:.0f} | max_len={row[3]:,} | total={row[4]:,}")
print(f"  Total chars: {total_chars:,} (~{total_chars//4:,} tokens)")

# Top bloating messages
c.execute("""
    SELECT id, length(content) as len, substr(content, 1, 100)
    FROM messages WHERE session_id = ? AND role = 'tool'
    ORDER BY len DESC LIMIT 5
""", (session_id,))
print(f"\n=== TOP 5 LARGEST TOOL RESPONSES ===")
for row in c.fetchall():
    name = "search" if ("matches" in row[2].lower() or "success" in row[2].lower()) else "file" if "content" in row[2].lower() else "cmd"
    print(f"  Tool#{row[0]}: {row[1]:,} chars - {name}")

conn.close()
```

## Common Bloat Sources

1. **`search_files` results**: File listings 50KB+ par appel
2. **`terminal` output**: ls -la, find, ps aux, etc.
3. **`read_file` outputs**: Gros fichiers lus entierement
4. **`skills_list` output**: Catalogue complet 20KB+ (ne change pas dans une session)
5. **System prompt**: 13KB+ avec SOUL.md + memory + 72 skills (~3K tokens)
6. **Persistent prompt files drift**: `SOUL.md`, `USER.md`, and `MEMORY.md` are all injected; duplicated facts across them become permanent payload bloat.

## Persistent Prompt Files: Placement Rules

Hermes injects three profile-scoped memory/persona files plus optional project context:

| File | Injected as | Correct content | Update path |
|---|---|---|---|
| `~/.hermes/SOUL.md` | stable identity slot | Agent identity, tone, communication rules only | Manual edit; not via memory tool |
| `~/.hermes/memories/USER.md` | `USER PROFILE` volatile block | Who the user is: preferences, habits, corrections, workflows | `memory(target="user")`; refreshes next session/reset |
| `~/.hermes/memories/MEMORY.md` | `MEMORY` volatile block | Durable operational facts not already in config/skills/vault | `memory(target="memory")`; refreshes next session/reset |
| Project context | context block | Repo-local instructions only | `.hermes.md`/`HERMES.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules` |

`USER.md` and `MEMORY.md` writes are durable immediately but do **not** mutate the current session's cached system prompt. Use `/reset` or start a new session to see the updated snapshot.

### Project context priority

`build_context_files_prompt()` loads only the first project-context type found:
1. `.hermes.md` / `HERMES.md` (walks to git root)
2. `AGENTS.md` / `agents.md` (cwd only)
3. `CLAUDE.md` / `claude.md` (cwd only)
4. `.cursorrules` / `.cursor/rules/*.mdc` (cwd only)

Do not store user preferences, secrets, or global agent identity in these files. They are for repo/task-local instructions.

### Cleanup rubric

- Move agent persona/style into `SOUL.md`.
- Move user vocabulary/preferences/workflow expectations into `USER.md`.
- Move durable infra facts and tool quirks into `MEMORY.md`, but avoid secrets, dynamic IPs, stale task state, and facts already obvious from `config.yaml`.
- Move procedures, runbooks, and provider quirks into skills/references, not memory.
- Keep secrets in vault/`.env`, never in injected prompt files.

## Compression Configuration

Location: `~/.hermes/config.yaml`, section `auxiliary.compression:`

```yaml
auxiliary:
  compression:
    provider: gemini          # MUST match a provider that actually hosts the model
    model: gemini-3.1-flash-lite
    base_url: ''
    api_key: ''
    timeout: 120
    extra_body: {}
```

### ⚠️ Pitfall: Provider/Model Mismatch → Silent Compression Failure

**Symptom**: Logs show `No auxiliary LLM provider for compression — summaries will be unavailable.` Context is **dropped without summary** — you lose information instead of getting a compressed version.

**Root cause**: Setting `provider: groq` with `model: gemini-3.1-flash-lite` when Groq does not host Gemini models. The provider initializes but can't serve the model → silent fallback to "drop without summary."

**How to diagnose**:
```bash
# Check logs for compression failures
grep -i "No auxiliary LLM provider" ~/.hermes/logs/agent.log* | tail -5
# Check what models the provider actually has
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer KEY" | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]"
```

**Fix**: Verify the provider hosts the model before configuring it. As of May 2026:
- `provider: gemini` → hosts gemini-3.1-flash-lite, gemini-3.1-pro, etc. (via AI Studio)
- `provider: groq` → hosts Llama, Qwen, Whisper, GPT-OSS only. **No Gemini models.**
- `provider: openrouter` → hosts everything but costs money

**After fixing**: restart gateway (`hermes gateway restart`) — config is loaded at startup only.

### Config structure note

The config uses `auxiliary.compression.provider` and `auxiliary.compression.model` (NOT `summary_model`/`summary_provider` — those are legacy field names from pre-v0.9.0).

### Model-Aware Absolute Thresholds (v0.9.0+)

The compression system now uses **model identity** rather than a raw percentage to decide when to compress. This prevents the classic pitfall where a 1M-context model never compresses at 50%, or a 32K model compresses prematurely.

| Model family | Threshold behavior |
|---|---|
| GPT-5.5 (all variants) | **No compression** — threshold = full context window |
| Everything else | Compress at **~100K tokens**, bounded by `context_length` and `MINIMUM_CONTEXT_LENGTH` (64K) |

The rule is implemented in `ContextCompressor._calculate_threshold_tokens()`:

```python
def _calculate_threshold_tokens(self, model: str, context_length: int) -> int:
    model_lower = (model or "").lower()
    if "gpt-5.5" in model_lower or "gpt5.5" in model_lower:
        return context_length  # never compress
    # Default: ~100K absolute, never exceeding the window, never below floor
    return max(min(100_000, context_length), MINIMUM_CONTEXT_LENGTH)
```

**Why this matters**: GPT-5.5 has a 1M+ context window and excellent recall — compression only degrades quality. Smaller models (GPT-4o, Claude Sonnet, etc.) benefit from early compression at ~100K to keep latency and cost down.

**Aux-model cap**: When the auxiliary compression model has a smaller window than the main model's threshold, the live threshold is capped to the aux model's context length. This cap is stored in `_effective_max_threshold` and respected across model switches.

### Files involved in model-aware compression

| File | Role |
|---|---|
| `agent/context_compressor.py` | `_calculate_threshold_tokens()` + `_effective_max_threshold` handling |
| `run_agent.py` | Startup display + aux-model cap wiring |
| `gateway/run.py` | Session hygiene uses same absolute rule |

See `references/model-aware-compression.patch` for the exact diff.

### Legacy: Percentage-Based Threshold (pre-v0.9.0)

**Pitfall**: `compression.threshold` in `config.yaml` is now **ignored** for threshold calculation. It is still passed to the constructor for backward compatibility but does not affect when compression fires.

**Pitfall historique**: Avec un model a 1M de context et threshold=0.5, la compression ne se declenche JAMAIS en pratique (il faut 500K tokens). Le systeme absolu fixe ce probleme.

### Quand la compression ne se declenche PAS

**Symptome**: 100K+ tokens mais aucune compression.

**Causes possibles** :
1. **Model GPT-5.5** — compression est explicitement desactivee pour cette famille
2. **Config chargee au demarrage uniquement** -- changer le YAML pendant qu'un agent tourne ne l'affecte PAS. Il faut redemarrer le CLI/gateway.
3. **Summary model inaccessible** -- le provider ne host PAS le modèle configuré (ex: `provider: groq` + `model: gemini-3.1-flash-lite` → Groq n'a pas de Gemini). Vérifier les logs pour `No auxiliary LLM provider for compression`.
4. **Compression desactivee** -- `compression.enabled: false` dans config

**Fix** :
1. Verifier le model actif (`/model` ou config.yaml)
2. Redemarrer le processus (`hermes chat` ou gateway) pour recharger la config
3. Compaction manuelle via DB editing si besoin urgent (voir ci-dessous)

### Algorithme de Compression

1. **Prune old tool results** -- remplace vieux outputs par `[Old tool output cleared to save context space]` (cheap, pas de LLM)
2. **Protected head** -- premier messages (system + premier echange)
3. **Protected tail** -- derniers N messages (token budget, pas count fixe)
4. **Summarize middle** -- LLM summary structure avec template:
   - Goal
   - Progress  
   - Decisions
   - Files
   - Next Steps
5. **Iterative update** -- si compression precedente existe, enrichit le summary existant

## Prompt Injection Payload Audit

When the user asks what is injected on every call, or when SOUL/USER/MEMORY feel duplicated, audit the prompt builder before editing memory files. Hermes injects:

- Stable tier: `SOUL.md`, tool guidance, model guidance, skills index, environment/platform hints.
- Context tier: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/*.mdc`, `.hermes.md`/`HERMES.md`, plus caller `system_message`.
- Volatile tier: `MEMORY.md`, `USER.md`, external memory provider block such as Hindsight, date/model/provider metadata.

Use `references/prompt-injection-audit.md` for the cleanup workflow and file-responsibility table. Keep responsibilities separated: `SOUL.md` = agent identity/style, `USER.md` = user preferences/constraints, `MEMORY.md` = durable operational facts not already in config/vault/skills. Never store raw secrets in injected memory; store only a pointer like “token in vault”.

### Cleanup workflow

1. Measure sizes and duplicate terms for `SOUL.md`, `USER.md`, and `MEMORY.md`.
2. Check cwd context files before blaming memory bloat.
3. Back up all three files before rewriting.
4. Move each fact to its correct layer rather than deleting blindly.
5. Restart gateway or start a fresh session because system prompts are cached per agent session.

## Iteration Limits & Provider Connection Errors

### Diagnostic: "maximum iterations (N) but couldn't summarize. Error: ConnectionError"

**What happens**: A subagent (delegate_task) or cron job hits the iteration cap, then the final LLM call to produce a summary fails with `APIConnectionError`. The user sees the raw error because there's no graceful fallback.

**Root cause chain**:
1. Task is complex enough to exhaust all iterations (60+ tool calls)
2. Session lasted long enough for the TCP connection to the provider to drop
3. The summary call fails — retries also fail against the same stale/dead connection

**Diagnosis**:
```bash
# Find the failing provider and session
grep -i "APIConnectionError\|Connection error" ~/.hermes/logs/agent.log | tail -20
grep -i "APIConnectionError\|Connection error" ~/.hermes/logs/errors.log* | tail -20

# Check provider latency profile (cold start pattern)
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w "Attempt $i: %{http_code} %{time_total}s\n" \
    --connect-timeout 5 --max-time 10 https://PROVIDER_ENDPOINT/v1/models \
    -H "Authorization: Bearer test"
  sleep 1
done
```

**Symptom pattern in logs**: Repeated `API call failed (attempt N/3) error_type=APIConnectionError provider=... base_url=... summary=Connection error.` — the provider and base_url tell you exactly which endpoint is flaky.

### Config Knobs (Iteration Limits)

| Config key | Default | Controls |
|---|---|---|
| `agent.max_turns` | 60 | Main agent loop iterations |
| `delegation.max_iterations` | 50 | Subagent (delegate_task) iterations |
| `delegation.child_timeout_seconds` | 600 | Subagent wall-clock timeout (seconds) |
| `code_execution.max_tool_calls` | 50 | execute_code script tool call limit |

**Rule of thumb**: If users report "couldn't summarize" errors, increase the relevant limit AND the timeout proportionally. 80 iterations needs ~1200s (20 min).

### Config Knobs (Provider Stability)

| Config key | Default | Controls |
|---|---|---|
| `agent.api_max_retries` | 3 | Retry attempts per API call |
| `providers.<id>.request_timeout_seconds` | ~30s (SDK default) | Per-request HTTP timeout |
| `providers.<id>.stale_timeout_seconds` | None | Connection staleness detection |

**Recommended for unstable providers** (e.g., GitLawb cold start):
```yaml
agent:
  api_max_retries: 5
providers:
  gitlawb:
    request_timeout_seconds: 120
    stale_timeout_seconds: 180
```

### Pitfall: Provider Cold Start Latency

Some providers (observed with GitLawb/opengateway) exhibit 2-3.5s latency on initial requests, then stabilize to <100ms. During long sessions (20+ minutes), the connection can go idle and the next request hits the cold path again. Setting `request_timeout_seconds: 120` absorbs these spikes. The `stale_timeout_seconds` setting helps the client detect and replace dead connections before they cause cascading failures.

### Pitfall: max_turns vs max_iterations Naming

- `agent.max_turns` controls the **main agent** loop (what the user interacts with)
- `delegation.max_iterations` controls **subagents** (delegate_task children)
- The error message "maximum iterations (60)" refers to whichever limit the agent hit — match the number to identify which one
- `code_execution.max_tool_calls` is separate and only governs `execute_code` scripts

## Optimization Strategies

### Prevent bloat at source
- Ne pas appeler `skills_list` repetitivement
- Utiliser `search_files` avec `file_glob` specifique
- Lire uniquement les sections utiles: `read_file(offset=X, limit=Y)`

### Session management
- `group_sessions_per_user: false` pour isoler les contextes par plateforme
- Fermer les sessions via `UPDATE sessions SET ended_at=time.time() WHERE source='telegram' AND ended_at IS NULL`
- Utiliser `/reset` pour clear le contexte entier

### Compaction manuelle (workaround)

Quand le compresseur ne se declenche pas mais que tu DOIS reduire le contexte :

```python
import sqlite3, time

db = '/root/.hermes/state.db'
conn = sqlite3(db)
c = conn.cursor()

session_id = 'YOUR_SESSION_ID'

# Option A: Pruner les tool responses anciens
# Garder les 10 derniers, remplacer les autres par placeholder
c.execute("""
    SELECT rowid FROM messages 
    WHERE session_id = ? AND role = 'tool'
    ORDER BY rowid DESC
""", (session_id,))
rows = c.fetchall()
keep_last = 10
for i, (rowid,) in enumerate(rows):
    if i >= keep_last:
        c.execute("UPDATE messages SET content='[Pruned to save context]' WHERE rowid=?", (rowid,))

# Option B: Supprimer les tool responses inutiles (search_files, skills_list)
c.execute("""
    UPDATE messages SET content = '[Pruned]'
    WHERE session_id = ? AND role = 'tool'
    AND (content LIKE '%"success": true, "skills"%' 
         OR content LIKE '%__pycache__%')
""", (session_id,))

conn.commit()
conn.close()
```

**ATTENTION**: Ne pas toucher les messages `user` ou `assistant`, seulement les `tool` responses.
