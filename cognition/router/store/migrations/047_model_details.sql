-- 2026-11-22 (owner): « dans la DB, les détails de chaque modèle : les inputs qu'ils prennent, combien de tokens
-- maximal… » — one row per model with what its providers' free catalogues say it can do, refreshed every cycle
-- (no call is added: the OpenRouter catalogue and the Codex account catalogue are already read by the cycle).
begin;
create table if not exists models.model_details (
  model_id text primary key,
  context_length integer,
  max_output_tokens integer,
  input_modalities text[],
  output_modalities text[],
  parameters text[],
  reasoning_efforts text[],
  reasoning_default text,
  knowledge_cutoff text,
  expires text,
  sources jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
comment on table models.model_details is 'What each model can do, from its providers'' free catalogues (OpenRouter models list, Codex account catalogue), rebuilt each cycle by analysis/details.py; the widest value of its sources wins.';
comment on column models.model_details.context_length is 'Largest input window any source announces (tokens).';
comment on column models.model_details.max_output_tokens is 'Largest answer any source allows (tokens); null = not published.';
comment on column models.model_details.input_modalities is 'What it reads: text, image, audio, video, file.';
comment on column models.model_details.output_modalities is 'What it writes: text, image, audio…';
comment on column models.model_details.parameters is 'Request parameters supported (tools, response_format, structured_outputs, reasoning, n, logprobs…), union of its routes.';
comment on column models.model_details.reasoning_efforts is 'Reasoning efforts it accepts (none, low, medium, high, xhigh, max…).';
comment on column models.model_details.reasoning_default is 'Effort used when none is asked.';
comment on column models.model_details.knowledge_cutoff is 'Training data cutoff as published by a source.';
comment on column models.model_details.expires is 'Date its provider will retire it, when announced.';
comment on column models.model_details.sources is '{field: [source…]}: which catalogue said each value.';
comment on column models.model_details.model_id is 'Canonical model id (models.canonical).';
comment on column models.model_details.updated_at is 'When the cycle last rebuilt this row.';
insert into models.schema_migrations (version) values ('047_model_details') on conflict do nothing;
commit;
