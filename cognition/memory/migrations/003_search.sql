-- Walter Memory P3 — unified search layer (derived, rebuildable from core.events / core.derived_items / core.objects).
begin;
create extension if not exists unaccent;
create schema if not exists search;
comment on schema search is 'Walter Memory search index: chunks of events, derived items and object texts with multilingual FTS + local embeddings. Fully rebuildable.';

create or replace function search.f_unaccent(text) returns text language sql immutable parallel safe strict as
$$ select public.unaccent('public.unaccent'::regdictionary, $1) $$;

create table if not exists search.chunks (
    chunk_id     bigserial primary key,
    kind         text not null check (kind in ('event','derived','object')),
    ref_id       uuid not null,                      -- core.events.event_id / core.derived_items.item_id / core.objects.id
    chunk_no     int  not null default 0,
    occurred_at  timestamptz,
    source       text not null,
    label        text not null,                      -- event_type / derived kind / object kind
    thread_id    text,
    actor_identity_id uuid,
    text         text not null,
    lang         text not null default 'simple',
    tsv          tsvector not null,
    embedding    vector(256),
    privacy_class text not null,
    hidden       boolean not null default false,     -- quarantined derived items, retracted events
    dup_of       bigint,                             -- same content observed through another source
    content_hash text,
    indexer_version text not null,
    created_at   timestamptz not null default now(),
    unique (kind, ref_id, chunk_no)
);
create index if not exists chunks_tsv on search.chunks using gin (tsv);
create index if not exists chunks_time on search.chunks (occurred_at desc);
create index if not exists chunks_source_label on search.chunks (source, label);
create index if not exists chunks_thread on search.chunks (thread_id);
create index if not exists chunks_hash on search.chunks (content_hash);
commit;
