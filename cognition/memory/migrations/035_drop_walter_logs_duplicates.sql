-- Memory cleanup, end of phase 2 (Monsieur 2026-11-09: « finalise les nettoyages validés, y compris walter_logs.duplicates »).
-- walter_logs.duplicates was the one-off reversible quarantine of 2026-10-25 (migration 016): 39 356 later copies, every
-- one identical (type, instant, text, data, call, tool, event_key) to the original still in walter_logs.events; nothing
-- writes it (the journal's Writer skips a known event_key: idempotence lives in walter_logs.events' unique index) and
-- nothing reads it. Its rows are kept encrypted in @instance/backups/changes/2026-11-09-memory-phase2/duplicates/
-- (age, sha256, restorable with migration 016 + `copy ... from stdin (format binary)`).
-- Guarded: refuses if one quarantined copy no longer has its identical original. Idempotent.
begin;
set local lock_timeout = '5s';
do $$ begin
  if to_regclass('walter_logs.duplicates') is not null and exists (
       select 1 from walter_logs.duplicates d left join walter_logs.events f
         on f.session_id = d.session_id and f.seq = d.duplicate_of and f.event_key = d.event_key
       where f.seq is null) then
    raise exception 'a quarantined copy has no identical original left: keep walter_logs.duplicates';
  end if;
end $$;
drop table if exists walter_logs.duplicates;      -- RESTRICT: fails if anything came to depend on it
commit;
