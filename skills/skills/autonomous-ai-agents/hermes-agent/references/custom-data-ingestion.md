# Custom Data Ingestion Endpoints

Pattern for accepting data from mobile devices, IoT, or external services into Hermes' knowledge base.

## Architecture

```
iOS Shortcut / Device → HTTPS (Cloudflare Tunnel) → Python HTTP Server → JSONL → Hindsight
```

## Step-by-Step

### 1. Write a minimal HTTP server

Use Python stdlib `http.server` — no dependencies. Listen on `127.0.0.1`.

Template: `templates/ingestion-server.py`

### 2. Expose via Cloudflare Tunnel

Add a new hostname or use an existing one:

```bash
# DNS: loc.walter-ai.cloud → CNAME → tunnel-uuid.cfargotunnel.com
# Cloudflare API:
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -d '{"type":"CNAME","name":"loc","content":"TUNNEL_ID.cfargotunnel.com","proxied":true}'
```

Add ingress rule in `~/.cloudflared/config.yml`:
```yaml
- hostname: loc.walter-ai.cloud
  service: http://localhost:5051
```

Restart cloudflared: `kill $(pgrep -f "cloudflared tunnel.*config.yml")` then restart.

⚠️ **Watch for Cloudflare Workers**: If a Worker route matches the hostname (e.g., `api.walter-ai.cloud/*`), it intercepts before the tunnel. Check with:
```bash
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE/workers/routes" \
  -H "Authorization: Bearer $CF_TOKEN"
```

### 3. Store to JSONL

Simple append-only JSONL at `$HERMES_HOME/data/<name>.jsonl`. Each line is a JSON record.

### 4. Ingest into Hindsight

Create a cron job that:
1. Reads new lines from JSONL
2. Clusters/analyzes data
3. Stores synthesized insights to Hindsight via `hindsight_retain`

Example cron (every 6h):
```bash
hermes cron create "0 */6 * * *" --name "location-insights" \
  --prompt "Process new data from JSONL, store insights to Hindsight"
```

### 5. iOS Shortcut Template

For iPhone automation:
- **Get Current Location** → lat/lng
- **Get Battery Level** → battery
- **Date** (ISO 8601) → ts
- **Dictionary** → {lat, lng, ts, acc, battery}
- **Get Contents of URL** → POST to endpoint with Bearer auth

Automation triggers: geofences (Arrive/Leave) for low battery impact, or Time of Day for periodic.

## Pitfalls

- **Bind to 127.0.0.1, not 0.0.0.0** — the tunnel connects locally; no need to expose
- **Worker interference** — Cloudflare Workers match BEFORE tunnels; use a clean hostname
- **DNS propagation** — CNAME records can take 1-2 min; test with `curl` after creation
- **Auth token** — use a static bearer token in the endpoint; rotate if compromised
- **JSONL is not a database** — for high-frequency data (>1000/day), switch to SQLite
- **Hindsight is for insights, not raw data** — store patterns/summaries, not every coordinate
