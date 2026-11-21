-- Memory views rebuilt from evidence (2026-11-02, Memory V1 P1.2).
--  * views.evidence: what a view is built from (knowledge items, events, objects, log positions, other views), with
--    a role; read backwards it is the dependency graph: which views to rebuild when an item changes.
--  * Privacy from creation, enforced here: a view's class is the strictest class of its evidence (adding evidence can
--    only tighten it), a version can never be less strict than its view, and a view is never declassified by the
--    builder (only an explicit owner decision sets walter.declassify). A cloud projection of a subject that also has
--    local_only evidence is a distinct view built from cloud evidence only.
--  * Kinds (subject, episode, person, project, place, period, run), time window, epistemic status, confidence and
--    entities on views; stale_since / inputs_hash on versions (targeted invalidation, no rebuild without change).
--  * status 'shadow': built and measured, never served by default (P1.2 runs in shadow).
begin;
alter table views.view add column if not exists kind text not null default 'subject';
alter table views.view drop constraint if exists view_kind_check;
alter table views.view add constraint view_kind_check check (kind in ('subject', 'episode', 'person', 'project', 'place', 'period', 'run'));
alter table views.view add column if not exists starts_at timestamptz;
alter table views.view add column if not exists ends_at timestamptz;
alter table views.view add column if not exists tz text;
alter table views.view add column if not exists epistemic text;
alter table views.view drop constraint if exists view_epistemic_check;
alter table views.view add constraint view_epistemic_check check (epistemic is null or epistemic in ('candidate', 'probable', 'confirmed', 'rejected'));
alter table views.view add column if not exists confidence real;
alter table views.view add column if not exists entity_ids uuid[] not null default '{}';
alter table views.view add column if not exists attributes jsonb not null default '{}';
alter table views.view drop constraint if exists view_status_check;
alter table views.view add constraint view_status_check check (status in ('active', 'dormant', 'merged', 'retired', 'shadow'));

alter table views.version add column if not exists stale_since timestamptz;
alter table views.version add column if not exists inputs_hash text;

create table if not exists views.evidence (
    view_key      text not null references views.view (view_key) on delete cascade,
    ref_kind      text not null check (ref_kind in ('derived', 'event', 'object', 'log', 'view')),
    ref_id        text not null,
    role          text not null default 'contains',
    confidence    real,
    privacy_class text not null check (privacy_class in ('local_only', 'redacted_cloud', 'cloud_allowed')),
    added_by      text not null,
    at            timestamptz not null default now(),
    primary key (view_key, ref_kind, ref_id, role)
);
create index if not exists evidence_ref on views.evidence (ref_kind, ref_id);
comment on table views.evidence is 'what a view is built from (role: contains, planned_by, located_by, paid_by, confirmed_by, mentions, member); backwards = which views depend on a ref';

create or replace function views.rank(c text) returns int language sql immutable as $$
    select case c when 'cloud_allowed' then 0 when 'redacted_cloud' then 1 else 2 end $$;

create or replace function views.evidence_tightens() returns trigger language plpgsql as $$
begin
    update views.view set privacy_class = new.privacy_class, updated_at = now()
     where view_key = new.view_key and views.rank(new.privacy_class) > views.rank(privacy_class);
    return new;
end $$;
drop trigger if exists evidence_tightens on views.evidence;
create trigger evidence_tightens after insert or update on views.evidence
    for each row execute function views.evidence_tightens();

create or replace function views.version_not_looser() returns trigger language plpgsql as $$
declare v text;
begin
    select privacy_class into v from views.view where view_key = new.view_key;
    if views.rank(new.privacy_class) < views.rank(v) then
        raise exception 'privacy: version % of % is % but its view is % (strictest evidence)',
            new.version, new.view_key, new.privacy_class, v;
    end if;
    return new;
end $$;
drop trigger if exists version_not_looser on views.version;
create trigger version_not_looser before insert on views.version
    for each row execute function views.version_not_looser();

create or replace function views.no_declassify() returns trigger language plpgsql as $$
begin
    if views.rank(new.privacy_class) < views.rank(old.privacy_class)
       and coalesce(current_setting('walter.declassify', true), '') <> 'on' then
        raise exception 'privacy: view % cannot go from % to % without an explicit owner decision',
            old.view_key, old.privacy_class, new.privacy_class;
    end if;
    return new;
end $$;
drop trigger if exists view_no_declassify on views.view;
create trigger view_no_declassify before update of privacy_class on views.view
    for each row execute function views.no_declassify();
commit;
