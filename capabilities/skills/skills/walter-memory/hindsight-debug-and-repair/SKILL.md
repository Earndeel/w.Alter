---
name: hindsight-debug-and-repair
category: devops
description: Debug and repair Hindsight memory system for Hermes — diagnosis of common failures (module missing, root PG crash, empty DB) and repair steps.
tags: [hindsight, memory, postgresql, pgvector, debug, hermes]
created: 2026-04-22
---

# Hindsight Debug & Repair

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

## Key Finding: `hindsight` package ≠ `hindsight-embed` (API mismatch v0.5.2)

The plugin does `from hindsight import HindsightEmbedded` — but the pip package
is called `hindsight-embed`, not `hindsight`. The import fails with:
`ModuleNotFoundError: No module named 'hindsight'`

This is the #1 failure mode. The embed log will show this error repeated in a loop.

**What changed in hindsight-embed ≥0.5:**
- Old API: `from hindsight import HindsightEmbedded` → class with `._manager`, `._ensure_started()`
- New API: `from hindsight_embed import get_embed_manager` → returns `DaemonEmbedManager` with:
  - `.ensure_running(config: dict, profile: str) → bool`
  - `.get_url(profile: str) → str`
  - `.is_running(profile: str) → bool`
  - `.stop(profile: str)`

The Hermes plugin (as of 2026-04-24) still expects the old API and crashes.

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

## Failure Mode 1: ModuleNotFoundError (local_embedded)

**Symptom:** `hindsight-embed.log` full of `No module named 'hindsight'`
**Cause:** Plugin imports `from hindsight import HindsightEmbedded` but package name is `hindsight-embed`
**Fix options:**

### Option A — Compatibility shim (quick fix)

Create the shim in **both** the system Python site-packages and the Hermes venv:

```bash
# System Python (3.12)
mkdir -p /usr/local/lib/python3.12/dist-packages/hindsight
# Hermes venv (3.11)
mkdir -p /root/.hermes/hermes-agent/venv/lib/python3.11/site-packages/hindsight
```

Write this to both `hindsight/__init__.py` locations:

```python
"""Shim: exposes HindsightEmbedded for the Hermes hindsight memory plugin.

Wraps hindsight_embed (daemon manager) + hindsight_client (API client)
so the plugin's local_embedded mode works with hindsight-embed >=0.5.
"""

import logging
from hindsight_embed import get_embed_manager
from hindsight_client import Hindsight

logger = logging.getLogger(__name__)


class HindsightEmbedded(Hindsight):
    """Local embedded Hindsight client that manages its own daemon."""

    def __init__(
        self,
        profile: str = "hermes",
        llm_provider: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
        llm_base_url: str | None = None,
    ):
        self._profile = profile
        self._daemon_config: dict[str, str] = {
            "HINDSIGHT_API_LLM_PROVIDER": llm_provider or "",
            "HINDSIGHT_API_LLM_API_KEY": llm_api_key or "",
            "HINDSIGHT_API_LLM_MODEL": llm_model or "",
        }
        if llm_base_url:
            self._daemon_config["HINDSIGHT_API_LLM_BASE_URL"] = llm_base_url

        self._manager = get_embed_manager()
        self._ensure_started()

        base_url = self._manager.get_url(profile)
        super().__init__(base_url=base_url, timeout=30.0)
        logger.debug(
            "HindsightEmbedded initialised for profile '%s' at %s",
            profile,
            base_url,
        )

    def _ensure_started(self) -> None:
        """Start the local daemon if it is not already running."""
        try:
            self._manager.ensure_running(self._daemon_config, self._profile)
        except Exception as e:
            logger.error(
                "Failed to start Hindsight daemon for profile '%s': %s",
                self._profile,
                e,
            )
            raise
```

**Why both locations?** The Hermes gateway runs in the venv, but the daemon manager may spawn subprocesses that inherit the system Python path. Installing in both prevents `ModuleNotFoundError` regardless of which interpreter loads the module.

### Option B — Switch to local_external or cloud mode
Change `/root/.hermes/hindsight/config.json` to use `"mode": "local_external"` (with `"api_url"`) or `"mode": "cloud"` instead of `"local_embedded"`.

## Failure Mode 2: Root user crash (embedded PostgreSQL pg0)

**Symptom:** After fixing the import (shim or otherwise), `hindsight-api.log` shows:
```
RuntimeError: Failed to start embedded PostgreSQL after 5 attempts.
initdb: error: cannot be run as root
initdb: hint: Please log in (using, e.g., "su") as the (unprivileged) user...
```
**Cause:** `hindsight-api` (launched by `hindsight-embed` daemon) tries to start embedded PostgreSQL (pg0), but PostgreSQL `initdb` **refuses to run as root**.
**Fix options:**

### Option A — LD_PRELOAD UID spoof (run pg0 as root)

Build a fake-uid shared library that makes `getuid()` return 1000 instead of 0:

