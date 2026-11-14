-- 2026-10-22 (owner: « en prenant en compte aussi les abonnements et le prix de revient du token avec ceux-ci »):
-- what a token really costs through a subscription = plan price / API value it carries per month. Recorded by the
-- plans research; routes read the latest row (cheap) to price subscription routes and to know the quota left.
begin;
create table if not exists models.subscription_costs (
    sub_id                 text not null,
    at                     timestamptz not null default now(),
    price_usd_month        double precision not null,
    api_value_month_pace   double precision,   -- API value of the tokens really used, last 7 days x 4.35
    api_value_month_full   double precision,   -- measured capacity (meter points) or, failing that, SemiAnalysis
    ratio_pace             double precision,   -- price / value at the current pace: share of the API price paid
    ratio_full             double precision,   -- same when the plan is used to its capacity
    used_percent           double precision,   -- weekly meter when recorded
    detail                 jsonb not null default '{}',
    primary key (sub_id, at)
);
comment on table models.subscription_costs is 'Cost price of a token through each subscription: plan price / API value carried per month (at the current pace and at full capacity). Recorded by research plans';
create or replace view models.latest_subscription_costs as
select distinct on (sub_id) * from models.subscription_costs order by sub_id, at desc;
comment on view models.latest_subscription_costs is 'Latest cost price per subscription';
insert into models.schema_migrations (version) values ('028_subscription_costs') on conflict do nothing;
commit;
