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
