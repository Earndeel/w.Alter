-- ops/devboard (2026-11-14): the development board. Reads documents, decisions, agent sessions, commits and the owner's
-- tasks; one model poste (devboard_reading) turns sessions into chantiers (cards). Nothing here is a source of truth:
-- DECISIONS.md, V1.md and the plans stay the truth, the board reads them. Owner corrections always win.
begin;
create schema if not exists devboard;
create table if not exists devboard.migrations (version text primary key, at timestamptz not null default now());

create table if not exists devboard.cards (
  id serial primary key,
  ref text generated always as ('W-' || id) stored unique,
  title text not null,
  module text,
  status text not null check (status in ('waiting_owner', 'in_progress', 'paused', 'done', 'abandoned')),
  owner text,
  change text,
  deadline date,
  waiting_since timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now());
comment on table devboard.cards is 'Chantiers inferred from agent sessions and tasks; every card has evidence; corrections win.';

create table if not exists devboard.card_evidence (
  id serial primary key,
  card_id int not null references devboard.cards(id) on delete cascade,
  kind text not null check (kind in ('session', 'decision', 'commit', 'task')),
  source_ref text not null,
  seq int,
  quote text,
  at timestamptz not null default now());

create table if not exists devboard.card_links (
  card_id int not null references devboard.cards(id) on delete cascade,
  kind text not null check (kind in ('decision', 'file', 'blocks')),
  target text not null,
  primary key (card_id, kind, target));

create table if not exists devboard.corrections (
  id serial primary key,
  card_id int not null references devboard.cards(id) on delete cascade,
  field text not null,
  value jsonb,
  reason text,
  by text not null default 'owner',
  at timestamptz not null default now());

create table if not exists devboard.documents (
  path text primary key,
  title text,
  kind text not null check (kind in ('vision', 'decisions', 'v1', 'architecture', 'runbook', 'module', 'report')),
  sha256 text not null,
  mtime timestamptz);

create table if not exists devboard.sections (
  doc_path text not null references devboard.documents(path) on delete cascade,
  anchor text not null,
  heading text not null,
  level int not null,
  line int not null,
  body text not null,
  sha256 text not null,
  removed_at timestamptz,
  primary key (doc_path, anchor));

create table if not exists devboard.decisions (
  id serial primary key,
  doc_path text not null,
  anchor text not null unique,
  date date not null,
  title text not null,
  sha256 text not null,
  read_sha256 text,
  removed_at timestamptz);

create table if not exists devboard.decision_links (
  newer_id int not null references devboard.decisions(id) on delete cascade,
  older_id int not null references devboard.decisions(id) on delete cascade,
  quote text,
  primary key (newer_id, older_id));

create table if not exists devboard.readings (
  key text primary key,
  kind text not null,
  source_ref text not null,
  from_seq int,
  to_seq int,
  prompt_version text not null,
  status text not null check (status in ('done', 'failed', 'skipped')),
  attempts int not null default 0,
  result jsonb,
  error text,
  at timestamptz not null default now());

create table if not exists devboard.sessions (
  session_id text primary key,
  runtime text not null,
  title text,
  cwd text,
  eligible boolean not null default true,
  read_seq int not null default 0,
  last_turn_at timestamptz,
  dirty boolean not null default false,
  state text);

create table if not exists devboard.activity (
  id bigserial primary key,
  at timestamptz not null default now(),
  kind text not null,
  source_ref text,
  card_id int references devboard.cards(id) on delete set null,
  text text not null,
  unique (kind, source_ref, card_id));
create index if not exists activity_at on devboard.activity (at desc);

create table if not exists devboard.live (
  session_id text primary key,
  runtime text not null,
  title text,
  card_id int references devboard.cards(id) on delete set null,
  at timestamptz not null default now());

create table if not exists devboard.state (key text primary key, value jsonb not null, at timestamptz not null default now());

insert into devboard.migrations (version) values ('001_devboard') on conflict do nothing;
commit;
