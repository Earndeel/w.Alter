// W.Alter — DSH adapter for walter_hook.py (UserPromptSubmit), mounted by walter-core composition.
// DSH's Claude Code hook bridge glues every pending message of a step into one `prompt` string, runtime notices
// included (approval policy, jobs, goals, subagent results…). This listener runs before the bridge and records the
// part the owner actually wrote (source.kind === "user", the test DSH itself uses), so Walter memory, runs and
// skills never take a runtime notice for an owner request. It only records; it changes nothing in the step.
import { mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const name = 'walter-owner-turn';
export const DIR = process.env.WALTER_DSH_OWNER_DIR || '/run/walter/dsh-owner';

const text = (message) => (message.content || []).filter((b) => b.type === 'text').map((b) => b.text).join('');

export function record(sessionId, messages, dir = DIR) {
  if (!sessionId || !messages?.length) return null;
  const entry = {
    at: Date.now(),
    owner: messages.filter((m) => m.source?.kind === 'user').map(text),
    kinds: [...new Set(messages.map((m) => m.source?.kind || 'unknown'))],
  };
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = join(dir, sessionId.replace(/[^A-Za-z0-9._-]/g, '_') + '.json');
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(entry), { mode: 0o600 });
  renameSync(tmp, file);
  return entry;
}

export function apply(ctx) {
  ctx.on('agent/pre-step', ({ agent, messages }, next) => {
    try { record(agent?.session?.header?.id, messages); }
    catch (error) { ctx.logger.warn(`walter-owner-turn: ${String(error)}`); }
    return next();
  }, { prepend: true });
}
