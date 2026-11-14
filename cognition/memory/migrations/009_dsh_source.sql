-- P8: DeepSeek Harness sessions (test runtime next to Hermes) in the canonical journal.
begin;
insert into core.sources (source, kind, description, privacy_default) values
  ('dsh', 'agent', 'DeepSeek Harness sessions on the VM (session.v4.jsonl.zstd → core.events): prompts, visible answers, tool metadata', 'cloud_allowed')
on conflict (source) do nothing;
commit;
