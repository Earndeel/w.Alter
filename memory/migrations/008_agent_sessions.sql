-- P8.2: sessions of other runtimes (Claude Code, Codex) in the canonical journal, same rules as Hermes.
begin;
insert into core.sources (source, kind, description, privacy_default) values
  ('claude_code', 'agent', 'Claude Code sessions on the VM (transcripts → core.events): Monsieur''s prompts, visible answers, tool metadata', 'cloud_allowed'),
  ('codex',       'agent', 'Codex sessions (rollout JSONL → core.events): prompts (Monsieur or delegating agent), answers, tool metadata', 'cloud_allowed')
on conflict (source) do nothing;
insert into ingestion.connectors (connector, source, mode, description, freshness_target) values
  ('agent_sessions', 'claude_code', 'push', 'Claude Code + Codex transcripts, triggered by their hooks (walter_hook.py); no timer', null)
on conflict (connector) do nothing;
commit;
