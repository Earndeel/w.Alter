# Programmatic Simulation Flow

Full curl-based workflow to run a MiroShark simulation without the UI.

## 1. Generate ontology (returns project_id)
```bash
curl -s -X POST http://localhost:5001/api/graph/ontology/generate \
  -F "simulation_requirement=Analyze the impact of X on Y" \
  -F "project_name=My Analysis" \
  -F 'url_docs=[{"title":"Source","url":"https://...","text":"Full article text..."}]'
# → {"data": {"project_id": "proj_xxxx", ...}}
```

## 2. Build Neo4j graph
```bash
curl -s http://localhost:5001/api/graph/build \
  -H "Content-Type: application/json" \
  -d '{"project_id": "proj_xxxx"}'
```

## 3. Create simulation
```bash
curl -s http://localhost:5001/api/simulation/create \
  -H "Content-Type: application/json" \
  -d '{"project_id":"proj_xxxx","enable_twitter":true,"enable_reddit":true,"enable_polymarket":true}'
# → {"data": {"simulation_id": "sim_xxxx", ...}}
```

## 4. Prepare (generates agent profiles)
```bash
curl -s http://localhost:5001/api/simulation/prepare \
  -H "Content-Type: application/json" \
  -d '{"simulation_id": "sim_xxxx"}'

# Poll (POST, not GET!):
curl -s -X POST http://localhost:5001/api/simulation/prepare/status \
  -H "Content-Type: application/json" \
  -d '{"simulation_id": "sim_xxxx"}'
# Wait for: {"data": {"status": "ready", "already_prepared": true}}
```

## 5. Start simulation
```bash
curl -s -X POST http://localhost:5001/api/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"simulation_id": "sim_xxxx"}'
# 72 rounds = 72 simulated hours, ~15-30 min real time
```

## 6. Poll progress
```bash
curl -s -X POST http://localhost:5001/api/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"simulation_id": "sim_xxxx"}'
# Check: current_round, twitter_actions_count, progress_percent
```

## 7. Get results
```bash
curl -s http://localhost:5001/api/simulation/sim_xxxx
```

## suggest-scenarios (optional, for prediction markets)
```bash
curl -s http://localhost:5001/api/simulation/suggest-scenarios \
  -H "Content-Type: application/json" \
  -d '{"text_preview": "Long article text (80+ chars after normalization)..."}]
# Returns Bull/Bear/Neutral scenarios with expected_yes_range
```

## Key gotchas
- `text_preview` not `text` for suggest-scenarios
- `prepare/status` is POST not GET
- `/api/simulation/start` not `/api/simulation/<id>/start`
- `url_docs` in ontology/generate must be JSON-encoded string in multipart form