```bash
cat > /tmp/fakeuid.c << 'EOF'
#define _GNU_SOURCE
#include <unistd.h>
#include <sys/types.h>
uid_t getuid(void) { return 1000; }
uid_t geteuid(void) { return 1000; }
gid_t getgid(void) { return 1000; }
gid_t getegid(void) { return 1000; }
EOF
gcc -shared -fPIC -o /tmp/fakeuid.so /tmp/fakeuid.c
```

Wrap the three PostgreSQL binaries that check UID:

```bash
PG_BIN="/root/.pg0/installation/18.1.0/bin"

# initdb — also chown the datadir to UID 1000 after init
mv "$PG_BIN/initdb" "$PG_BIN/initdb.real"
cat > "$PG_BIN/initdb" << 'EOF'
#!/bin/bash
export LD_PRELOAD=/tmp/fakeuid.so
DATADIR=""
for ((j=0; j<$#; j++)); do
  arg="${!j}"
  [[ "$arg" == "-D" || "$arg" == "--pgdata" ]] && DATADIR="${!((j+1))}"
  [[ "$arg" == -D* ]] && DATADIR="${arg#-D}"
  [[ "$arg" == --pgdata=* ]] && DATADIR="${arg#--pgdata=}"
done
[ -n "$DATADIR" ] && mkdir -p "$DATADIR" && chown -R 1000:1000 "$DATADIR"
exec "$PG_BIN/initdb.real" "$@"
EOF
chmod +x "$PG_BIN/initdb"

# postgres server
mv "$PG_BIN/postgres" "$PG_BIN/postgres.real"
printf '#!/bin/bash\nexport LD_PRELOAD=/tmp/fakeuid.so\nexec "$PG_BIN/postgres.real" "$@"\n' > "$PG_BIN/postgres"
chmod +x "$PG_BIN/postgres"

# pg_ctl
mv "$PG_BIN/pg_ctl" "$PG_BIN/pg_ctl.real"
printf '#!/bin/bash\nexport LD_PRELOAD=/tmp/fakeuid.so\nexec "$PG_BIN/pg_ctl.real" "$@"\n' > "$PG_BIN/pg_ctl"
chmod +x "$PG_BIN/pg_ctl"
```

After this, `hindsight-embed daemon start` works even as root. The daemon auto-creates the pg0 instance under `~/.pg0/instances/hindsight-embed-<profile>`.

### Option B — Use external PG container or cloud mode
See Repair Steps below.

**Note:** This error appears in `~/.hindsight/profiles/<profile>.log`, not in `/root/.hermes/logs/`.

## Failure Mode 3: Plugin writes literal `***` as API key

**Symptom:** Daemon starts but API calls fail with 401/auth errors.
**Cause:** The plugin's `_start_daemon()` method (line ~701) writes the profile `.env` file but hardcodes the key as `HINDSIGHT_API_LLM_API_KEY=***` instead of the real key value. The `current_key` variable is masked before writing.
**Workaround:** Manually edit `~/.hindsight/profiles/<profile>.env` after the plugin creates it, and replace `***` with the real `HINDSIGHT_LLM_API_KEY` value.

## Failure Mode 4: Empty database (no tables)
**Symptom:** `docker exec hindsight-pg psql -U hindsight -d hindsight -c "\dt"` returns 0 rows
**Cause:** API never completed initialization, so schema was never created
**Fix:** After fixing mode 1 or 2, the API auto-creates tables on first start.
Verify pgvector extension exists first:
```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT extname FROM pg_extension;"
# Should show: plpgsql AND vector
```

## Failure Mode 5: Alembic revision mismatch
**Symptom:** `RuntimeError: Database migration failed` → `Can't locate revision identified by '8c6fa6f7230b'`
**Cause:** The alembic_version table in the DB references a revision that doesn't exist in the current code's migration scripts. Happens when DB was created by a different hindsight-api version.
**Fix:**
```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -c "DELETE FROM alembic_version;"
# Then stamp to current head (don't upgrade — tables may already exist)
cd /root/.hermes/hermes-agent && source venv/bin/activate
python3 -c "
import os
os.environ['HINDSIGHT_API_DATABASE_URL'] = 'postgresql://hindsight@172.17.0.3:5432/hindsight'
from alembic.config import Config
from alembic import command
cfg = Config('venv/lib/python3.11/site-packages/hindsight_api/alembic.ini')
cfg.set_main_option('script_location', 'venv/lib/python3.11/site-packages/hindsight_api/alembic')
cfg.set_main_option('sqlalchemy.url', 'postgresql://hindsight@172.17.0.3:5432/hindsight')
command.stamp(cfg, 'head')
"
```

## Failure Mode 6: Embedding dimension mismatch
**Symptom:** `RuntimeError: Cannot change embedding dimension from 384 to 768: memory_units table contains N rows with embeddings`
**Cause:** Existing data was embedded with a different model (e.g. local 384-dim). New model (e.g. Gemini 768-dim) can't reuse old vectors.
**Fix — nuclear option (drop + recreate schema):**
```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO hindsight;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"
# Then restart the API — it will recreate all tables with correct dimensions
```
**WARNING:** This deletes ALL stored memories. Only do this when changing embedding models.

