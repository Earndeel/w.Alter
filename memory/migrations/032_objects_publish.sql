-- Event-driven search index (2026-11-03): a file's derived text (OCR, transcript, caption, extract) is published on the
-- bus (memory.object) when it appears or changes, so the index takes it within seconds instead of on a timer.
begin;

create or replace function core.publish_object() returns trigger language plpgsql as $$
begin
    if new.derived_text is null or (tg_op = 'UPDATE' and new.derived_text is not distinct from old.derived_text) then
        return null;
    end if;
    insert into bus.events (type, source, subject, payload)
    values ('memory.object', 'memory', new.id::text,
            jsonb_build_object('op', lower(tg_op), 'kind', new.kind, 'privacy_class', new.privacy_class));
    return null;
end $$;
comment on function core.publish_object() is 'publishes a new or changed derived text of a Raw Vault object as bus memory.object (same transaction)';
drop trigger if exists objects_publish on core.objects;
create trigger objects_publish after insert or update of derived_text on core.objects
    for each row execute function core.publish_object();

commit;
