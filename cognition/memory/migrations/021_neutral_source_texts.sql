-- Walter Memory — source descriptions shipped with the software name no person (2026-10-29, Walter Clean). The
-- descriptions inserted by 008/009 were written for the first instance's owner; same meaning, neutral wording.
update core.sources set description = 'Beeper Desktop API on the owner''s computer: WhatsApp, Instagram, Messenger, Telegram, LINE, Signal…'
 where source = 'beeper';
update core.sources set description = 'Claude Code sessions (transcripts → core.events): the owner''s prompts, visible answers, tool metadata'
 where source = 'claude_code';
update core.sources set description = 'Codex sessions (rollout JSONL → core.events): prompts (the owner or a delegating agent), answers, tool metadata'
 where source = 'codex';
