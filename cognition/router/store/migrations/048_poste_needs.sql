-- 2026-11-22 (owner): a challenger is judged against what the poste really uses (D1.2 Ultra was kept for several
-- decisions per call and image reading, not for one AA point). One row per poste (task + level): what its real calls
-- ask (gateway journal, counted, never copied) and what its modules declare (Walter Decision needs).
begin;
create table if not exists models.poste_needs (
  task text not null,
  level text not null default '',
  calls integer not null default 0,
  window_days integer not null,
  inputs jsonb not null default '{}'::jsonb,
  tools_share double precision,
  json_share double precision,
  max_n integer,
  input_tokens_p95 integer,
  input_tokens_max integer,
  output_tokens_max integer,
  decision_kinds text[],
  updated_at timestamptz not null default now(),
  primary key (task, level)
);
comment on table models.poste_needs is 'What each poste really uses, rebuilt each cycle by analysis/needs.py from the walter-llm journal (counts only) and the declared Walter Decision needs; models.model_details says whether a challenger can do it.';
comment on column models.poste_needs.level is 'L1/L2/L3 for a text tier, empty for a poste without levels.';
comment on column models.poste_needs.inputs is '{part type: share of calls} beyond text (image_url, input_audio, file…).';
comment on column models.poste_needs.tools_share is 'Share of calls that give the model tools.';
comment on column models.poste_needs.json_share is 'Share of calls that ask for a JSON answer (response_format).';
comment on column models.poste_needs.max_n is 'Most answers asked in one call (n).';
comment on column models.poste_needs.input_tokens_p95 is '95th percentile of the input size (tokens).';
comment on column models.poste_needs.input_tokens_max is 'Largest input seen (tokens): a challenger''s context must hold it.';
comment on column models.poste_needs.output_tokens_max is 'Longest answer seen (tokens).';
comment on column models.poste_needs.decision_kinds is 'Question kinds the decision modules ask (choice, noul, multiple, spans…).';
comment on column models.poste_needs.task is 'Router task (poste), as the gateway journal names it before its /level.';
comment on column models.poste_needs.calls is 'Successful real calls seen in the window.';
comment on column models.poste_needs.window_days is 'Days of journal read.';
comment on column models.poste_needs.updated_at is 'When the cycle last rebuilt this row.';
insert into models.schema_migrations (version) values ('048_poste_needs') on conflict do nothing;
commit;
