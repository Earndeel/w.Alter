-- 2026-10-02: Telegram only when a new model ranks above one of the ACTIVE models ('new_best' for the
-- auto-picked #1 of a specialised task, 'challenger' for a favourite, 'tier' for a text tier). Plus the learning
-- loop: every routed execution is logged (reliability) and the owner's feedback on a model is kept (scoring).
begin;
alter table models.alerts drop constraint if exists alerts_kind_check;
alter table models.alerts add constraint alerts_kind_check
    check (kind in ('challenger', 'unranked', 'source_stale', 'top3', 'billing', 'tier', 'new_best'));

create table if not exists models.exec_log (
    exec_id     bigserial primary key,
    at          timestamptz not null default now(),
    task        text,
    role        text,
    model_id    text,
    provider    text,             -- Hermes provider name (openai-codex, kie, kie-codex, openrouter, arnict...)
    model       text,             -- model id at that provider
    ok          boolean not null,
    skipped     text,             -- not run: provider test failed / known down
    seconds     real,
    cost_usd    real,
    fallback_for text,
    kind        text not null default 'text'   -- text | image | video | music | audio
);
create index if not exists exec_log_recent on models.exec_log (provider, model_id, at desc);

create table if not exists models.feedback (
    feedback_id bigserial primary key,
    at          timestamptz not null default now(),
    model_id    text not null references models.canonical,
    task        text,
    rating      int not null check (rating between -2 and 2),
    note        text,
    source      text not null default 'owner'
);

insert into models.schema_migrations (version) values ('014_new_best_exec_feedback') on conflict do nothing;
commit;