## Failure Mode 7: Embeddings provider name wrong
**Symptom:** `ValueError: Unknown embeddings provider: gemini. Supported: 'local', 'tei', 'openai', 'cohere', 'google', 'litellm', 'litellm-sdk'`
**Cause:** Config uses `HINDSIGHT_API_EMBEDDINGS_PROVIDER=gemini` but the correct name is `google`.
**Fix:** Set `HINDSIGHT_API_EMBEDDINGS_PROVIDER=google` (not `gemini`).

## Failure Mode 8: systemd Environment= overrides .env file
**Symptom:** Hindsight runs on a different (more expensive) model than what `.env` or `.env.service` specifies.
**Cause:** The systemd unit file has `Environment=HINDSIGHT_API_LLM_MODEL=gemini-3.1-pro-preview` hardcoded. Systemd `Environment=` inline vars take precedence over `EnvironmentFile=` — the .env file is loaded first, then inline vars overwrite it. This caused the system to run on Gemini 3.1 Pro ($2/M input) instead of Flash Lite ($0.05/M) for 2 weeks, costing ~$50.
**Fix:**
```bash
# 1. Check what the running process actually uses
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep HINDSIGHT_API_LLM_MODEL

# 2. If it differs from .env.service, fix the systemd unit
sed -i 's/HINDSIGHT_API_LLM_MODEL=.*/HINDSIGHT_API_LLM_MODEL=gemini-3.1-flash-lite-preview/' /etc/systemd/system/hindsight-api.service

# 3. Reload and restart
systemctl daemon-reload && systemctl restart hindsight-api

# 4. Verify
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep HINDSIGHT_API_LLM_MODEL
```
**Rule:** Never put model/provider overrides in `Environment=` lines in the systemd unit. Put ALL config in `EnvironmentFile=` only. Inline `Environment=` is a trap — it silently overrides the file and is invisible when you inspect the .env file.

## Failure Mode 9: Wrong reranker provider (FlashRank instead of ZeRank-2)
**Symptom:** Reranker is `flashrank ms-marco-MiniLM-L-12-v2` but should be `zeroentropy zerank-2`.
**Cause:** The systemd unit was created with FlashRank as default. ZeRank-2 was added later but the unit wasn't updated.
**Fix:**
```bash
# Update systemd unit
sed -i 's/HINDSIGHT_API_RERANKER_PROVIDER=flashrank/HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy/' /etc/systemd/system/hindsight-api.service
sed -i 's/HINDSIGHT_API_RERANKER_FLASHRANK_MODEL=.*/HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL=zerank-2/' /etc/systemd/system/hindsight-api.service
# Add API key if missing
grep -q ZEROENTROPY_API_KEY /etc/systemd/system/hindsight-api.service || \
  sed -i '/HINDSIGHT_API_RERANKER_MAX_CANDIDATES/a Environment=HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=<key>' /etc/systemd/system/hindsight-api.service
systemctl daemon-reload && systemctl restart hindsight-api
```

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

## API Endpoints (v0.5.2)

Retain (store memories):
```
POST /v1/default/banks/{bank_id}/memories
{
  "items": [
    {"content": "fact text", "context": "optional context", "document_id": "optional"}
  ],
  "async": false
}
```
**CRITICAL:** Body requires `items` array, NOT a direct `content` field.

Recall (search):
```
POST /v1/default/banks/{bank_id}/memories/recall
{"query": "search text", "limit": 5}
```

List all:
```
GET /v1/default/banks/{bank_id}/memories/list
```

Stats:
```
GET /v1/default/banks/{bank_id}/stats/memories-timeseries
```

## Prometheus Metrics (detailed timing)

The `/metrics` endpoint exposes detailed histograms. Key metrics for performance analysis:

```bash
# Get all hindsight metrics (filtered from Prometheus exposition format)
curl -s http://127.0.0.1:8888/metrics | grep '^hindsight_' | grep -v '_bucket' | grep -v '_created'
```

### Key metric families:
- `hindsight_llm_duration_seconds_sum` — LLM call durations by scope:
  - `retain_extract_facts`: avg ~15.7s per call (gemini-3.1-flash-lite-preview)
  - `consolidation`: avg ~156s per call (2.6 min!)
  - `reflect`: avg ~8.2s per call
  - `reflect_tool_call`: avg ~63.8s per call
- `hindsight_operation_duration_seconds_sum` — End-to-end operation durations:
  - `recall` (budget=mid): avg ~2.38s across 151 calls
  - `retain`: avg ~7.53s across 10 calls
- `hindsight_http_duration_seconds_sum` — Per-endpoint HTTP durations
- `hindsight_db_pool_*` — Connection pool stats

### Automated test scripts (production-ready)
```bash
# Full test suite (10 tests, exit code 0=pass, 1=fail)
python3 /root/.hermes/scripts/test_hindsight.py --verbose

# Component speed benchmark (uses Prometheus /metrics)
python3 /root/.hermes/scripts/bench_hindsight.py
```
Both scripts auto-cleanup test data they create.

