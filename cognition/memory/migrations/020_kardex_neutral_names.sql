-- Walter Memory — kardex identifiers no longer name the first instance's owner (2026-10-29, Walter Clean).
-- The retired kardex service named columns after the owner; the software must not. Renamed only where the old name
-- exists (a database built from 004b already has the neutral names). Rows keep their values: historical
-- corrections.created_by values are data of their instance and stay as they are; only the default changes.
-- The only reader of the old names was the legacy Hermes cron job « Kardex Semantic Extract », paused the same day.
do $$
declare r record;
begin
  for r in select * from (values
      ('claims', 'monsieur_knows', 'owner_knows'),
      ('claims', 'contact_told_monsieur', 'contact_told_owner'),
      ('claims', 'contact_knows_monsieur_knows', 'contact_knows_owner_knows'),
      ('social_graph', 'relationship_to_lucas', 'relationship_to_owner')) as t(tbl, old, new)
  loop
    if exists (select 1 from information_schema.columns
               where table_schema = 'kardex' and table_name = r.tbl and column_name = r.old) then
      execute format('alter table kardex.%I rename column %I to %I', r.tbl, r.old, r.new);
    end if;
  end loop;
end $$;
alter table kardex.corrections alter column created_by set default 'owner';
comment on table kardex.corrections is 'Owner corrections that become extraction rules. Example: a nickname is not an alias.';
