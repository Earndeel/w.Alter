-- Memory generations (2026-11-02, Memory V1 P1.0): pre-V1 interpretations (g0) and V1 interpretations (g1) live side
-- by side; what Walter reads is the set of readable generations, so the switch g0 → g1 is one row and is reversible.
-- Generations apply to interpretations only (derived knowledge, projections). Canonical events and objects have no
-- generation: they are the shared evidence of every generation, always searchable.
begin;

create table if not exists core.generations (
    generation   text primary key,
    status       text not null check (status in ('active', 'candidate', 'archived')),
    readable     boolean not null default true,
    description  text not null default '',
    created_at   timestamptz not null default now(),
    activated_at timestamptz,
    note         text
);
comment on table core.generations is 'memory generations: readable = read by default (memory_context, search, views); archived ones only on explicit history requests. Switch = walter-memory generations switch (owner decision)';
insert into core.generations (generation, status, readable, description, activated_at) values
    ('g0', 'active', true, 'pre-V1 interpretations: Hindsight, user_model_compiler, L3 v1, legacy subject views', now()),
    ('g1', 'candidate', true, 'Memory V1 interpretations: extract2 (from extraction.state v1_start), curated documents', null)
on conflict (generation) do nothing;

-- Safe default: a producer that does not say its generation writes history (g0), never the V1.
alter table core.derived_items add column if not exists generation text not null default 'g0'
    references core.generations (generation);
alter table views.view add column if not exists generation text not null default 'g0'
    references core.generations (generation);
update core.derived_items set generation = 'g1'
 where derived_by in ('l3.extract', 'documents') and generation <> 'g1';
create index if not exists derived_generation on core.derived_items (generation, kind, status);
comment on column core.derived_items.generation is 'memory generation (core.generations); default g0 = history';

-- The index carries the generation of the derived row it copies (null for events: evidence has no generation).
alter table search.chunks add column if not exists generation text;
update search.chunks c set generation = d.generation
  from core.derived_items d where c.kind = 'derived' and d.item_id = c.ref_id and c.generation is distinct from d.generation;
comment on column search.chunks.generation is 'copy of core.derived_items.generation for derived chunks; null = canonical evidence';

-- No contamination: a V1 interpretation never cites, replaces, contests or confirms a pre-V1 one. The only bridge is an
-- explicit import (role imported_from), reserved to the bootstrap the owner decides.
create or replace function core.guard_generation_provenance() returns trigger language plpgsql as $$
declare g_target text; g_source text;
begin
    if new.target_table = 'derived_items' and new.source_type = 'derived' and new.role <> 'imported_from' then
        select generation into g_target from core.derived_items where item_id::text = new.target_id;
        select generation into g_source from core.derived_items where item_id::text = new.source_id;
        if g_target is distinct from g_source then
            raise exception 'generation guard: % item % cannot % % item % (use an explicit import)',
                g_target, new.target_id, new.role, g_source, new.source_id;
        end if;
    end if;
    return new;
end $$;
drop trigger if exists provenance_generation_guard on core.provenance;
create trigger provenance_generation_guard before insert on core.provenance
    for each row execute function core.guard_generation_provenance();
commit;