### Component Speed Reference (Prometheus /metrics, 2026-04-26)

Use `/metrics` endpoint for internal timings — `trace=true` does NOT expose phase timings.

| Component | Avg Latency | Source |
|---|---|---|
| Recall end-to-end | 2.36s | `hindsight_operation_duration_seconds` (budget=mid) |
| Retain end-to-end | 7.53s | `hindsight_operation_duration_seconds` |
| LLM extract_facts | 15.7s/call | `hindsight_llm_duration_seconds` (scope=retain_extract_facts) |
| LLM consolidation | 155.9s/call | `hindsight_llm_duration_seconds` (scope=consolidation) |
| LLM reflect | 8.2s/call | `hindsight_llm_duration_seconds` (scope=reflect) |
| Health check | 0.002s | `hindsight_http_duration_seconds` |
| Entities list | 0.005s | `hindsight_http_duration_seconds` |
| Entity graph | 0.007s | `hindsight_http_duration_seconds` |

**Bottleneck:** Cross-encoder rerank = 68% of recall latency (~1.6s out of 2.36s total).

24. **Gemini model name suffix:** `gemini-3.1-flash-lite` returns 403 Forbidden. The correct name is `gemini-3.1-flash-lite-preview`. This applies everywhere: systemd env vars, Python script defaults, Hindsight config. Always include `-preview` suffix. This broke `dream_cycle.py` silently — the merge task failed while health checks passed, masking the issue for 14 days.
25. **Script corruption from key redaction:** When tools or scripts redact API keys from Python source files, they can corrupt `os.getenv()` calls. Pattern: `os.getenv("OPENROUTER_API_KEY", "")` becomes `os.get...EY", "")` (truncated, unterminated string literal). Check with `python3 -c "import py_compile; py_compile.compile('script.py', doraise=True)"` after any automated key redaction. Also `grep -rn 'os\.get\.\.\.' /root/.hermes/scripts/ /root/.hermes/services/` to find corrupted files.
26. **Guarded maintenance max_delete too low:** The `memory-guarded-maintenance` systemd service default `--max-delete 50` is too low for active systems. With 174 duplicate groups and 251 excess rows, the guard blocks every run. Set `--max-delete 200` in the systemd unit. Check with: `cat /root/.hermes/logs/memory-autopilot/pg-exact-dedup-latest.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'blocked={d.get(\"blocked\")} reason={d.get(\"reason\")}')"`
27. **PG query patterns:** The `memory_units` table has NO `norm_text` column. For exact duplicate detection, use `md5(text)` grouping. Table name is `entities` NOT `memory_entities`. Use `docker exec hindsight-pg psql -U hindsight -d hindsight -c "..."` since psql is not installed on the host.
28. **Cron failures from provider cascading:** When the primary provider AND fallback both have connection errors simultaneously (e.g. 3AM UTC), cron jobs fail silently. The job's `last_status: error` is the only signal. Check: `grep "APIConnectionError" /root/.hermes/logs/gateway.log | tail -20`

## Full Stack Audit

See `references/full-stack-audit.md` for the complete step-by-step audit procedure (infrastructure health, data volume, duplicates, systemd timers, crons, script validation, PG/Qdrant drift interpretation).

## Diagnostic Checklist

```bash
# 1. Check if API is running
curl -s http://127.0.0.1:8888/health
ss -tlnp | grep 8888

# 2. Check PG container
docker ps | grep hindsight-pg
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT extname FROM pg_extension;"

# 3. Check embed log for errors
tail -30 /root/.hermes/logs/hindsight-embed.log

# 4. Check API log for errors
tail -30 /root/.hermes/logs/hindsight-api.log

# 5. Check installed packages
venv/bin/pip list | grep hindsight

# 6. Check config
cat /root/.hermes/hindsight/config.json
```

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

## Qdrant Vector Store (2026-04-27 — replaces PG for vector search)

**Deployment:** Docker container `qdrant` on Oracle ARM (aarch64), ports 6333 (API) / 6334 (gRPC)
```bash
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant-data:/qdrant/storage \
  qdrant/qdrant:latest
```

**Collections:**
- `memories` — dense vectors (768d), payload: text, bank_id, source, tags, fact_type, timestamps, access_count, metadata
- `entities` — dense vectors (768d), payload: name, entity_type, bank_id, observations, properties

**Performance vs PG:**
| Backend | Vector search (264 memories) | Notes |
|---|---|---|
| PG (pgvector) | ~200ms | Docker container at 172.17.0.3 |
| **Qdrant** | **~5ms** | 40x faster, same data |

**Migration script:** `/root/.hermes/scripts/migrate_pg_to_qdrant.py`
- Exports memory_units + entities from PG with embeddings
- Generates BM25 sparse vectors (hash-based) for hybrid search
- Upserts into Qdrant collections
- Usage: `HINDSIGHT_PG_PASSWORD=<pass> python3 migrate_pg_to_qdrant.py`

