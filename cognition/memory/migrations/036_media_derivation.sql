-- Media derivation (SOCLE A5, 2026-11-11): every Raw Vault object gets a derived text (transcript, extract, OCR or
-- caption) that is found from its message. Additive and idempotent.
--  1. a NEW object is published on the bus too (memory.object, payload text = false), so the media processor of the
--     event-driven assimilation derives it within seconds; a new or changed derived text is published as before
--     (payload text = true → the search index).
--  2. the message → attachments lookup (core.object_links by target) gets its index: memory_events, objects.search by
--     thread / event and the attachment lines resolve links at read time (append-only events are never rewritten).
--  3. the objects still waiting for a derived text are found without a scan (media status / backfill).
begin;

create or replace function core.publish_object() returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' and new.derived_text is not distinct from old.derived_text then
        return null;
    end if;
    if tg_op = 'INSERT' and new.derived_text is null then        -- a new file: its derivation is due
        insert into bus.events (type, source, subject, payload)
        values ('memory.object', 'memory', new.id::text,
                jsonb_build_object('op', 'insert', 'kind', new.kind, 'privacy_class', new.privacy_class, 'text', false));
        return null;
    end if;
    if new.derived_text is null then
        return null;
    end if;
    insert into bus.events (type, source, subject, payload)
    values ('memory.object', 'memory', new.id::text,
            jsonb_build_object('op', lower(tg_op), 'kind', new.kind, 'privacy_class', new.privacy_class, 'text', true));
    return null;
end $$;
comment on function core.publish_object() is 'publishes a new Raw Vault object (text=false: to derive) and a new or changed derived text (text=true: to index) as bus memory.object (same transaction)';
drop trigger if exists objects_publish on core.objects;
create trigger objects_publish after insert or update of derived_text on core.objects
    for each row execute function core.publish_object();

create index if not exists object_links_target on core.object_links (target_type, target_id);
create index if not exists objects_underived on core.objects (kind, captured_at)
    where derived_at is null and purged_at is null;

commit;
