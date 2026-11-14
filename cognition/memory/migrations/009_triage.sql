-- V3 environmental input (2026-10-04): every new incoming event (Beeper message, e-mail, calendar event) gets ONE
-- triage decision: ignore / remember / notify / prepare_reply (+ urgency, category, needs_reply). Decided by a cheap
-- decision model (Clef on Cloudflare Workers AI) on a privacy-safe Context Lite, then by Monsieur's deterministic
-- rules (silence hours, VIP / muted threads, groups). Starts in SHADOW mode: decisions are recorded, nothing is sent.
begin;
create schema if not exists triage;
create table if not exists triage.decisions (
    decision_id  bigserial primary key,
    event_id     uuid not null,
    occurred_at  timestamptz not null,
    source       text not null,
    thread_id    text,
    decided_at   timestamptz not null default now(),
    model_action text,               -- what the decision model proposed
    action       text not null check (action in ('ignore', 'remember', 'notify', 'prepare_reply')),
    urgency      text check (urgency in ('now', 'today', 'later')),
    category     text,
    needs_reply  boolean,
    confidence   real,
    model        text,
    rule         text,               -- the deterministic rule that set or changed the action
    shadow       boolean not null default true,
    delivered_at timestamptz,
    payload      jsonb not null default '{}',
    unique (event_id)
);
create index if not exists triage_decisions_time on triage.decisions (decided_at desc);
create index if not exists triage_decisions_action on triage.decisions (action, delivered_at);
insert into ingestion.connectors (connector, source, mode, description, freshness_target) values
  ('triage', 'beeper', 'pull', 'Triage of new incoming events (Beeper, Gmail, Calendar) by Clef + Monsieur rules', '15 minutes')
on conflict (connector) do nothing;
commit;