**Pitfall: BM25 sparse vectors** — The hash-based sparse vector approach (python hash → sparse indices) does NOT produce consistent indices between query and stored documents. Dense search alone is sufficient for <1000 memories. For 10k+ memories, use Qdrant's built-in text index or a proper BM25 vocabulary.

**Pitfall: FlashRank passage format** — FlashRank expects passages as dicts with "text" key:
```python
# WRONG: passages=["text1", "text2"]
# RIGHT: passages=[{"text": "text1"}, {"text": "text2"}]
```
And returns `{"text": "...", "score": float32}` (NOT `{"rank": ..., "score": ...}`). Match back to original docs by text content.

## Hybrid Search Service (2026-04-27)

Standalone FastAPI service on port 8889 — separate from Hindsight API (8888).

```bash
systemctl status hybrid-search    # service
journalctl -u hybrid-search -f    # logs
curl http://127.0.0.1:8889/health  # health check
```

**Architecture — Read/Write path separation:**
```
READ PATH (synchronous, blocking):
  Agent → POST /recall → Gemini embed (500ms) → Qdrant search (5ms) → FlashRank rerank (1.3s) → Top 5
  Total: ~1.8s avg (min 1.1s, max 3.7s)
  LLM waits for results before generating response.

WRITE PATH (asynchrone, non-bloquant):
  Agent → Hindsight API (8888) → retain/consolidate → PG + background processing
  Results written to Qdrant by migration/connector scripts.
```

**Env vars (in systemd unit):**
```bash
GEMINI_API_KEY=<key>           # for embedding
RERANKER_PROVIDER=flashrank    # or: cohere, zeroentropy
QDRANT_URL=http://127.0.0.1:6333
```

**API endpoint:**
```bash
curl -X POST http://127.0.0.1:8889/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "Lucas preferences", "top_k": 5, "prefetch_limit": 50}'
# Returns: {results: [...], timings: {embed_ms, search_ms, rerank_ms, total_ms, candidates_count}}
```

**Config:** `/root/.hermes/services/hybrid_search.py`

**Pitfall: prefetch_limit** — Default 50. With FlashRank on ARM CPU, 100 candidates takes ~2.5s rerank, 50 takes ~1.3s. Quality difference is negligible for <500 memories.

**Cloud reranker (ZeRank-2 — now in production):**
ZeRank-2 is now the primary reranker. Config in systemd:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy
HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL=zerank-2
HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=<key>
```
Estimated total with ZeRank-2 API: ~740ms (500ms embed + 5ms search + 200ms API rerank).
Fallback: `HINDSIGHT_API_RERANKER_PROVIDER=flashrank` with `ms-marco-MiniLM-L-12-v2`.

## Recall Performance Optimization (2026-04-27)

### Latency breakdown (hybrid search service)
- `Gemini embedding`: ~500ms (API round trip)
- `Qdrant vector search`: ~5ms (40x faster than PG)
- `FlashRank rerank`: ~1300ms avg (highly variable on ARM: 675-3241ms)
- `Total`: ~1819ms avg (min 1137ms, max 3720ms)

### Latency breakdown (legacy Hindsight API)
Use `{"query":"...", "trace":true}` in recall to get `phase_metrics`:
- `generate_query_embedding`: ~0.5s (Gemini API round trip)
- `parallel_retrieval`: ~0.07s (PG vector + BM25 + graph)
- `reranking`: **1.6-1.9s** (cross-encoder on 80 candidates) ← **main bottleneck**
- Total: ~2.2-2.5s

### Reranker FlashRank model comparison (tested 2026-04-26)

| Model | Size | Avg recall | Quality (top-1 match) | Notes |
|---|---|---|---|---|
| `ms-marco-MiniLM-L-12-v2` | 34MB | 2.2s | 100% (baseline) | **Current production** |
| `ms-marco-TinyBERT-L-2-v2` | 4MB | 0.7s | 50% vs baseline | 3x faster but loses quality on technical queries |

**Conclusion:** TinyBERT confuses context on technical/architecture queries (e.g. "Scena Factory architecture" returns "creator of Scena Factory" instead of "Workers, D1, PiAPI"). Since reranking is async (prefetch), speed doesn't matter — **stay on MiniLM-12 for quality**.

### Reranker config options
```bash
# Limit candidates sent to cross-encoder (default: 300)
# 40 is the sweet spot — quality matters more than speed (async reranking)
HINDSIGHT_API_RERANKER_MAX_CANDIDATES=40

# Bucket batching — sorts by length for efficient batching
# ⚠️ COUNTERPRODUCTIVE on ARM (Neoverse-N1) with small candidate counts!
# Made things 30% SLOWER in testing. Only useful with 200+ candidates on fast CPUs.
HINDSIGHT_API_RERANKER_LOCAL_BUCKET_BATCHING=false  # keep false on ARM

