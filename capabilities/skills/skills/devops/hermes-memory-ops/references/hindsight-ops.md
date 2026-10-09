---
name: hindsight-memory-ops
description: "Operational maintenance for Hindsight memory system — dedup tuning, cron model routing, Docker IP drift, auto_retain pipeline. Companion to hindsight-debug-and-repair (which covers full architecture and recovery)."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hindsight, memory, dedup, cron, docker, maintenance]
    related_skills: [hindsight-debug-and-repair, hermes-memory-ops, memory-auto-maintenance]
---

# Hindsight Memory Operations

Day-to-day maintenance for the Hindsight memory stack. Covers deduplication backlog, cron model routing, Docker IP drift, and the auto_retain pipeline.

## When to Use

- Dreaming cycle or other cron jobs failing with 402 / provider errors
- Duplicate memories accumulating faster than cleanup
- hindsight-pg container IP changed after reboot
- Verifying Hindsight health and model configuration
- Tuning exact dedup parameters

## Architecture Quick Reference

| Component | Model | Provider | Role |
|---|---|---|---|
| Hindsight API | gemini-3.1-flash-lite-preview | Google direct | Extraction, consolidation, entities |
| Dreaming cron | gemini-3.5-flash | Google direct | Deep consolidation, mental models |
| Skill Intel cron | gemini-3.5-flash | Google direct | Gap detection, quality analysis |
| Reranker | zerank-2 | ZeroEntropy | Result ranking (local, no API cost) |

**Key files:**
- `/root/.hermes/hindsight/hindsight-api.env` — DATABASE_URL (IP hardcoded here)
- `/etc/systemd/system/hindsight-api.service` — systemd unit
- `/etc/systemd/system/memory-guarded-maintenance.service` — exact dedup timer
- `/root/.hermes/cron/jobs.json` — Hermes cron jobs (dreaming, etc.)
- `/root/.hermes/scripts/memory_dreaming.py` — dreaming cycle script
- `/root/.hermes/scripts/hindsight_pg_exact_dedup.py` — exact dedup script

## Pitfalls

### 1. Exact dedup default params are too slow

Default: `--limit-groups 25 --max-delete 200`. With 600+ duplicate groups, takes 26+ days — while `auto_retain` creates new ones daily.

**Fix (systemd):** Edit `memory-guarded-maintenance.service`:
```
--limit-groups 100 --max-delete 500
```
Then `systemctl daemon-reload`.

**Fix (immediate backlog):**
```bash
python3 /root/.hermes/scripts/hindsight_pg_exact_dedup.py --apply --limit-groups 200 --max-delete 1000
```

**Count current duplicates:**
```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -c "
SELECT COUNT(*) as groups, SUM(cnt - 1) as excess
FROM (SELECT text, COUNT(*) as cnt FROM memory_units GROUP BY text HAVING COUNT(*) > 1) sub;"
```

### 2. Cron jobs silently fail when provider is unset

When `model.provider` is omitted, Hermes resolves through the default chain (OpenRouter). If credits exhausted → HTTP 402, cron marked `error`, no alert.

**Detection:**
```bash
python3 -c "
import json
with open('/root/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for j in data['jobs']:
    if j.get('last_status') == 'error':
        m = j.get('model','?')
        if isinstance(m, dict): mp = m.get('model','?') + ' / ' + m.get('provider','?')
        else: mp = str(m)
        print(f'{j[\"id\"][:12]}  {j[\"name\"]:35s}  model={mp}')
"
```

**Fix:** Always set provider explicitly via `cronjob action=update`:
```json
{"model": "gemini-3-5-flash", "provider": "google"}
```

### 3. Docker bridge IP changes on reboot

`hindsight-pg` on default bridge gets a new IP after host reboot. Hardcoded in `hindsight-api.env`.

**Quick fix:**
```bash
NEW_IP=$(docker inspect hindsight-pg --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
sed -i "s/172.17.0.[0-9]*/$NEW_IP/" /root/.hermes/hindsight/hindsight-api.env
systemctl restart hindsight-api
sleep 20 && curl -s http://127.0.0.1:8888/health
```

**Permanent fix:** Dedicated Docker network with fixed IP.

### 4. auto_retain inserts without dedup → FIXED with MD5 hash cache

The Hindsight plugin's `auto_retain` posts each turn to the API → direct INSERT, no similarity check. **Fixed (2026-06-10):** Added a `_retain_hash_cache` dict in the plugin that stores `MD5(text) → timestamp` for the last 10 minutes. Before inserting, the plugin checks if an identical text was recently retained and skips it.

**Location:** `/root/.hermes/hermes-agent/plugins/memory/hindsight/__init__.py` → `_do_retain()` method.

**How it works:**
```python
import hashlib, time
h = hashlib.md5(text.encode()).hexdigest()
if h in self._retain_hash_cache and (now - self._retain_hash_cache[h]) < 600:
    return  # skip duplicate
self._retain_hash_cache[h] = now
```

Cache is in-memory (lost on gateway restart), TTL 10 min. Catches exact duplicates only — semantic near-duplicates still handled by consolidation/dreaming.

## Health Check Recipe

```bash
# 1. Service status
systemctl status hindsight-api | head -10

# 2. Container status
docker ps -a | grep hindsight

# 3. Health endpoint
curl -s http://127.0.0.1:8888/health

# 4. Memory count
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT COUNT(*) FROM memory_units;"

# 5. Duplicate count
docker exec hindsight-pg psql -U hindsight -d hindsight -c "
SELECT COUNT(*) as groups, SUM(cnt - 1) as excess
FROM (SELECT text, COUNT(*) as cnt FROM memory_units GROUP BY text HAVING COUNT(*) > 1) sub;"

# 6. Cron status
python3 -c "
import json
with open('/root/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for j in data['jobs']:
    print(f'{j[\"name\"]:35s}  {j.get(\"last_status\",\"?\"):8s}  next={j.get(\"next_run_at\",\"?\")}')"
```

## Dreaming Cycle

Runs daily at 04:00 UTC. Executes `memory_dreaming.py` which performs:

1. **Exact dedup (first!)** — calls `hindsight_pg_exact_dedup.py` inline to clean text-identical duplicates BEFORE consolidation runs. This prevents the consolidation LLM from wasting tokens on obvious duplicates.
2. **Consolidation** — `POST /consolidate` (async, polls `/operations/{id}` until done). Merges semantically similar memories.
3. **Entity extraction** — `POST /entities/extract` to update knowledge graph.
4. **Mental models** — `POST /mental-models` for cross-domain pattern synthesis.

**Critical:** The consolidation endpoint returns immediately with an `operation_id` and processes asynchronously. The dreaming script polls `GET /operations/{id}` until `status=completed` (max 10 min, 5s intervals). Do NOT assume the consolidation is done when the POST returns.

**Provider:** `provider: google` (NOT OpenRouter — 402 credit errors). Model: `gemini-3.5-flash`.

**Key distinction:**
- **Exact dedup** = text-identical memories (`hindsight_pg_exact_dedup.py`). Handles the ~650+ duplicate groups that accumulate from auto_retain.
- **Consolidation** = semantic similarity (Hindsight API `/consolidate`). Merges near-duplicates with different wording.

If dreaming fails, check cron status first (provider/credits), then Hindsight API health.

## Reference Files

- `references/dedup-and-dreaming-fixes.md` — June 2026 fixes: dedup ROLLBACK pattern, dreaming API key corrections, plugin hash cache
