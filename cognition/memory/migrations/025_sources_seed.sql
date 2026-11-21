-- Sources the first instance registered by hand (found 2026-11-02 while rebuilding a blank test database): a new
-- database now gets them from the migrations. Idempotent: existing rows are left as they are.
insert into core.sources (source, kind, privacy_default, description) values
    ('walter', 'agent', 'cloud_allowed', 'Walter Memory internal processors (indexer, router, consolidation)'),
    ('overland', 'location', 'local_only', 'Overland iPhone GPS'),
    ('documents', 'files', 'cloud_allowed', 'Curated records the instance declares (documents.toml)')
on conflict (source) do nothing;