# FP16 — may help on CPUs with AVX-512/VNNI, not tested on ARM
HINDSIGHT_API_RERANKER_LOCAL_FP16=false
```

### Reranker provider: `rrf` (fast alternative)
The `rrf` (Reciprocal Rank Fusion) provider is a **passthrough** that skips the cross-encoder entirely:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=rrf
```
- **Speed:** 0.7s vs 2.5s (3.8x faster)
- **Quality:** Slightly lower — gives more weight to recency/entity than semantic similarity
- **When to use:** <500 memories, or as a pre-filter stage
- **When NOT to use:** 500+ memories where cross-encoder quality matters
- **Tested 2026-04-26:** 5 queries, same top-3 results as cross-encoder on 83 memories

### Reranker provider options (all valid values)
`local`, `tei`, `cohere`, `zeroentropy`, `siliconflow`, `google`, `flashrank`, `litellm`, `litellm-sdk`, `rrf`, `jina-mlx`

### Cloud reranker options (for scaling to 100k+ memories)

**Jina reranker v2 via Cohere provider (RECOMMENDED):**
Jina's API is Cohere-compatible — use the `cohere` provider pointed at Jina:
```bash
HINDSIGHT_API_RERANKER_PROVIDER=cohere
HINDSIGHT_API_RERANKER_COHERE_API_KEY=<jina_api_key>     # Free: 1M tokens/month
HINDSIGHT_API_RERANKER_COHERE_MODEL=jina-reranker-v2-base-multilingual
HINDSIGHT_API_RERANKER_COHERE_BASE_URL=https://api.jina.ai/v1
```
- Multilingual (French included), 0.3B params, ~200-400ms via API
- Free tier: 1M tokens/month (sufficient for 100k+ memories daily use)
- Get key: https://jina.ai/?key=key-manager
- **Not yet tested in production** — benchmark quality vs MiniLM-12 before switching

**Cohere rerank-v3.5 via OpenRouter:**
```bash
HINDSIGHT_API_RERANKER_PROVIDER=openrouter
HINDSIGHT_API_RERANKER_OPENROUTER_MODEL=cohere/rerank-v3.5
# Needs: OPENROUTER_API_KEY in env
# Cost: ~$1/1000 searches, ~300-500ms per search
```

**Key finding (2026-04-26):** Reranking runs **asynchronously** via prefetch — the user never waits for it. The prefetch starts when the turn begins, reranks in a background thread, and results are injected at the next turn. This means **reranker speed does not impact user experience**. Prioritize quality over speed. Use MAX_CANDIDATES=40 (not 25) for best results.

### Legacy HUD CPU hog
The `hermes-hudui` service (legacy HUD on port 3002) can consume **82% CPU** continuously after running for days. This directly impacts reranker latency. Check and kill:
```bash
systemctl stop hermes-hudui
systemctl disable hermes-hudui
```
After killing, recall latency dropped from 2.8s to 2.2s.

## Comprehensive Test Suite (10 tests)

### Automated Script (preferred)

```bash
# Full test suite — exit code 0 = all pass, 1 = failure
python3 /root/.hermes/scripts/test_hindsight.py

# With detailed warnings
python3 /root/.hermes/scripts/test_hindsight.py --verbose
```

The script covers all 10 tests below, auto-creates test memories, and auto-cleans them after.
Test data uses prefix `TEST_SUITE:` for easy identification.

### Manual Tests (for debugging individual components)

### Test 1: API Health
```bash
curl -s http://127.0.0.1:8888/health
# Expected: {"status":"healthy","database":"connected"}
```

### Test 2: Retain (store memories)
```bash
curl -s -X POST http://127.0.0.1:8888/v1/default/banks/walter/memories \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"content":"test fact","context":"test context"}]}'
# Expected: {"id": "...", "status": "ok"}
```

### Test 3: Recall (various query types)
Test: exact match (EN), exact match (FR), semantic, entity-based, bilingual, technical deep, vague, recent events. All should return results.

### Test 4: Consolidate
```bash
curl -s -X POST http://127.0.0.1:8888/v1/default/banks/walter/consolidate \
  -H 'Content-Type: application/json' -d '{}'
# Returns operation_id, processes asynchronously
```

### Test 5: Entities + Graph
```bash
curl -s http://127.0.0.1:8888/v1/default/banks/walter/entities
curl -s http://127.0.0.1:8888/v1/default/banks/walter/entities/graph
```

### Test 6: Performance benchmarks
Run 10 recall queries, measure P50/P95. Target: P50 < 3s.

### Test 7: Edge cases
Empty query (expect 422), single char, 500-char query, special chars, emoji, SQL injection, unicode, null bytes. All except empty should return 200.

**Edge case behavior (tested 2026-04-26):**
- Empty query `""` → HTTP 422 (validation error, correct)
- Special chars `!@#$%^&*()` → HTTP 422 (validation error)
- Emoji `🔥💧🎉` → HTTP 422 (validation error)
- SQL injection, unicode, null bytes, 500-char query → HTTP 200 (handled gracefully)

