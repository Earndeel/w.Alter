-- Walter Memory — PostgreSQL extensions the schema needs (2026-10-29, Walter Clean). They were installed by hand on
-- the first database; a blank database gets them here. Idempotent.
create extension if not exists pgcrypto;   -- gen_random_uuid() defaults
create extension if not exists vector;     -- pgvector: embeddings (search.chunks, views)
create extension if not exists pg_trgm;    -- trigram indexes
create extension if not exists unaccent;   -- accent-insensitive full-text search
