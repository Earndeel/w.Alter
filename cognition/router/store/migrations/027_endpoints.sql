-- 2026-10-22 (owner: « la partie providers : celui qui propose le modèle au meilleur prix »). A gateway such as
-- OpenRouter serves one model through several hosts (Parasail, DeepInfra, Bedrock…) at different prices, compression
-- (quantization) and reliability. research.prices.openrouter_endpoints reads them for the models of the active library.
begin;
create table if not exists models.endpoints (
    snapshot_id   bigint not null references models.snapshots(snapshot_id) on delete cascade,
    gateway       text not null,              -- openrouter
    model_id      text not null,              -- router model id
    gateway_model text not null,              -- e.g. deepseek/deepseek-v4-pro
    host          text not null,              -- provider_name (Parasail, Amazon Bedrock…)
    tag           text not null,              -- the gateway's routing tag (parasail/fp8, amazon-bedrock/eu-west-1)
    service_tier  text,                       -- flex (cheaper, slower, background), priority / fast, null = standard
    quantization  text,                       -- fp4, fp8, bf16… ('unknown' when the host does not say)
    price_in_1m   double precision,
    price_out_1m  double precision,
    cache_read_1m double precision,
    context_length bigint,
    uptime_1d     double precision,           -- % of successful requests over 24 h
    uptime_30m    double precision,
    status        integer,                    -- gateway status (0 = ok, negative = degraded / down)
    latency_ms    double precision,
    throughput_tps double precision,
    tools         boolean,
    structured    boolean,
    primary key (snapshot_id, gateway, gateway_model, tag)
);
create index if not exists endpoints_model on models.endpoints (model_id);
comment on table models.endpoints is 'Hosts of a model behind a gateway (OpenRouter): price, quantization, reliability, speed, tool / structured-output support. One row per host per snapshot';

-- A host is usable when it is reliable (>= 95 % successful over 24 h; unknown uptime ranked after measured hosts)
-- and does not serve the model below its native precision: 4/6-bit formats only when the model's own vendor
-- serves that same format (Kimi K3 is released in mxfp4 by Moonshot AI).
create or replace view models.usable_endpoints as
with latest as (select * from models.endpoints
                where snapshot_id = (select snapshot_id from models.latest_snapshots where kind = 'or_endpoints')),
vendor as (select distinct on (gateway_model) gateway_model, quantization as native
           from latest where split_part(tag, '/', 1) = split_part(gateway_model, '/', 1)
           order by gateway_model, price_in_1m)
select l.*, (3 * l.price_in_1m + l.price_out_1m) / 4 as blended_1m, v.native as vendor_quantization
from latest l left join vendor v using (gateway_model)
where l.price_in_1m is not null
  and coalesce(l.uptime_1d, 100) >= 95
  and (coalesce(l.quantization, 'unknown') !~ '(fp4|int4|fp6|int6)'
       or l.quantization = v.native);
comment on view models.usable_endpoints is 'Hosts of the latest snapshot that are reliable (>= 95 % over 24 h) and not below the vendor''s own precision';

-- Interactive work: standard and priority tiers only. Background work (summaries, memory, analysis) may use flex.
create or replace view models.best_endpoints as
select distinct on (model_id, usage) * from (
    select u.*, 'interactive' as usage from models.usable_endpoints u where coalesce(u.service_tier, '') <> 'flex'
    union all
    select u.*, 'background' as usage from models.usable_endpoints u) x
order by model_id, usage, uptime_1d is null, blended_1m, uptime_1d desc nulls last;
comment on view models.best_endpoints is 'Cheapest usable host per model and usage (interactive: no flex tier; background: flex allowed), 3:1 input:output blend';
insert into models.schema_migrations (version) values ('027_endpoints') on conflict do nothing;
commit;
