-- walter-skills registry v2 (2026-10-10): everything derived or observed lives here; git keeps only the content.
-- cards   : trigger cards (one per skill, keyed by the content hash they were generated from)
-- labels  : relevance truth the ranker learns from — judge (sampled), bench (frozen benchmark), implicit (the agent's
--           own choices: shown→opened, searched→opened-not-shown). qid = sha1 of the normalised message (no text here)
-- rankers : trained ranker versions; exactly one 'active'; candidates are evaluated before promotion
-- state   : small key/value state of jobs (watermarks, last runs) — no state files on disk
begin;
create table if not exists skills.cards (
    name         text primary key,
    content_sha  text not null,
    model        text,
    version      text,
    card         jsonb not null,
    created_at   timestamptz not null default now()
);

create table if not exists skills.labels (
    qid          text not null,
    skill        text not null,
    label        smallint not null check (label in (0, 1, 2)),
    source       text not null check (source in ('bench', 'judge', 'implicit', 'miss')),
    weight       real not null default 1.0,
    runtime      text,
    at           timestamptz not null default now(),
    evidence     jsonb not null default '{}',
    primary key (qid, skill, source)
);
create index if not exists labels_at on skills.labels (at);

create table if not exists skills.rankers (
    version      text primary key,
    state        text not null check (state in ('candidate', 'active', 'retired', 'rejected')),
    created_at   timestamptz not null default now(),
    promoted_at  timestamptz,
    encoder      text not null,
    learner      text not null,
    skills       integer,
    metrics      jsonb not null default '{}',
    blob         bytea not null
);
create unique index if not exists rankers_one_active on skills.rankers ((state)) where state = 'active';

create table if not exists skills.state (
    key          text primary key,
    value        jsonb not null,
    updated_at   timestamptz not null default now()
);
commit;