### Test 8: Plugin integration
Verify `config.json`: auto_recall=true, auto_retain=true, retain_async=true.
Check memories created in last hour: `SELECT COUNT(*) FROM memory_units WHERE created_at > NOW() - INTERVAL '1 hour';`

### Test 9: Cron readiness
Verify dreaming script syntax: `python3 -c "import ast; ast.parse(open('/root/.hermes/scripts/memory_dreaming.py').read())"`
Verify endpoints: consolidate, entities, mental-models all return HTTP 200.

### Test 10: Data integrity
```sql
-- Counts
SELECT COUNT(*) FROM memory_units;    -- memories
SELECT COUNT(*) FROM entities;         -- entities
SELECT COUNT(*) FROM unit_entities;    -- unit↔entity links
SELECT COUNT(*) FROM memory_links;     -- memory graph links
SELECT COUNT(*) FROM chunks;           -- chunks

-- Embedding coverage
SELECT COUNT(*) FROM memory_units WHERE embedding IS NOT NULL;
SELECT COUNT(*) FROM memory_units WHERE embedding IS NULL;  -- should be 0

-- Dimension check
SELECT vector_dims(embedding) FROM memory_units WHERE embedding IS NOT NULL LIMIT 1;

-- Duplicates
SELECT COUNT(*) FROM (SELECT text, COUNT(*) c FROM memory_units GROUP BY text HAVING COUNT(*) > 1) dup;

-- Similar duplicates (pg_trgm)
SELECT COUNT(DISTINCT a.id) FROM memory_units a JOIN memory_units b ON a.id < b.id AND similarity(a.text, b.text) > 0.85;

-- Extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm');

-- DB size
SELECT pg_size_pretty(pg_database_size('hindsight'));
```

## DB Schema Reference (v0.5.2)

| Table | Purpose |
|---|---|
| `memory_units` | Core facts. Has `embedding vector(768)` column directly. |
| `entities` | Extracted entities (people, tools, projects) |
| `unit_entities` | Links memory_units ↔ entities |
| `memory_links` | Memory graph edges (source → target) |
| `entity_cooccurrences` | Entity pair co-occurrence counts |
| `chunks` | Document chunks (linked via memory_units.chunk_id) |
| `documents` | Source documents |
| `mental_models` | Generated by dreaming cycle |
| `directives` | Active directives |
| `async_operations` | Background job tracking |
| `audit_log` | API audit trail |
| `banks` | Bank definitions |
| `webhooks` | Webhook subscriptions |
| `file_storage` | File attachments |

## Modularity (provider swapping)

Each component is swappable via env var — no data migration needed:
```bash
# Embeddings (current: google / gemini-embedding-2-preview, 768d)
HINDSIGHT_API_EMBEDDINGS_PROVIDER=google|openai|cohere|local|tei|litellm
HINDSIGHT_API_EMBEDDINGS_GEMINI_MODEL=gemini-embedding-2-preview

# Reranker (current: zeroentropy / zerank-2)
HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy|local|rrf|cohere|openrouter|google|tei|flashrank|...

# LLM (current: gemini / gemini-3.1-flash-lite-preview)
HINDSIGHT_API_LLM_PROVIDER=gemini
HINDSIGHT_API_LLM_MODEL=gemini-3.1-flash-lite-preview

# Database (current: Docker PG)
HINDSIGHT_API_DATABASE_URL=postgresql://hindsight@172.17.0.3:5432/hindsight
```

⚠️ If changing embedding model with different dimension, must drop + recreate schema (Failure Mode 6).

### Layer 4: Support (Cron)
- **Health check** — daily at 3AM UTC, checks API health + PG + systemd
- **Dreaming** — daily at 4AM UTC, active consolidation + reflection + entity graph check
- **Connectors** — daily at 5AM UTC, ingests Telegram + Beeper messages into Hindsight
- Scripts: `/root/.hermes/scripts/memory_dreaming.py`, `/root/.hermes/scripts/memory_connectors.py`

### Key Improvements
- `on_pre_compress` hook retains last 10 turns before compression (no data loss)
- `_is_substantive` filter skips trivial messages ("ok", "merci", etc.)
- Thinking blocks stripped from old messages in compressor
- FlashRank reranker active (ms-marco-MiniLM-L-12-v2, CPU)
- Seeded 12 initial facts into Hindsight (user, infra, stack)

## Pitfalls

