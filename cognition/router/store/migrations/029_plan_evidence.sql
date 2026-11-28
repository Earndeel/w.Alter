-- 2026-10-22 (owner: « pour les calculs tokens by plans … peut-être qu'il existe d'autres données sur le web ; cela doit
-- faire partie du cycle de recherche par plan »). Every published or measured fact about a plan, with its source:
-- web research (SemiAnalysis / Tokenomics, vendors' limit pages, other analyses), billing e-mails, our own measures.
begin;
create table if not exists models.plan_evidence (
    evidence_id  bigserial primary key,
    sub_id       text,                 -- the owner's plan it concerns (null = a plan he does not have)
    vendor       text not null,
    plan         text not null,
    model_id     text,                 -- null = the whole plan
    metric       text not null check (metric in ('usd_value_month', 'tokens_month', 'messages_5h', 'messages_week',
                                                  'price_usd_month', 'limit_note', 'plan_change')),
    value        double precision,
    unit         text,
    source_name  text not null,
    source_url   text,
    published    date,
    quote        text,
    origin       text not null check (origin in ('web', 'email', 'owner', 'measure')),
    found_at     timestamptz not null default now(),
    unique (sub_id, model_id, metric, source_url, value)
);
comment on table models.plan_evidence is 'Facts about subscription plans with their source: value of a plan at API prices, tokens or messages per window, price, limits, changes (web research, billing e-mails, owner, our measures)';
insert into models.schema_migrations (version) values ('029_plan_evidence') on conflict do nothing;
commit;
