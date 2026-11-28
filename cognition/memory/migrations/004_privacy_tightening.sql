-- Append-only history may still get *stricter* access control: privacy_class can be tightened, never loosened,
-- and nothing else can change outside break-glass purge. 2026-10-01. (Trigger sees partition names: events_YYYY_MM.)
begin;
create or replace function core.forbid_event_mutation() returns trigger language plpgsql as $$
declare ord text[] := array['cloud_allowed','redacted_cloud','local_only'];
begin
  if coalesce(current_setting('walter.purge', true), '') = 'on' then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'UPDATE' and tg_table_name <> 'event_keys'
     and (to_jsonb(new) - 'privacy_class') = (to_jsonb(old) - 'privacy_class')
     and array_position(ord, new.privacy_class) > array_position(ord, old.privacy_class) then
    return new;                                   -- tightening only
  end if;
  raise exception 'core.% is append-only: emit a correcting event (*.corrected / *.retracted) or use break-glass purge', tg_table_name;
end $$;
commit;