1. **Package name mismatch:** `hindsight-embed` (pip) ≠ `hindsight` (import). The plugin imports `from hindsight import HindsightEmbedded` which may require a different package or symlink.
2. **Root + embedded PG:** PostgreSQL `initdb` refuses to run as root by default. **Preferred fix:** use `local_api` mode with external Docker PG (avoids the LD_PRELOAD hack entirely). Fallback: LD_PRELOAD UID spoof (see Failure Mode 2).
3. **Shim must be in both Pythons:** The `hindsight` shim needs to be installed in both the system Python site-packages AND the Hermes venv site-packages, because daemon subprocesses may inherit either `PYTHONPATH`.
4. **Config says `memory.provider: hindsight` in config.yaml** but plugin is broken — Hermes silently falls back or returns errors from tools.
5. **hindsight-api log ANSI codes:** The startup banner uses ANSI escape sequences, making log files hard to read. Use `cat -v` or pipe through `sed 's/\\x1b\\[[0-9;]*m//g'`.
6. **pg_hba.conf ordering:** Trust rules MUST come before `scram-sha-256`. PostgreSQL is first-match.
7. **Embeddings provider is `google` not `gemini`:** The env var `HINDSIGHT_API_EMBEDDINGS_PROVIDER` must be `google` (the value `gemini` is not recognized).
8. **Reranker startup delay:** The cross-encoder model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) takes ~20-25s to load. The port won't bind until it's ready. Don't panic if health check fails immediately after start.
9. **Retain API body format:** The POST to `/v1/default/banks/{bank_id}/memories` requires `{"items": [...]}` not `{"content": "..."}`.
10. **Docker PG bridge IP:** The container's IP on the bridge network (typically `172.17.0.x`) is used for host→container connections. Check with `docker inspect hindsight-pg --format '{{.NetworkSettings.Networks.bridge.IPAddress}}'`. This IP can change if the container is recreated — consider adding port mapping to docker-compose for stability. Symptom: `hindsight-api.service` restarts every ~13s with `psycopg2.OperationalError: connection to server at "172.17.0.X" refused` / exit `status=3/NOTIMPLEMENTED`. Quick fix: `PG_IP=$(docker inspect hindsight-pg --format '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}'); echo "HINDSIGHT_API_DATABASE_URL=postgresql://hindsight@${PG_IP}:5432/hindsight" > /root/.hermes/hindsight/hindsight-api.env; systemctl restart hindsight-api.service`.
11. **Plugin mode is `local_external` NOT `local_api`:** The plugin's valid modes are `cloud`, `local_embedded`, `local_external`. There is NO `local_api` mode. If you set `"mode": "local_api"` in config.json, the plugin will not recognize it and silently fail or fall back to cloud mode. Always use `"local_external"` with `"api_url"` for external API servers.
12. **Never `kill -9` the gateway from an agent session:** The agent process runs inside the gateway. Killing the gateway kills the session, and the user must manually relaunch the TUI. Use SIGUSR1 (`kill -USR1 <gateway_pid>`) for graceful restart, or `systemctl restart hermes-gateway`. The gateway exits with code 75 and systemd restarts it. Session state is preserved in SQLite and can be resumed.
14. **`.env.service` getting `***` values:** The vault CLI masks keys in output. If something writes vault output to `.env.service`, it stores `***` instead of real keys. The service keeps running (keys loaded at startup) but dies on next restart. Fix: `vault decrypt | python3 -c "..." > .env.service` (see Test section above for exact command).
15. **Bucket batching counterproductive on ARM:** `HINDSIGHT_API_RERANKER_LOCAL_BUCKET_BATCHING=true` adds overhead that exceeds its benefit on ARM Neoverse-N1 with <100 candidates. Made recall 30% slower in testing. Keep false on ARM.
16. **Legacy HUD eats CPU:** `hermes-hudui` service can consume 82% CPU after running for days, directly impacting reranker latency. Disable it: `systemctl stop hermes-hudui && systemctl disable hermes-hudui`.
17. **Consolidate is async:** `POST /consolidate` returns immediately with `operation_id` but the actual dedup runs in background. Wait 30-45s before checking results. The LLM consolidation call takes ~170s with gemini-3.1-flash-lite-preview.
18. **`trace=true` response is huge:** The recall endpoint with `trace: true` includes the full query embedding vector (768 floats) in the response. This can exceed 20KB and cause JSON parsing issues in shell tools. Use `trace: false` for automated tests.
19. **DB table names:** The schema uses `unit_entities` (not `entity_links`), `memory_links` (not `memory_graph`), and `entity_cooccurrences`. The `memory_units` table has the `embedding` column directly (no separate embeddings table).
20. **`recall` endpoint ignores `limit` param:** The recall API returns all candidates up to `reranker_max_candidates`. The `limit` parameter is not recognized. Control output size via `budget` (low/mid/high) and `max_tokens`.
21. **Edge case validation:** The recall API returns 422 for empty queries, special chars (`!@#$%^&*()`), and emoji (`🔥💧🎉`). SQL injection attempts, unicode, null bytes, and long queries are handled gracefully (200). Build automated tests to expect 422 on these inputs.
22. **`trace=true` does NOT expose phase timings:** The trace field returns retrieval results, RRF merged, reranked, and graph traversal data — but NOT internal timing breakdowns. Use the `/metrics` Prometheus endpoint for component-level latency data.
23. **Retain body schema:** The `POST /v1/default/banks/{bank_id}/memories` endpoint requires `{"items": [{"content": "...", "context": "..."}]}`. The `context` field is optional. The `async` field defaults to false. Single memory: wrap in `items` array of length 1.
