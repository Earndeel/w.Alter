## Architecture

```
Hermes Gateway
  └─ Plugin: plugins/memory/hindsight/__init__.py (1044 lines)
       ├─ mode: local_embedded → uses `from hindsight import HindsightEmbedded`\n       ├─ mode: cloud → uses hindsight-client, hits api.hindsight.vectorize.io\n       └─ mode: local_external → hits api_url (e.g. http://127.0.0.1:8888)\n           └─ hindsight-api (systemd, uvicorn) → external Docker PG\n\n⚠️ The plugin ONLY recognizes: cloud, local_embedded, local_external.\n   There is NO \"local_api\" mode — it will silently fail or fall back to cloud.
```

**Config:** `/root/.hermes/hindsight/config.json`
**Env:** `/root/.hermes/hindsight/.env`
**Logs:** `/root/.hermes/logs/hindsight-embed.log`, `/root/.hermes/logs/hindsight-api.log`

## Installed Packages (as of 2026-04-26)

```
hindsight-client  0.5.2   # HTTP client for API mode
hindsight-embed   0.5.2   # Embedded mode support
hindsight-api     0.5.2   # Server (in venv, entry_points)
```

**Latest available:** 0.5.4 (2026-04-22). Key changes in 0.5.3/0.5.4:
- LLM_MAX_RETRIES reduced from 10→3 (avoids retry loops)
- Race condition fix in consolidation (orphan prevention)
- Adaptive recall budget mode (proportional to max_tokens)
- Consolidation max_memories_per_round=100 (prevents worker hogging)
- Structured mental models (delta ops, no prose drift on refresh)
- 5 new DB migrations (run automatically at startup)
- No breaking changes, upgrade is safe

## Current Production Setup (2026-04-26)

**Mode:** `local_api` (NOT `local_embedded`)
**API:** systemd service `hindsight-api` on port 8888
**DB:** External PG container `hindsight-pg` at 172.17.0.3:5432 (trust auth via Docker bridge)
**LLM:** gemini / gemini-3.1-flash-lite-preview
**Embeddings:** Google / gemini-embedding-2-preview (768-dim)
**Reranker:** zeroentropy / zerank-2 (ZeRank-2 API, with FlashRank as fallback)
**Bank:** walter

```bash
# Service management
systemctl status hindsight-api
systemctl restart hindsight-api
journalctl -u hindsight-api -f

# Health check
curl http://127.0.0.1:8888/health

# Config files
/root/.hermes/hindsight/config.json          # mode, bank_id, llm settings
/root/.hermes/hindsight/.env                 # template (keys masked)
/root/.hermes/hindsight/.env.service         # real keys (sourced by systemd)
/etc/systemd/system/hindsight-api.service    # systemd unit
/root/.hermes/logs/hindsight-api.log         # logs
```

### Key changes from default setup:
1. PG runs in Docker container, NOT embedded pg0 (avoids root user crash)
2. Trust auth for Docker bridge network (172.16.0.0/12) in pg_hba.conf
3. Alembic stamped to head (old data had 384-dim embeddings, dropped for fresh 768-dim)
4. LLM uses Gemini 3.1 Flash Lite (cheapest tier, sufficient for extraction)
5. Embeddings use Google Gemini (quality matters for semantic search)
6. Reranker uses ZeRank-2 (ZeroEntropy API) — FlashRank as fallback

## Docker Container: hindsight-pg

```
docker ps | grep hindsight-pg
# pgvector/pgvector:pg16, user=hindsight, db=hindsight, port=5432 (internal)
```

**Critical:** The container ships pgvector BUT the extension is NOT created by default.
After first init, you must:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
Without this, the API crashes on schema creation.

## Production Setup: local_external mode with external Docker PG (RECOMMENDED)

This is the cleanest and most reliable approach. Bypasses all embedded pg0 root issues entirely. No LD_PRELOAD hack needed.

