-- The catalogue showed media prices only: text models now carry their cheapest paid token prices
-- (USD per 1M input / output tokens, and AA's 3:1 blended price) and their subscription route.
begin;
create or replace view models.catalog as
with o as (
    select o.* from models.offers o join models.latest_snapshots s using (snapshot_id)
), g as (
    select model_id, interface,
           array_agg(distinct provider order by provider) as providers,
           min(norm_price) filter (where offer_kind = 'generation') as price_min,
           max(norm_price) filter (where offer_kind = 'generation') as price_max,
           mode() within group (order by norm_unit) filter (where offer_kind = 'generation' and norm_price is not null)
               as price_unit,
           array_agg(distinct resolution) filter (where offer_kind = 'generation' and resolution is not null) as resolutions,
           min(provider_created) as released,
           count(*) as offers
    from o group by model_id, interface
), m as (
    select model_id, interface, array_agg(distinct mode order by mode) as modes
    from o, unnest(o.modes) as mode where o.offer_kind = 'generation' group by model_id, interface
), t as (
    select distinct on (model_id) model_id, provider as token_provider, price_in_1m, price_out_1m,
           (3 * price_in_1m + price_out_1m) / 4 as blended_1m
    from o where interface = 'chat' and access = 'paid' and price_in_1m is not null and price_out_1m is not null
    order by model_id, (3 * price_in_1m + price_out_1m) / 4
), sub as (
    select model_id, array_agg(distinct provider) as subscriptions from o where access in ('subscription', 'ui')
    group by model_id
)
select g.model_id, coalesce(c.display_name, g.model_id) as name, g.interface, coalesce(m.modes, '{}') as modes,
       g.providers, g.price_min, g.price_max, g.price_unit, coalesce(g.resolutions, '{}') as resolutions, g.released,
       g.offers, coalesce(b.scores, '{}') as scores, b.scores is not null as ranked,
       c.open_weights, c.license, c.content_policy, c.base_model_id,
       case when g.interface = 'chat' then t.price_in_1m end as price_in_1m,
       case when g.interface = 'chat' then t.price_out_1m end as price_out_1m,
       case when g.interface = 'chat' then t.blended_1m end as blended_1m,
       case when g.interface = 'chat' then t.token_provider end as token_provider,
       coalesce(sub.subscriptions, '{}') as subscriptions
from g join models.canonical c using (model_id)
left join m using (model_id, interface)
left join models.model_scores b using (model_id)
left join t using (model_id)
left join sub using (model_id);
insert into models.schema_migrations (version) values ('011_catalog_chat_prices') on conflict do nothing;
commit;
