---
name: postgres-integration
description: PostgreSQL commands, patterns, and troubleshooting — psql, SQL, indexes, backups, and common operations.
category: devops
---

# PostgreSQL Integration

## When to Use
- Querying, creating, or modifying PostgreSQL databases
- Writing migrations or schema changes
- Troubleshooting connection issues, slow queries, or locks
- Setting up backups, replication, or user permissions

## Key Commands

### Connection
```bash
psql -h localhost -U postgres -d dbname
psql "postgresql://user:pass@host:5432/dbname"
\l                  # list databases
\dt                 # list tables
\d tablename        # describe table
\di                 # list indexes
\q                  # quit
```

### Common SQL
```sql
-- Create database
CREATE DATABASE mydb OWNER myuser;

-- Create table with common types
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX CONCURRENTLY idx_users_created ON users(created_at DESC);

-- JSONB queries
SELECT * FROM events WHERE data->>'type' = 'signup';
SELECT * FROM events WHERE data @> '{"status": "active"}';
```

### Backups
```bash
pg_dump -h localhost -U postgres dbname > backup.sql
pg_dump -Fc dbname > backup.dump           # custom format (compressed)
pg_restore -d dbname backup.dump           # restore custom format
psql dbname < backup.sql                   # restore plain SQL
```

## Common Patterns

### Connection pooling (PgBouncer)
```bash
# pgbouncer.ini
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
```

### Useful monitoring queries
```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' ORDER BY duration DESC;

-- Table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
```

## Pitfalls
- `SERIAL` is not truly sequential under concurrent inserts — use `GENERATED ALWAYS AS IDENTITY` for guarantees
- `VARCHAR(255)` vs `TEXT`: in PostgreSQL there's no performance difference, prefer `TEXT`
- Always use `CONCURRENTLY` for index creation on production tables (no table lock)
- `pg_dump` locks tables — use `-Fc` format with `--no-owner` for flexible restores
- Connection strings with special chars need URL encoding: `postgresql://user:p%40ss@host/db`
- Don't use `SELECT *` in production — specify columns to avoid breaking on schema changes
