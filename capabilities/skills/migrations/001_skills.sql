-- walter-skills (P10, 2026-10-09): registry of W.Alter's procedural memory, independent of the runtime.
-- The bytes live in the git store /opt/walter-skills (skills/, archive/, drafts/); this schema is the catalogue,
-- the retrieval journal (what was suggested to which agent) and the curator's ledger. Queries are not stored here
-- (walter_logs has them): only a hash and a length.
begin;
create schema if not exists skills;
comment on schema skills is 'walter-skills: catalogue, retrieval journal and curator ledger of the skills store /opt/walter-skills';

create table if not exists skills.catalog (
    name         text primary key,
    state        text not null check (state in ('active', 'archived', 'draft')),
    domain       text,
    owner        text,                          -- walter | upstream (bundled/hub: read-only to the curator)
    origin       text,                          -- hermes-agent, hermes-bundled, hermes-hub, hermes-archive(-restored), walter
    description  text,
    summary      text,                          -- trigger card summary
    path         text not null,
    content_sha  text not null,
    card_sha     text,                          -- content_sha the card was generated from (stale card if different)
    updated_at   timestamptz not null default now(),
    meta         jsonb not null default '{}'
);

create table if not exists skills.retrievals (
    id           bigserial primary key,
    at           timestamptz not null default now(),
    runtime      text,                          -- claude_code, codex, dsh, hermes, mcp
    session_id   text,
    mode         text not null,                 -- inject | shadow | search
    query_sha    text,
    query_chars  integer,
    results      jsonb not null,                -- [{name, score}] ranked
    injected     text[] not null default '{}',
    latency_ms   integer,
    model        text                           -- retriever version (encoder + learner)
);
create index if not exists retrievals_session on skills.retrievals (session_id, at);
create index if not exists retrievals_at on skills.retrievals (at);

create table if not exists skills.reads (
    id           bigserial primary key,
    at           timestamptz not null default now(),
    runtime      text,
    session_id   text,
    name         text not null,
    via          text not null                  -- mcp_skill_read | inject | hermes_skill_view
);
create index if not exists reads_session on skills.reads (session_id, at);

create table if not exists skills.ledger (
    id           bigserial primary key,
    at           timestamptz not null default now(),
    actor        text not null,                 -- curator.<poste> | sync | user | agent
    action       text not null,                 -- import, restore, patch, merge, archive, card, train ...
    name         text,
    git_commit   text,
    evidence     jsonb not null default '{}'
);
create index if not exists ledger_name on skills.ledger (name, at);
commit;
