// W.Alter engine — events strategy (lot E2, 2026-11-10; 02-ARCHITECTURE § 3 and § 4.5).
// Publishes what happens in the engine on Walter's bus (turn.ended, session.ended) and closes the turn's run in the
// Run Plane, through the Memory gateway (/v1/runs/end, /v1/bus/emit). Replaces walter_hook.py's Stop for the engine.
//
// mode shadow  — observation only: the hook keeps closing runs and emitting turn.ended. The plugin records the events
//                it would publish (private JSONL, observation=true); the gateway refuses observations anyway.
// mode native  — closes the run and emits. session.ended: on archive (the owner ended the conversation); on an agent
//                unload only with endOnDispose, until the shadow has shown when the kernel unloads agents (a service
//                restart unloads every session that is not over).
import { currentRuns, observe, post, sessionKey, settings, token } from '../shared.mjs';

export const name = 'walter-events';

export async function turnEnded(cfg, session, turn) {
  const run = currentRuns.get(session);
  if (cfg.mode === 'shadow') {
    observe(cfg, { kind: 'event', type: 'turn.ended', session, turn });
    return null;
  }
  const auth = token(cfg);
  currentRuns.delete(session);
  const ended = await post(`${cfg.gateway}/v1/runs/end`, { run_id: run?.run_id || null, session_id: session },
    { auth, timeoutMs: 5000 }).catch(() => null);
  const runId = ended?.run_id || run?.run_id || null;
  await post(`${cfg.gateway}/v1/bus/emit`, {
    type: 'turn.ended', source: cfg.runtime, subject: session, payload: { run_id: runId, turn: turn ?? null },
    dedupe_key: runId ? `turn.ended/${runId}` : null,
  }, { auth, timeoutMs: 5000 });
  return runId;
}

export async function sessionEnded(cfg, session, reason) {
  if (cfg.mode === 'shadow') {
    observe(cfg, { kind: 'event', type: 'session.ended', session, reason });
    return;
  }
  if (reason === 'disposed' && !cfg.endOnDispose) return;
  await post(`${cfg.gateway}/v1/bus/emit`, {
    type: 'session.ended', source: cfg.runtime, subject: session, payload: { reason },
  }, { auth: token(cfg), timeoutMs: 5000 });
}

export function apply(ctx, config) {
  const cfg = { ...settings(config), endOnDispose: Boolean(config?.endOnDispose) };
  const warn = (what) => (e) => ctx.logger.warn(`walter-events ${what}: ${String(e)}`);
  ctx.on('agent/turn-stopping', async ({ agent, turn }) => {
    const session = sessionKey(cfg.runtime, agent);
    if (session) await turnEnded(cfg, session, turn).catch(warn('turn.ended'));
  });
  ctx.on('agent/disposed', ({ agent }) => {
    const session = sessionKey(cfg.runtime, agent);
    if (session) sessionEnded(cfg, session, 'disposed').catch(warn('session.ended'));
  });
  ctx.on('workspace/session-stop', ({ sessionId }) => {
    if (sessionId) sessionEnded(cfg, `${cfg.runtime}/vm/${sessionId}`, 'archived').catch(warn('session.ended'));
  });
}
