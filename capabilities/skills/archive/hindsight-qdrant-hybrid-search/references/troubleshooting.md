## Pitfalls

### FlashRank passage format
FlashRank expects `[{"text": "..."}]`, NOT `["string"]`. Returns `[{"text": "...", "score": float32}]` sorted by score desc. Match back to originals by text content (no `rank` key).

### Qdrant named vectors
When collection uses named vectors (`"dense"`), PointStruct must be `vector={"dense": [0.1, 0.2, ...]}`. Passing `vector=[0.1, 0.2, ...]` or adding `vectors={"dense": [...]}` to `upsert()` both fail.

### Systemd empty Environment line
An empty `Environment=` line in a .service file silently drops ALL subsequent Environment lines. Always `grep` the env vars from `/proc/<pid>/environ` after starting.

### Systemd Environment Override Pitfall
The systemd service file (`/etc/systemd/system/hindsight-api.service`) can hardcode `Environment=HINDSIGHT_API_LLM_MODEL=...` which **silently overrides** the `.env` file. The `.env` at `~/.hindsight/profiles/hermes.env` may say `gemini-3-flash-preview` while the running process actually uses `gemini-3.1-pro-preview` (or whatever the systemd unit says). This caused $50+ in 2 weeks when Pro was left running for extraction.

**Diagnosis**: compare ALL running process env vars vs .env — not just LLM_MODEL:
```bash
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep -E 'LLM_MODEL|RERANKER|EMBEDDINGS|ZEROENTROPY' | sort
cat ~/.hindsight/profiles/hermes.env | grep -E 'LLM_MODEL|RERANKER|EMBEDDINGS'
```

This pitfall affects ALL environment variables in the systemd unit, not just LLM_MODEL. In one session, three mismatches were found simultaneously:
- `HINDSIGHT_API_LLM_MODEL` — had `gemini-3.1-pro-preview` instead of `gemini-3-flash-preview` (40× cost difference)
- `HINDSIGHT_API_RERANKER_PROVIDER` — had `flashrank` instead of `zeroentropy`
- `HINDSIGHT_API_RERANKER_*_MODEL` — had `ms-marco-MiniLM-L-12-v2` instead of `zerank-2`

**Fix**: edit the systemd unit directly for ALL mismatched vars, then reload+restart:
```bash
sed -i 's/HINDSIGHT_API_LLM_MODEL=.*/HINDSIGHT_API_LLM_MODEL=gemini-3.1-flash-lite-preview/' /etc/systemd/system/hindsight-api.service
sed -i 's/HINDSIGHT_API_RERANKER_PROVIDER=.*/HINDSIGHT_API_RERANKER_PROVIDER=zeroentropy/' /etc/systemd/system/hindsight-api.service
systemctl daemon-reload && systemctl restart hindsight-api
# Verify
PID=$(systemctl show hindsight-api -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep -E 'LLM_MODEL|RERANKER'
```

Same check applies to `write-worker.service` and `hybrid-search.service` — always verify the running process env, not just the .env files.

### ZeroEntropy API Key Location
The ZeRank-2 API key is stored in:
- `/root/.hermes/hindsight/.env.service` as `HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=ze_...`
- Systemd unit: `Environment=HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY=ze_...`

### Gemini Embed dimension mismatch
`gemini-embedding-2-preview` returns **3072 dimensions** by default. Qdrant collection expects 768. Always include `"output_dimensionality": 768` in the embed request body. Symptom: `Wrong input: Vector dimension error: expected dim: 768, got 3072`.

### Gemini 2.0-flash deprecated
`gemini-2.0-flash` is no longer available. Use `gemini-2.5-flash` for extraction LLM.

### ZeRank-2 endpoint
URL: `https://api.zeroentropy.dev/v1/models/rerank`
Payload: `{"model": "zerank-2", "query": "...", "documents": [...], "top_n": 5}`
Auth: `Authorization: Bearer ze_...`
