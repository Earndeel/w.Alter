// W.Alter engine — budget strategy (lot E3, 2026-11-10; 02-ARCHITECTURE § 5.4).
// Fixed ceilings of the composition until Context's ContextPlan carries an effort (03-MIGRATION § E3, prerequisite):
//   maxSteps    — model steps in one turn. At the ceiling the agent is told once to conclude with what it has, without
//                 a new tool call; `graceSteps` later, a further step is refused (the turn closes).
//   maxTurnMs   — wall time of one turn, same two stages.
// Model spend stays capped where every model call passes: walter-llm (channel budgets). Every stop is journaled.
import { appendFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';

export const name = 'walter-budget';
const hostRequire = createRequire('/opt/dsh/package.json');

const NOTICE = 'Budget de ce tour atteint (Walter) : conclus maintenant avec ce que tu as déjà, sans nouvel appel '
  + "d'outil ; dis clairement ce qui reste à faire.";

function record(cfg, row) {
  if (!cfg.stateDir) return;
  try {
    mkdirSync(cfg.stateDir, { recursive: true, mode: 0o700 });
    appendFileSync(join(cfg.stateDir, `budget-${new Date().toISOString().slice(0, 10)}.jsonl`),
      `${JSON.stringify({ at: new Date().toISOString(), ...row })}\n`, { mode: 0o600 });
  } catch { /* never on the turn's path */ }
}

export function verdict(cfg, { step, startedAt, now = Date.now() }) {
  const overSteps = step >= cfg.maxSteps, overTime = now - startedAt >= cfg.maxTurnMs;
  if (!overSteps && !overTime) return 'go';
  const graceOver = step >= cfg.maxSteps + cfg.graceSteps || now - startedAt >= cfg.maxTurnMs + cfg.graceMs;
  return graceOver ? 'stop' : 'conclude';
}

export function apply(ctx, config = {}) {
  const cfg = { maxSteps: config.maxSteps ?? 80, graceSteps: config.graceSteps ?? 3, maxTurnMs: config.maxTurnMs ?? 45 * 60_000,
    graceMs: config.graceMs ?? 5 * 60_000, stateDir: config.stateDir };
  let userMessage = null;
  try { ({ createUserMessage: userMessage } = hostRequire('@deepseek-ai/dsh-llm')); } catch { /* notice degrades to a refusal */ }
  const turns = new WeakMap();                                 // agent → { turn, startedAt, told }
  ctx.on('agent/pre-step', async ({ agent, turn, step }, next) => {
    let t = turns.get(agent);
    if (!t || t.turn !== turn) { t = { turn, startedAt: Date.now(), told: false }; turns.set(agent, t); }
    const v = verdict(cfg, { step, startedAt: t.startedAt });
    if (v === 'go') return next();
    const session = agent?.session?.header?.id || null;
    if (v === 'stop' || !userMessage) {
      record(cfg, { action: 'stop', session, turn, step, ms: Date.now() - t.startedAt });
      return { kind: 'reject' };
    }
    const downstream = await next();
    if (t.told || downstream.kind !== 'enter') return downstream;
    t.told = true;
    record(cfg, { action: 'conclude', session, turn, step, ms: Date.now() - t.startedAt });
    return { ...downstream, messages: [...downstream.messages, userMessage({ content: [{ type: 'text', text: NOTICE }], source: { kind: 'walter-budget' } })] };
  }, { prepend: true });
}
