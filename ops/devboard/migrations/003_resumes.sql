-- The owner's « Reprendre » button (2026-11-15): each resume of a card is one turn of a Walter Engine conversation
-- of that card (web door, the owner's full access), followed here until it ends. Never a second running resume.
begin;
create table if not exists devboard.resumes (
  id serial primary key,
  card_id int not null references devboard.cards(id) on delete cascade,
  session_id text not null,                 -- Engine API conversation (web/<account>/devboard-w-<n>)
  walter_session text,                      -- dsh/vm/<kernel id>: the same conversation in Walter Web and walter_logs
  request_id text not null unique,          -- idempotency key of the turn: a replay never runs twice
  note text,                                -- the owner's instruction typed with the click (may be empty)
  status_before text not null,
  status text not null default 'running'
    check (status in ('running', 'ok', 'cancelled', 'budget_exhausted', 'error', 'interrupted', 'unknown_outcome',
                      'lost')),
  outcome text check (outcome in ('done', 'waiting_owner', 'in_progress', 'abandoned')),
  summary text,                             -- the engine's closing report (trimmed)
  started_at timestamptz not null default now(),
  ended_at timestamptz);
create unique index if not exists resumes_one_running on devboard.resumes (card_id) where status = 'running';
comment on table devboard.resumes is 'Owner resumes of a card: one Walter Engine turn each, followed until it ends.';
insert into devboard.migrations (version) values ('003_resumes') on conflict do nothing;
commit;
