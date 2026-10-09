---
name: miroshark
category: devops
description: "Deploy and manage MiroShark — swarm intelligence simulation engine. Flask backend + Vue frontend + Neo4j. OpenRouter-powered, no GPU needed."
tags: [miroshark, simulation, swarm-intelligence, neo4j, flask, vue, self-hosted]
---

# MiroShark — Swarm Intelligence Simulation Engine

## What It Is
MiroShark = **oracle prédictif swarm intelligence**. Spawns hundreds of AI agents that react to a scenario hour by hour — posting, arguing, trading, changing their minds. Use it as a predictive tool: feed a topic/article, get back a swarm consensus with belief drift, market prices, and opinion convergence. Simulates Twitter, Reddit, and a prediction market.

## When to Use
- User asks "what will happen if..." about a market, industry, or event
- Need a prediction/multiple-perspective analysis on a topic
- Want to stress-test a business decision (launch, pivot, pricing)
- Need a "wisdom of the crowd" simulation before a real bet
- Exploring how public opinion might shift on a narrative

**Source**: https://github.com/aaronjmars/MiroShark
**License**: AGPL-3.0
**Cost**: ~$1/simulation via OpenRouter

## Architecture
- **Backend**: Flask (Python 3.11+), port 5001
- **Frontend**: Vue.js + Vite, port 3000
- **Database**: Neo4j (bolt://localhost:7687)
- **LLM**: OpenRouter (default: Mimo V2 Flash + Grok-4.1 Fast)
- **No GPU needed** — all inference via OpenRouter API

## Installation Steps

### 1. Prerequisites
```bash
apt install neo4j          # or brew install neo4j on macOS
# Python 3.11+, Node 18+, uv (https://astral.sh/uv/install.sh)
```

### 2. Clone & Configure
```bash
cd /root && git clone https://github.com/aaronjmars/MiroShark.git
cd MiroShark && cp .env.example .env
```

Set the same OpenRouter key in 5 places in `.env`:
```
LLM_API_KEY=sk-or-...
SMART_API_KEY=sk-or-...
NER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-or-...
EMBEDDING_API_KEY=sk-or-...
```

Set Neo4j credentials:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your_password>
```

### 3. Neo4j Setup (critical — see pitfalls)
```bash
# Set password BEFORE first start
neo4j-admin dbms set-initial-password <your_password>

# Fix permissions if running as root
chown -R neo4j:neo4j /var/lib/neo4j /var/log/neo4j /etc/neo4j

# Start as neo4j user
su - neo4j -c "neo4j start"
```

### 4. Install Dependencies
```bash
# Backend
cd backend && uv sync  # or: .venv/bin/python -m pip install -r requirements.txt

# Frontend — IMPORTANT: rm node_modules first if npm install was already run
cd ../frontend && rm -rf node_modules package-lock.json && npm install --include=dev
```

### 5. Start (3 separate processes)
```bash
# Terminal 1: Backend
cd backend && uv run python run.py

# Terminal 2: Frontend
cd frontend && npx vite --host --port 3000

# Terminal 3: Verify
curl -s http://localhost:5001/api/simulation/list
curl -s http://localhost:3000/
```

## Key Endpoints
- `GET /api/simulation/list` — list all simulations
- `GET /api/simulation/trending` — trending topics from RSS feeds
- `POST /api/simulation/create` — create a new simulation
- `POST /api/simulation/ask` — ask mode (no doc needed)
- `GET /api/simulation/<id>` — get simulation details
- `POST /api/simulation/branch-counterfactual` — fork with injected event
- `GET /api/docs` — Swagger UI
- `GET /explore` — public gallery

## Pitfalls

### Neo4j permission denied when running as root
Neo4j refuses to run if the process user (root) differs from the data dir owner (neo4j). Fix:
```bash
chown -R neo4j:neo4j /var/lib/neo4j /var/log/neo4j /etc/neo4j
su - neo4j -c "neo4j start"
```

### Neo4j authentication rate limit
If you get `Neo.ClientError.Security.AuthenticationRateLimit`, the password in `.env` doesn't match. Set it with `neo4j-admin dbms set-initial-password` BEFORE first start, or reset via Neo4j Browser at `:7474`.

### npm devDependencies not installed
Vite and other devDeps may not install on first `npm install`. Fix:
```bash
rm -rf node_modules package-lock.json && npm install --include=dev
```

### Launcher script output buffering
The `./miroshark` launcher buffers all output when run in background. For Hermes background processes, start backend and frontend separately instead of using the launcher.

### 5 API key slots
The `.env` requires the SAME OpenRouter key in 5 different `*_API_KEY` fields. This is not a mistake — different internal modules read different env vars.

### Cost tracking: shared key with Hermes
MiroShark's `LLM_API_KEY` is the same OpenRouter key as Hermes (`vault get openrouter/api_key`). You cannot isolate MiroShark costs from the OpenRouter dashboard — `GET /api/v1/auth/key` returns total usage across all consumers. To track MiroShark-specific spend, check `GET /api/v1/credits` for remaining balance, or grep MiroShark backend logs for `Calling LLM` entries to count calls. Models used: `xiaomi/mimo-v2-flash` (cheap), `x-ai/grok-4.1-fast` (smart/NER), `openai/text-embedding-3-large` (embeddings). A full ontology+prep+simulation costs ~$1.

### Model deprecation on OpenRouter (404)
Smart/NER models like `x-ai/grok-4.1-fast` get deprecated without notice. Symptoms: ontology returns `Error code: 404 - '... is deprecated'`. Fix: update `SMART_MODEL_NAME`, `NER_MODEL_NAME`, `WEB_SEARCH_MODEL` in `/root/MiroShark/.env` (e.g. `x-ai/grok-4.3`), then restart backend. Quick fix:
```bash
cd /root/MiroShark && sed -i 's|x-ai/grok-4.1-fast|x-ai/grok-4.3|g' .env
```
See `references/cost-tracking.md` for current model names.

### Programmatic simulation polling
`prepare/status` returns `not_started` for 1-2 min before `ready`. Poll every 10s, up to 60 attempts. For progress, POST `/api/simulation/start` with `simulation_id` body — returns `current_round`, `progress_percent`, `completed_at`.

### Hidden Dependencies (NOT in requirements.txt)
The Wonderwall simulation engine bundles code that imports packages not listed in `requirements.txt`. Simulation will fail at runtime with `ModuleNotFoundError`. Install these BEFORE first simulation:
```bash
cd /root/MiroShark/backend
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install sentence-transformers igraph pandas
```
Use CPU-only torch to avoid massive CUDA downloads on headless servers. Install one at a time — if you get a new `ModuleNotFoundError`, add it and restart backend.

**Verified import chain** (test with `python -c "import wonderwall"` until clean):
1. `torch` → `sentence-transformers` → `igraph` → `pandas`
2. Then verify: `python -c "from scripts.belief_integration import BeliefTracker"` (the actual entrypoint)

### suggest-scenarios field name
The endpoint uses `text_preview` or `document_preview`, NOT `text`. Minimum 80 chars after whitespace normalization.

### prepare/status is POST not GET
`/api/simulation/prepare/status` requires POST with `{"simulation_id": "..."}` body. GET returns 405.

### Simulation start endpoint
`/api/simulation/start` (not `/api/simulation/<id>/start`). Pass `{"simulation_id": "..."}` in POST body.

### Vite Host Allowlist for Cloudflare Tunnel
Vite blocks requests from unknown hosts. Add to `frontend/vite.config.js`:
```js
server: {
  allowedHosts: ['miroshark.walter-ai.cloud'],
}
```

### Neo4j Password in .env
The `***` masking in terminal output is literal by the vault tool. Use Python to write the actual password value, not sed.

### Cloudflare Tunnel for Remote Access
Create via CF API (account_id + api_token), add CNAME, configure ingress to localhost:3000, run with token. Create systemd services for persistence: miroshark-backend, miroshark-frontend, miroshark-tunnel.

## Programmatic API
See `references/api-flow.md` for full curl-based workflow to run simulations without the UI (ontology → graph → create → prepare → start → poll → results).

## Runtime Pitfalls

### Model deprecation on OpenRouter
OpenRouter deprecates models without warning. If ontology/graph generation fails with `404` + `"model is deprecated"`, update the model name in `.env` (e.g., `x-ai/grok-4.1-fast` → `x-ai/grok-4.3`). Check `SMART_MODEL_NAME`, `NER_MODEL_NAME`, and `WEB_SEARCH_MODEL`. Restart backend after `.env` changes.

### Simulation stuck at round 0 after restart
If a simulation shows `status: running`, `current_round: 0`, and no PID, the child process died but the DB state wasn't reset. Creating a new simulation from the same project is faster than debugging the stuck one. The project/graph/ontology are reusable — just create → prepare → start fresh.

### Vite frontend not running
The frontend (`npx vite --host --port 3000`) must be running separately from the backend. If `curl localhost:3000` returns empty, start it with `terminal(background=true)`.
The simulation process can hang mid-run with `CLOSE-WAIT` TCP connections to OpenRouter. Symptoms:
- Process uses 180%+ CPU but log file stops updating
- `ss -tnp | grep <pid>` shows CLOSE-WAIT on port 443
- Simulation log last modified > 10 min ago

**Diagnosis:** `tail -5 uploads/simulations/<sim_id>/simulation.log` — if no new round lines, it's stuck.
**Recovery:** `kill -9 <pid>`. The trajectory data is still valid up to the last completed round. See `references/reading-results.md` for how to extract partial results.
**Prevention:** Likely caused by slow LLM model (mimo-v2-flash on complex prompts). Consider switching `WONDERWALL_MODEL_NAME` to a faster model in `.env`.

### Simulation stuck at round 0 after process death
If a simulation shows `status: running`, `current_round: 0`, and `process_pid: None`, the child process died (gateway restart, OOM, etc.) but the DB wasn't updated. **`force_restarted: true` does NOT fix this** — the start endpoint returns `None` for all fields. Solution: create a new simulation from the same project:
```bash
# The project graph is still valid — no need to regenerate ontology
curl -s -X POST http://localhost:5001/api/simulation/create \
  -H "Content-Type: application/json" \
  -d '{"project_id":"<existing_project_id>","enable_twitter":true,"enable_reddit":true,"enable_polymarket":true}'
```
Then prepare + start the new simulation. Old stuck sims can be ignored.

### Port 5001 conflicts on backend restart
When restarting MiroShark backend, old processes may still hold port 5001. Kill them first:
```bash
fuser -k 5001/tcp 2>/dev/null; sleep 2
```
Multiple `run.py` processes can accumulate over time. Always check with `ps aux | grep run.py | grep -v grep` before starting.

### Gateway restart kills simulation processes
Hermes gateway restarts terminate all child processes including MiroShark simulations. If a long simulation is running during a gateway restart, it will die silently. The backend will still show the simulation as "running" but it's dead. See "Simulation stuck at round 0" above for recovery.

### Process management
The simulation spawns a child process (`run_parallel_simulation.py`). Killing the backend does NOT kill the simulation child. Always check: `ps aux | grep run_parallel | grep -v grep`.

### Cost tracking
MiroShark shares the same OpenRouter key as Hermes. The `GET /api/v1/auth/key` usage reflects TOTAL usage across all consumers. To estimate MiroShark-specific cost: count LLM calls in `logs/<date>.log` (grep for "Calling LLM") and multiply by model pricing. Simulation rounds each make ~4 LLM calls (one per agent per platform).

## Programmatic API
See `references/api-flow.md` for full curl-based workflow to run simulations without the UI.

See `references/reading-results.md` for extracting and interpreting simulation results (trajectory, belief states, market prices).

## MCP Integration
MiroShark has a built-in MCP server at `backend/mcp_server.py`. Can be integrated with Claude Desktop / Cursor / Windsurf. See the Settings → AI Integration page in the web UI for auto-generated config snippets.

## Programmatic API Flow
For running simulations from Hermes without the UI, follow this exact sequence:

1. **Ontology** — `POST /api/graph/ontology/generate` (multipart: simulation_requirement, project_name, url_docs JSON) → returns `project_id`
2. **Graph** — `POST /api/graph/build` with `{"project_id": "..."}` → poll `GET /api/graph/project/<id>` until `status: graph_completed`
3. **Create** — `POST /api/simulation/create` with `{"project_id": "...", "enable_twitter": true, "enable_reddit": true, "enable_polymarket": true}` → returns `simulation_id`
4. **Prepare** — `POST /api/simulation/prepare` with `{"simulation_id": "..."}` → poll `POST /api/simulation/prepare/status` until `status: ready`
5. **Start** — `POST /api/simulation/start` with `{"simulation_id": "..."}` → poll same endpoint for progress (current_round, actions_count, progress_percent)

Export endpoints for analysis:
- `GET /api/simulation/<id>/transcript` — per-round agent posts
- `GET /api/simulation/<id>/trajectory.csv` — belief evolution
- `GET /api/simulation/<id>/thread.txt` — auto-generated tweet thread
