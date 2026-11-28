-- Episodic memory (2026-11-03, Memory V1 P1.3-P1.6). Additive; nothing existing is rewritten.
--  * Entities beyond people (P1.3): project, place, organization, work, merchant live in core.entities (entity_type is
--    free text); an entity can carry its own privacy class (a place learned from GPS is local_only: its coordinates and
--    even its name — a Wi-Fi network — stay on the VM).
--  * Relations (P1.3): core.relationships gains a privacy class, attributes and a generation, so V1 relations
--    (works_on, visited, attended, met, part_of…) are dated, sourced and filtered like knowledge.
--  * Flows (P1.4) and episodes / periods (P1.5-P1.6) reuse core.derived_items (observed signals: visit, conversation,
--    appointment, work_session; episode facets: kind facet, epistemic inferred) and views.* (kind episode / period):
--    only indexes are added for their time-window reads.
begin;
alter table core.entities add column if not exists privacy_class text;
alter table core.entities drop constraint if exists entities_privacy_class_check;
alter table core.entities add constraint entities_privacy_class_check check (privacy_class is null or privacy_class = any (
    array['local_only', 'redacted_cloud', 'cloud_allowed']));
comment on column core.entities.privacy_class is 'null = as its identities (people); places learned from GPS are local_only';
create index if not exists entities_type_name on core.entities (entity_type, lower(canonical_name));

alter table core.relationships add column if not exists privacy_class text;
alter table core.relationships drop constraint if exists relationships_privacy_class_check;
alter table core.relationships add constraint relationships_privacy_class_check check (privacy_class is null or
    privacy_class = any (array['local_only', 'redacted_cloud', 'cloud_allowed']));
alter table core.relationships add column if not exists attributes jsonb not null default '{}';
alter table core.relationships add column if not exists generation text references core.generations (generation);
comment on column core.relationships.privacy_class is 'strictest class of its source events (null = legacy identity rows)';
create index if not exists relationships_subject on core.relationships (subject_id, predicate);
create index if not exists relationships_object on core.relationships (object_id, predicate);
create unique index if not exists relationships_v1_unique on core.relationships (subject_id, predicate, object_id, derived_by)
    where generation = 'g1';

create index if not exists derived_g1_signals on core.derived_items (derived_by, valid_from)
    where generation = 'g1' and derived_by like 'flows.%';
create index if not exists derived_g1_kind_time on core.derived_items (kind, valid_from) where generation = 'g1';
create index if not exists view_kind_window on views.view (kind, starts_at) where generation = 'g1';
commit;