⚠️ Use `"mode": "local_external"` — NOT `"local_api"`. The plugin does NOT recognize `local_api`.
   The plugin's valid modes are: `cloud`, `local_embedded`, `local_external`.

### Architecture
```
hindsight-pg (Docker container, pgvector/pgvector:pg16)
  └─ port 5432, accessible via bridge IP 172.17.0.3
  └─ data in Docker volume `hindsight-data`

hindsight-api (systemd service, NOT Docker)
  └─ port 8888, connects to PG via bridge IP
  └─ LLM: gemini / gemini-3-flash-preview
  └─ Embeddings: google / gemini-embedding-2-preview (768-dim)
```

### Step 1: Make PG accessible from host (no password)

The PG container has no port mapping by default. Add trust auth for the Docker bridge network:

```bash
# Add trust rule BEFORE scram-sha-256 (PostgreSQL uses first-match)
docker exec hindsight-pg bash -c "
sed -i '/^host all all 172.16.0.0/d' /var/lib/postgresql/data/pg_hba.conf
sed -i '/^host all all all scram-sha-256/i host all all 172.16.0.0/12 trust' /var/lib/postgresql/data/pg_hba.conf
"
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT pg_reload_conf();"
```

**CRITICAL:** The trust rule MUST appear BEFORE the `scram-sha-256` line. PostgreSQL pg_hba.conf is first-match — if scram-sha-256 comes first, it blocks the trust rule.

Verify order: `docker exec hindsight-pg cat /var/lib/postgresql/data/pg_hba.conf | grep -v "^#" | grep -v "^$"`

### Step 2: Ensure extensions exist

```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -c "
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"
```

### Step 3: Create systemd service

Create `/etc/systemd/system/hindsight-api.service`:
```ini
[Unit]
Description=Hindsight Memory API
After=docker.service network.target
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/.hermes/hermes-agent
Environment=HINDSIGHT_API_DATABASE_URL=postgresql://hindsight@172.17.0.3:5432/hindsight
Environment=HINDSIGHT_API_LLM_PROVIDER=gemini
Environment=HINDSIGHT_API_LLM_MODEL=gemini-3.1-flash-lite-preview
Environment=HINDSIGHT_API_LLM_MAX_RETRIES=3
Environment=HINDSIGHT_API_EMBEDDINGS_PROVIDER=google
Environment=HINDSIGHT_API_EMBEDDINGS_GEMINI_MODEL=gemini-embedding-2-preview
Environment=HINDSIGHT_API_EMBEDDINGS_OPENAI_BATCH_SIZE=100
Environment=HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy
Environment=HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL=zerank-2
Environment=HINDSIGHT_API_RERANKER_MAX_CANDIDATES=40
EnvironmentFile=/root/.hermes/hindsight/.env.service
ExecStart=/root/.hermes/hermes-agent/venv/bin/hindsight-api --host 127.0.0.1 --port 8888
Restart=on-failure
RestartSec=5
StandardOutput=append:/root/.hermes/logs/hindsight-api.log
StandardError=append:/root/.hermes/logs/hindsight-api.log

[Install]
WantedBy=multi-user.target
```

Create `/root/.hermes/hindsight/.env.service` with REAL API keys (not masked):
```bash
GEMINI_KEY=$(vault get gemini/api_key)
cat > /root/.hermes/hindsight/.env.service << EOF
HINDSIGHT_API_LLM_API_KEY=${GEMINI_KEY}
HINDSIGHT_API_EMBEDDINGS_GEMINI_API_KEY=${GEMINI_KEY}
HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=<zeroentropy_key>
EOF
chmod 600 /root/.hermes/hindsight/.env.service
```

### Step 4: Update config.json

```json
{
    "mode": "local_external",
    "api_url": "http://127.0.0.1:8888",
    "bank_id": "walter",
    "recall_budget": "mid",
    "recall_prefetch_method": "recall",
    "auto_recall": true,
    "auto_retain": true,
    "retain_async": true,
    "retain_every_n_turns": 2,
    "memory_mode": "hybrid",
    "timeout": 30
}
```

