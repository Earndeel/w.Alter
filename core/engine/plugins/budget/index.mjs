// W.Alter engine — budget strategy (lot E3, 2026-11-10; 02-ARCHITECTURE § 5.4; plan applied: decision A7, 2026-11-11).
// The effort of a turn follows what Context understood of the request (ContextPlan `decision.effort`, published by the
// intake: the context level raised by the difficulty asked and by work to carry out; the level itself for a rule-made plan):
//   checkpoint  — steps after which the agent is told ONCE where it stands: conclude if the result is reachable,
//                 otherwise say what is missing and go on with that only (it stays free to go deeper).
//   maxSteps    — model steps in one turn. At the ceiling the agent is told once to conclude with what it has, without
//                 a new tool call; `graceSteps` later, a further step is refused (the turn closes).
//   maxTurnMs   — wall time of one turn, same two stages.
// An effort level sets these three for an owner turn (`levels`, composition values [dsh.budget.levels]); a turn without a
// plan, with a degraded plan, or a delegated mission keeps the composition's general ceilings: an unread request is
// never cut short. Model spend stays capped where every model call passes: walter-llm. Every stage is journaled.
import { appendFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { turnPlans } from '../shared.mjs';

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

const CHECKPOINT = (step, level) => `Point d'étape (Walter) : ce tour a déjà pris ${step} étapes pour une demande dont l'effort a été évalué ${level}. `
  + "Si le résultat demandé est atteignable avec ce que tu as, conclus maintenant. Sinon dis en une phrase ce qui manque "
  + "et continue uniquement là-dessus, sans retenter à l'identique une opération qui a déjà échoué.";

/** The ceilings of a turn: those of its plan's EFFORT when an owner request was understood, the general ones
 * otherwise. The effort is stated by Context (`decision.effort`): the context level raised by the difficulty asked
 * and by work to carry out — the level alone says what the model must see, not how much it must do (a self-contained
 * request with three delegated evaluations was cut at L0 ceilings, 2026-11-12). A plan without it (rule-made): its level. */
export function ceilings(cfg, plan = null) {
  const name = plan && !plan.degraded && plan.channel !== 'machine' ? (plan.effort || plan.level) : null;
  const level = name ? cfg.levels?.[name] : null;
  if (!level) return { level: null, checkpoint: 0, maxSteps: cfg.maxSteps, maxTurnMs: cfg.maxTurnMs };
  return { level: name, checkpoint: Math.min(level.checkpoint ?? 0, cfg.maxSteps),
    maxSteps: Math.min(level.maxSteps ?? cfg.maxSteps, cfg.maxSteps),
    maxTurnMs: Math.min(level.maxTurnMs ?? cfg.maxTurnMs, cfg.maxTurnMs) };
}

export function verdict(cfg, { step, startedAt, now = Date.now(), plan = null }) {
  const c = ceilings(cfg, plan);
  const overSteps = step >= c.maxSteps, overTime = now - startedAt >= c.maxTurnMs;
  if (!overSteps && !overTime) return c.checkpoint && step >= c.checkpoint ? 'checkpoint' : 'go';
  const graceOver = step >= c.maxSteps + cfg.graceSteps || now - startedAt >= c.maxTurnMs + cfg.graceMs;
  return graceOver ? 'stop' : 'conclude';
}

export function apply(ctx, config = {}) {
  const cfg = { maxSteps: config.maxSteps ?? 80, graceSteps: config.graceSteps ?? 3, maxTurnMs: config.maxTurnMs ?? 45 * 60_000,
    graceMs: config.graceMs ?? 5 * 60_000, stateDir: config.stateDir, runtime: config.runtime || 'dsh', levels: config.levels || {} };
  let userMessage = null;
  try { ({ createUserMessage: userMessage } = hostRequire('@deepseek-ai/dsh-llm')); } catch { /* notice degrades to a refusal */ }
  const turns = new WeakMap();                                 // agent → { turn, startedAt, told, checked }
  ctx.on('agent/pre-step', async ({ agent, turn, step }, next) => {
    let t = turns.get(agent);
    if (!t || t.turn !== turn) { t = { turn, startedAt: Date.now(), told: false, checked: false }; turns.set(agent, t); }
    const session = agent?.session?.header?.id || null;
    const key = session ? `${cfg.runtime}/vm/${session}` : null;
    const known = key ? turnPlans.get(key) : null;
    const plan = known && known.turn === turn ? known : null;  // the plan of THIS turn (the intake publishes it at its first step)
    const v = verdict(cfg, { step, startedAt: t.startedAt, plan });
    if (v === 'go' || (v === 'checkpoint' && (t.checked || !userMessage))) return next();
    const row = { session, turn, step, ms: Date.now() - t.startedAt, level: ceilings(cfg, plan).level };
    if (v === 'stop' || !userMessage) {
      record(cfg, { action: 'stop', ...row });
      if (plan) plan.stopped = 'budget';                       // said on the run's outcome (events strategy)
      return { kind: 'reject' };
    }
    const downstream = await next();
    if (downstream.kind !== 'enter' || (v === 'conclude' && t.told)) return downstream;
    if (v === 'checkpoint') t.checked = true; else t.told = true;
    record(cfg, { action: v, ...row });
    const text = v === 'checkpoint' ? CHECKPOINT(step, row.level) : NOTICE;
    return { ...downstream, messages: [...downstream.messages, userMessage({ content: [{ type: 'text', text }], source: { kind: 'walter-budget' } })] };
  }, { prepend: true });
}
