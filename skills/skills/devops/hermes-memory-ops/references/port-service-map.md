# W.Alter Memory Stack — Port to Service Map

| Port | Bind       | Service                  | Description                                    | Health     |
|------|-----------|--------------------------|------------------------------------------------|------------|
| 8888 | 127.0.0.1 | hindsight-api            | Hindsight Memory API (PG read/write)           | /health    |
| 8889 | 127.0.0.1 | hybrid-search            | Hybrid Search API (Qdrant + reranker)          | /health    |
| 8890 | 127.0.0.1 | write-worker             | Async write worker (Gemini Flash Lite extract) | /health    |
| 8891 | 0.0.0.0   | jarvis-memory-gateway    | Memory Gateway (orchestrates all downstream)   | /health    |
| 8896 | 127.0.0.1 | walter-call-embed-fast   | Local MiniLM embedding service (384-d)         | /health    |
| 6333 | 0.0.0.0   | qdrant                   | Qdrant vector DB                               | / (root)   |
| 5433 | 127.0.0.1 | hindsight-pg (docker)    | PostgreSQL 16 + pgvector                       | —          |

## Internal Docker bridge

| Container Port | Container    | Host Port |
|---------------|-------------|-----------|
| 5432          | hindsight-pg| 5433      |
| 6333          | qdrant      | 6333      |
| 6334          | qdrant      | 6334      |

## Downstream dependency chain

```
jarvis-memory-gateway (8891)
  ├── hindsight-api (8888) → postgres (hindsight-pg:5432)
  ├── hybrid-search (8889) → qdrant (6333)
  └── write-worker (8890)  → postgres (hindsight-pg:5432)
```

## Service discovery commands

Use `ss -tlnp | grep -E '888|889|6333'` for quick port scan.
Use `systemctl status hindsight-api hybrid-search write-worker jarvis-memory-gateway walter-call-embed-fast` for service status.
Use `docker stats --no-stream hindsight-pg qdrant` for container health.