⚠️ Must be `"local_external"` with `"api_url"`. The plugin reads `api_url` only when mode is `local_external`.
   LLM/embedding settings go in the systemd service env vars, NOT in config.json.

### Step 5: Start and verify

```bash
systemctl daemon-reload
systemctl enable hindsight-api
systemctl start hindsight-api
# Wait ~25s for reranker model to load (cross-encoder/ms-marco-MiniLM-L-6-v2)
sleep 25
curl -s http://127.0.0.1:8888/health
# Should return: {"status":"healthy","database":"connected"}
```

### Step 6: Restart Hermes gateway

⚠️ NEVER `kill -9` the gateway from inside an agent session — it kills the session
and forces manual relaunch. Use one of these instead:

```bash
# Option A: SIGUSR1 (graceful drain, gateway exits with code 75, systemd restarts)
kill -USR1 $(python3 -c "import json; print(json.load(open('/root/.hermes/gateway_state.json'))['pid'])")

# Option B: systemctl restart (also kills session, but at least systemd handles lifecycle)
systemctl restart hermes-gateway

# Option C: Scheduled restart (safest from inside agent session)
/root/.hermes/scripts/gateway-restart.sh --delay 5
```

After restart, send any message to resume the session (gateway preserves sessions in SQLite).

## Repair Steps (if starting fresh)

**RECOMMENDED:** Use the Production Setup section above (local_external + external Docker PG). It avoids all embedded pg0 root issues entirely.

Legacy quick steps:
1. Ensure pgvector in container:
   ```bash
   docker exec hindsight-pg psql -U hindsight -d hindsight -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

2. Start hindsight-api pointing to external PG:
   ```bash
   cd /root/.hermes/hermes-agent && source venv/bin/activate
   export HINDSIGHT_API_DATABASE_URL="postgresql://hindsight@172.17.0.3:5432/hindsight"
   export HINDSIGHT_API_EMBEDDINGS_PROVIDER=google   # NOT "gemini"
   hindsight-api --host 127.0.0.1 --port 8888
   ```

3. Update config to use `local_external` mode:
   ```json
   {"mode": "local_external", "api_url": "http://127.0.0.1:8888", "bank_id": "walter"}
   ```

4. Restart Hermes gateway to reload plugin.

## Memory Stack Architecture (4 layers)

### Layer 1: Working Memory
- `protect_last_n: 15` — last 15 messages protected from compression
- Old tool outputs auto-pruned: `[Old tool output cleared to save context space]`
- Config: `config.yaml → compression.protect_last_n`

### Layer 2: Intelligent Compression
- Triggered at 10% context window (`threshold: 0.10`)
- Compresses to 10% (`target_ratio: 0.10`)
- Uses auxiliary model (qwen/qwen3.6-plus:free) for summarization
- Structured summaries with Resolved/Pending question tracking
- Protects head (system prompt) and tail (recent 15 messages)
- **Tool outputs**: auto-pruned with informative summaries
- **Thinking blocks**: auto-stripped from old messages (Phase 1b)
- Config: `config.yaml → compression.*`

### Layer 3: GraphRAG (Hindsight)
- `prefetch()` — injects relevant memories at session start (targeted, not dump)
- `sync_turn()` — auto-retains after each user/assistant turn
- `queue_prefetch()` — background prefetch for next turn
- Entity resolution + knowledge graph automatic
- Config: `/root/.hermes/hindsight/config.json`

### Layer 4: Support
- Health check cron: every 30m, checks API + service
- Dreaming cron: every 6h, runs `/root/.hermes/scripts/memory_dreaming.py`
  - Consolidation (deduplicate, merge)
  - Entity graph maintenance
  - Mental model generation
  - Health reporting
- Cron job IDs: health=`fa8c6bdcc442`, dreaming=`13d0f88771cb`
