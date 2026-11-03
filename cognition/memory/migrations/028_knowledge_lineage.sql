-- Knowledge lineage and epistemic status as columns (2026-11-02, Memory V1 P1.2). P1.1 only had them as attributes.
--   lineage_id  every version of the same knowledge (a supersession keeps the lineage; the current version is the one
--               still derived/verified); a new item starts its own lineage
--   epistemic   who establishes it: stated_owner, agent_reported, stated_third_party, observed, inferred (hypothesis)
--   stage       where an intention stands: requested (the owner asked) → proposed (W.Alter proposed) → decided (the owner
--               validated) → executed (reported done) → verified (evidence of the result) | abandoned; commitments
--               open | done; plain statements: stated
--   scope       how long it holds: durable, task (for the work under way: expires with it), until (valid_to)
-- Pre-V1 (g0) rows are left as they are (null = legacy).
begin;
alter table core.derived_items add column if not exists lineage_id uuid;
alter table core.derived_items add column if not exists epistemic text;
alter table core.derived_items add column if not exists stage text;
alter table core.derived_items add column if not exists scope text;
alter table core.derived_items drop constraint if exists derived_items_epistemic_check;
alter table core.derived_items add constraint derived_items_epistemic_check check (epistemic is null or epistemic = any (
    array['stated_owner', 'agent_reported', 'stated_third_party', 'observed', 'inferred']));
alter table core.derived_items drop constraint if exists derived_items_stage_check;
alter table core.derived_items add constraint derived_items_stage_check check (stage is null or stage = any (
    array['requested', 'proposed', 'decided', 'executed', 'verified', 'abandoned', 'open', 'done', 'stated']));
alter table core.derived_items drop constraint if exists derived_items_scope_check;
alter table core.derived_items add constraint derived_items_scope_check check (scope is null or scope = any (
    array['durable', 'task', 'until']));

create or replace function core.derived_lineage_default() returns trigger language plpgsql as $$
begin
    if new.lineage_id is null and new.generation = 'g1' then
        new.lineage_id := new.item_id;
    end if;
    return new;
end $$;
drop trigger if exists derived_lineage_default on core.derived_items;
create trigger derived_lineage_default before insert on core.derived_items
    for each row execute function core.derived_lineage_default();

update core.derived_items set lineage_id = coalesce(lineage_id, item_id),
       epistemic = case attributes->>'epistemic' when 'owner_stated' then 'stated_owner'
                        when 'agent_reported' then 'agent_reported' else epistemic end,
       stage = coalesce(stage, attributes->>'state'),
       scope = coalesce(scope, 'durable')
 where generation = 'g1' and derived_by = 'l3.extract' and kind <> 'summary';
create index if not exists derived_lineage on core.derived_items (lineage_id) where lineage_id is not null;
comment on column core.derived_items.lineage_id is 'all versions of one knowledge share it; current = status derived/verified';
comment on column core.derived_items.stage is 'requested → proposed → decided → executed (reported) → verified (evidence) | abandoned; commitments open|done';
comment on column core.derived_items.scope is 'durable | task (expires with the work under way) | until (valid_to)';
commit;
