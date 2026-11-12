#!/bin/sh
# Throwaway PostgreSQL for the tests (2026-11-02): never the production database. In memory (tmpfs), same image as
# hindsight-pg, built from this module's migrations. Usage: tests/testdb.sh up | down | reset
set -eu
NAME=${WALTER_MEMORY_TEST_NAME:-walter-memory-testpg} PORT=${WALTER_MEMORY_TEST_PORT:-5440}
DSN="postgresql://hindsight:walter-test-only@127.0.0.1:$PORT/hindsight"   # test-only credentials, no data
HERE=$(cd "$(dirname "$0")/.." && pwd)
case "${1:-up}" in
  down) docker rm -f "$NAME" >/dev/null 2>&1 || true ;;
  reset) "$0" down; "$0" up ;;
  up)
    if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
      docker run -d --name "$NAME" --restart no -p "127.0.0.1:$PORT:5432" -e POSTGRES_USER=hindsight \
        -e POSTGRES_DB=hindsight -e POSTGRES_PASSWORD=walter-test-only \
        --tmpfs /var/lib/postgresql/data:rw,size=2g pgvector/pgvector:pg16 >/dev/null
      for _ in $(seq 30); do docker exec "$NAME" pg_isready -U hindsight -q && break; sleep 1; done
      sleep 2
    fi
    cd "$HERE" && WALTER_MEMORY_DATABASE_URL="$DSN" walter-python -m walter_memory.cli migrate >/dev/null
    WALTER_MEMORY_DATABASE_URL="$DSN" walter-python -m walter_memory.cli types sync >/dev/null
    # Walter Router's call log, read by runs/episodes (owned by the router module): an empty stand-in
    docker exec -i "$NAME" psql -q -U hindsight -d hindsight >/dev/null <<'SQL'
create schema if not exists models;
create table if not exists models.exec_log (exec_id bigserial primary key, at timestamptz not null default now(),
  task text, role text, model_id text, provider text, model text, ok boolean not null, skipped text, seconds real,
  cost_usd real, fallback_for text, kind text not null default 'text', run_id uuid, task_id uuid, usage jsonb,
  cost_status text not null default 'unknown');
SQL
    echo "$DSN" ;;
esac
