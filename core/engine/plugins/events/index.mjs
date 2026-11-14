// W.Alter engine — events strategy (lot E2, 2026-11-10; 02-ARCHITECTURE § 3 and § 4.5).
// Publishes what happens in the engine on Walter's bus (turn.ended, session.ended) and closes the turn's run in the
// Run Plane, through the Memory gateway (/v1/runs/end, /v1/bus/emit). Replaces walter_hook.py's Stop for the engine.
//
// mode shadow  — observation only: the hook keeps closing runs and emitting turn.ended. The plugin records the events
//                it would publish (private JSONL, observation=true); the gateway refuses observations anyway (403
//                `observation_not_on_production_bus`: an authorisation refusal by design, recorded as such).
// mode native  — closes the run and emits. session.ended: on archive (the owner ended the conversation); on an agent
//                unload only with endOnDispose, until the shadow has shown when the kernel unloads agents (a service
//                restart unloads every session that is not over).
import { currentRuns, deliver, observe, orphanRuns, sessionKey, settings, token, trackRun, turnPlans, turnStats } from '../shared.mjs';

export const name = 'walter-events';

const OUTCOMES = { ended: 'ok', failed: 'failed', cancelled: 'cancelled' };

/** How a turn ended, for the run (Memory builds the execution experience from it, decision A4): a status, the error
 * that ended it (kind + bounded message; Memory masks secrets at its door) and what it did (numbers). */
export function outcomeOf(status, { stats = null, error = null, interrupted = false } = {}) {
  const out = { status: interrupted ? 'interrupted' : OUTCOMES[status] || 'failed', ...(stats || {}) };
  if (error) out.error = { kind: String(error.kind || 'error').slice(0, 80), message: String(error.message || '').slice(0, 500) };
  return out;
}

const errorOf = (error) => ({
  kind: String(error?.code || error?.name || (error?.status ? `http_${error.status}` : 'error')),
  message: String(error?.message || error || ''),
});

export async function turnEnded(cfg, session, turn, status = 'ended', outcome = null) {
  const run = currentRuns.get(session);
  if (cfg.mode === 'shadow') {
    observe(cfg, { kind: 'event', type: 'turn.ended', session, turn });
    return null;
  }
  const auth = token(cfg);
  currentRuns.delete(session);
  turnPlans.delete(session);
  trackRun(cfg, session, null);
  const ended = await deliver(`${cfg.gateway}/v1/runs/end`, { run_id: run?.run_id || null, session_id: session, status,
    ...(outcome ? { outcome } : {}) }, { auth, timeoutMs: 5000 });
  const runId = ended.result?.run_id || run?.run_id || null;
  const sent = await deliver(`${cfg.gateway}/v1/bus/emit`, {
    type: 'turn.ended', source: cfg.runtime, subject: session,
    payload: { run_id: runId, turn: turn ?? null, status, ...(outcome ? { outcome: outcome.status } : {}) },
    dedupe_key: runId ? `turn.ended/${runId}` : null,
  }, { auth, timeoutMs: 5000 });
  record(cfg, 'turn.ended', session, { run_end: ended, emit: sent });
  if (sent.error) throw sent.error;
  return runId;
}

// One private row per delivery that did not simply succeed (and every retry), so a refusal by design and a lost
// event are counted apart (outcome refused | invalid | transport).
function record(cfg, type, session, steps) {
  const rows = Object.entries(steps).filter(([, d]) => d.outcome !== 'delivered' || d.retried);
  if (!rows.length) return;
  observe(cfg, { kind: 'delivery', type, session, steps: Object.fromEntries(rows.map(([k, d]) => [k, {
    outcome: d.outcome, status: d.error?.status ?? null, refused: d.error?.refused ?? null, retried: Boolean(d.retried) }])) });
}

export async function sessionEnded(cfg, session, reason) {
  if (cfg.mode === 'shadow') {
    observe(cfg, { kind: 'event', type: 'session.ended', session, reason });
    return;
  }
  if (reason === 'disposed' && !cfg.endOnDispose) return;
  const sent = await deliver(`${cfg.gateway}/v1/bus/emit`, {
    type: 'session.ended', source: cfg.runtime, subject: session, payload: { reason },
    dedupe_key: `session.ended/${session}/${reason}`,
  }, { auth: token(cfg), timeoutMs: 5000 });
  record(cfg, 'session.ended', session, { emit: sent });
  if (sent.error) throw sent.error;
}

/** Runs a previous engine process left open (it was restarted during their turn): closed as interrupted, so the
 * tasks they worked on are seen as suspended and the next turn of their thread is told what happened. */
export async function closeOrphans(cfg) {
  if (cfg.mode !== 'native') return [];
  const closed = [];
  for (const { session, run_id: runId, turn } of orphanRuns(cfg)) {
    const outcome = outcomeOf('cancelled', { interrupted: true,
      error: { kind: 'engine_restart', message: 'the engine process was restarted during this turn' } });
    const ended = await deliver(`${cfg.gateway}/v1/runs/end`, { run_id: runId, session_id: session, status: 'cancelled', outcome },
      { auth: token(cfg), timeoutMs: 5000 });
    observe(cfg, { kind: 'recovery', session, run_id: runId, turn, outcome: ended.outcome });
    closed.push(runId);
  }
  return closed;
}

export function apply(ctx, config) {
  const cfg = { ...settings(config), endOnDispose: Boolean(config?.endOnDispose) };
  const warn = (what) => (e) => ctx.logger.warn(`walter-events ${what}: ${String(e)}`);
  Promise.resolve().then(() => closeOrphans(cfg)).catch(warn('recovery'));
  ctx.on('agent/turn-stopping', async ({ agent, turn }) => {
    const session = sessionKey(cfg.runtime, agent);
    if (!session) return;
    failed.delete(session);
    await turnEnded(cfg, session, turn, 'ended', outcomeOf('ended', { stats: turnStats(agent.session) })).catch(warn('turn.ended'));
  });
  // A turn that closes without its stop boundary was interrupted (owner's stop, cancel, budget) or failed: its run
  // is closed as such when the agent goes idle, instead of waiting for the next turn to cancel it.
  const failed = new Map();                                  // session → the error that ended its turn
  ctx.on('agent/error', ({ agent, error }) => { const s = sessionKey(cfg.runtime, agent); if (s) failed.set(s, errorOf(error)); });
  ctx.on('agent/status', ({ agent, status }) => {
    const session = sessionKey(cfg.runtime, agent);
    if (status !== 'idle' || !session) return;
    const error = failed.get(session) || null;
    failed.delete(session);
    if (cfg.mode !== 'native' || !currentRuns.has(session)) return;
    const status_ = error ? 'failed' : 'cancelled';
    const stopped = turnPlans.get(session)?.stopped;         // the budget strategy refused a further step
    const outcome = outcomeOf(status_, { stats: turnStats(agent.session),
      error: error || (stopped ? { kind: stopped, message: 'the turn reached its ceiling and was stopped' } : null) });
    turnEnded(cfg, session, currentRuns.get(session)?.turn, status_, outcome).catch(warn('turn.ended'));
  });
  ctx.on('agent/disposed', ({ agent }) => {
    const session = sessionKey(cfg.runtime, agent);
    if (session) sessionEnded(cfg, session, 'disposed').catch(warn('session.ended'));
  });
  ctx.on('workspace/session-stop', ({ sessionId }) => {
    if (sessionId) sessionEnded(cfg, `${cfg.runtime}/vm/${sessionId}`, 'archived').catch(warn('session.ended'));
  });
}
