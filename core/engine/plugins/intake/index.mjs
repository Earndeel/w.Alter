// W.Alter engine — intake strategy (lot E2, 2026-11-10; 02-ARCHITECTURE § 3 and § 4.2).
// Accueil d'un tour : garder le texte du propriétaire, ouvrir le run (passerelle Memory, seule source des runs),
// obtenir LE ContextPlan (preflight walter-context :8897), injecter le contexte qu'il demande et les skills.
// Replaces walter_hook.py's UserPromptSubmit for the engine; walter_hook.py stays for Claude Code and Codex.
//
// mode shadow  — observation only: the hook keeps doing the work. For each owner message the plugin records what
//                it would do (owner text hash, idempotency key, the plan it obtains, its latency) in a private JSONL.
//                It never opens a run, never writes on the bus, never injects; the plan request carries no run_id,
//                so the preflight writes nothing. A message that holds a secret is never sent to the preflight.
// mode native  — the engine's own intake: run, plan + context pack, skills, injected as one tagged user message.
import { createRequire } from 'node:module';
import { parentIdOf } from '../lineage.mjs';
import { currentRuns, deliver, lastExchange, machinePrompt, observe, outcome, ownerText, post, recordRun, sessionKey, settings, sha16, token, trackRun, turnPlans } from '../shared.mjs';

export const name = 'walter-intake';

let hostRequire = createRequire(import.meta.url);
try { hostRequire.resolve('@deepseek-ai/dsh-llm'); }
catch { hostRequire = createRequire(process.env.WALTER_DSH_PACKAGE || '/opt/dsh/package.json'); }

const SOURCE = { kind: 'walter-intake' };
const WINDOW_ENTRY = Symbol.for('walter.context.window');   // walter-context's in-process window entry (its DSH port)
// walter_hook.HEADER, so the legacy block reads the same whichever adapter delivers it
const HEADER = "Mémoire W.Alter (injectée automatiquement pour ce message ; souvenirs datés : réponds à partir d'eux en citant "
  + "la date, le plus récent l'emporte ; si l'état réel compte et que tu as les outils, vérifie-le ; approfondir "
  + 'avec memory_search / person_lookup) :';

// Said to the model when the preflight itself did not answer (its own degraded plan says it in the pack): the
// context below was not chosen for this message. Never a silent fallback (decision A2, 2026-11-11).
const DEGRADED = "Contexte dégradé : la préparation du contexte n'a pas répondu, l'intention de ce message n'a pas pu être "
  + "évaluée. Ce qui suit est une sélection mémoire par défaut : vérifie avec les outils mémoire si la demande en dépend.";

/** The preflight request walter_hook.context_pack sends for the same message (DSH has no transcript path).
 * `previous` is the session's last completed exchange ({message, answer, age_s, thread_id}), read from its journal. */
export function planRequest(cfg, session, message, runId = null, at = Date.now(), channel = null, previous = null) {
  return {
    turn_id: `${session}:${at}`, message: message.slice(0, 6000), previous: previous || null, runtime: cfg.runtime,
    session_id: session, privacy_class: 'cloud_allowed', run_id: runId, exclude_blocks: ['capabilities'],
    answer_within_ms: cfg.preflightTimeoutMs,          // how long the engine waits: the preflight answers inside it
    ...(channel === 'machine' ? { channel } : {}),   // a sub-agent's mission: the preflight asks one tier lower
  };
}

/** One run per turn: a replayed step (same session, turn, step and text) finds the same run. */
export const dedupeKey = (session, turn, step, message) => `${session}:${turn ?? '-'}:${step ?? '-'}:${sha16(message)}`;

const summary = (plan) => plan && {
  act: plan.act, level: plan.level, task: plan.model_profile?.task, model_level: plan.model_profile?.level,
  fast_path: Boolean(plan.fast_path), thread_new: Boolean(plan.thread?.new),
};

export async function shadowTurn(cfg, { session, turn, step, message }, now = () => performance.now()) {
  const t0 = now();
  const row = { kind: 'intake', session, turn, step, message_sha: sha16(message.slice(0, 6000)), chars: message.length,
    channel: machinePrompt(message) ? 'machine' : 'owner', dedupe_key: dedupeKey(session, turn, step, message) };
  try {
    const auth = token(cfg);
    const privacy = await post(`${cfg.gateway}/v1/privacy/classify`, { text: message }, { auth, timeoutMs: 3000 });
    row.privacy_class = privacy.privacy_class;
    if (privacy.privacy_class !== 'cloud_allowed') {
      row.plan = null; row.skipped = 'local_only';           // the hook falls back to the legacy block: no plan either
    } else {
      const t1 = now();
      const plan = await post(`${cfg.preflight}/preflight`, planRequest(cfg, session, message), { timeoutMs: 9000 });
      row.plan = summary(plan); row.plan_ms = Math.round(now() - t1);
    }
  } catch (error) {
    row.error = String(error?.message || error).slice(0, 160);
    row.outcome = outcome(error);                 // refused (by design) | invalid | transport (a defect)
  }
  row.native_ms = Math.round(now() - t0);
  observe(cfg, row);
  return row;
}

/** Native intake: run, then context (pack or legacy block) and skills in parallel; every source fails open. */
export async function nativeTurn(cfg, { session, turn, step, message, parent = null, previous: lastTurn = null, requestId = null }) {
  const t0 = performance.now();
  const auth = token(cfg);
  // a bench or Lab run (walter-scenario sets WALTER_RUN_CHANNEL=test): walter-llm caps its paid spend, as with the hook
  // a session opened through the Engine API says who speaks (machine, test) and, for a delegation, its parent run
  const meta = globalThis[Symbol.for('walter.engine.sessionMeta')]?.get?.(session.replace(/^[^/]+\/vm\//, '')) || {};
  // an in-process sub-agent (lot E5): its "user" message is its parent's mission, never the owner's words; its run is
  // filed under the parent's current run (correlation, costs, cancellation follow the tree)
  const parentRun = parent ? currentRuns.get(parent)?.run_id || null : null;
  const channel = process.env.WALTER_RUN_CHANNEL || (parent ? 'machine' : null)
    || (meta.channel && meta.channel !== 'owner' ? meta.channel : null) || (machinePrompt(message) ? 'machine' : 'owner');
  const parentRunId = meta.parent_run_id || parentRun;
  // skills need no run: asked at once, beside the run and then the context (as the hook's thread pool does)
  const skills = post(`${cfg.skills}/v1/expose`, {
    kind: 'message', message, context: '', session_id: session, runtime: cfg.runtime, first_turn: false,
  }, { timeoutMs: 4000 }).then((r) => [r?.text || '', Math.round(performance.now() - t0)]).catch(() => ['', null]);
  let run = null;
  let runOutcome = 'delivered';
  let source = 'none';
  const key = dedupeKey(session, turn, step, message);
  const previous = currentRuns.get(session);
  try {
    run = await post(`${cfg.gateway}/v1/runs/start`, {
      // who asked and through which door: the run is found again from the door's own identifiers (traceability)
      origin: { channel, runtime: cfg.runtime, session_id: session,
        ...(meta.interface ? { interface: meta.interface } : {}), ...(meta.engine_session ? { engine_session: meta.engine_session } : {}),
        ...(requestId ? { request_id: String(requestId).slice(0, 200) } : {}) }, goal: message, dedupe_key: key,
      ...(parentRunId ? { parent_run_id: parentRunId } : {}),
      // the previous turn never got its end: interrupted. A replay of this same turn is not a new turn.
      cancel_run_id: previous && previous.key !== key ? previous.run_id : null,
      routing: { applied: false, configured: true, via: 'walter-llm poste (DSH provider walter)',
        // a model the owner named for this conversation (Engine API delegation): the plan walter-llm reads per call
        ...(meta.model?.id ? { requested: { model: meta.model.id, ...(meta.model.provider ? { provider: meta.model.provider } : {}) } } : {}) },
    }, { auth, timeoutMs: 5000 });
    currentRuns.set(session, { run_id: run.run_id, turn, key });
    trackRun(cfg, session, { run_id: run.run_id, turn });
    run.ms = Math.round(performance.now() - t0);
    recordRun(cfg, run.run_id, session);
  } catch (e) { run = null; runOutcome = outcome(e); }
  const local = run?.privacy_class === 'local_only';
  const legacy = async () => {
    if (channel === 'machine' || message.split(/\s+/).length < 4 || message.startsWith('/')) return '';
    const res = await post(`${cfg.gateway}/v1/context`, {
      query: message.slice(0, 4000), budget: { profile: 0, people: 300, knowledge: 600, evidence: 300 },
      include_profile: false, caller: `${cfg.runtime}-hook`, mode: 'on', session_id: session, cloud_safe: true,
    }, { auth, timeoutMs: 8000 });
    const text = (res?.text || '').trim();
    return text ? `${HEADER}\n${text}` : '';
  };
  const t1 = performance.now();
  const timed = (p) => p.then((v) => [v, Math.round(performance.now() - t1)]);
  let plan = null;
  const memory = (async () => {
    if (cfg.inject === 'pack' && !local) {
      try {
        const out = await post(`${cfg.preflight}/preflight?inject=1`,
          planRequest(cfg, session, message, run?.run_id || null, Date.now(), channel, lastTurn), { timeoutMs: cfg.preflightTimeoutMs });
        if (out?.error || !out?.plan) throw new Error(out?.error || 'no plan');
        const degraded = Boolean(out.degraded || out.plan.decision?.degraded);
        plan = { thread: out.plan.thread?.id || null, act: out.plan.act || null, level: out.plan.level || null,
          effort: out.plan.decision?.effort || null, degraded, channel };
        source = degraded ? 'pack_degraded' : 'pack';   // the preflight says so itself in the pack, on the run and on the bus
        return out.text || '';                   // empty = the plan's own decision (L0: nothing beyond the message)
      } catch (e) {
        // The preflight did not answer at all: the turn goes on with Memory's default block, and it is SAID: to the
        // model (first line), in the measurements, on the bus (the context guardian counts it).
        source = 'legacy_degraded';
        plan = { thread: null, act: null, level: null, degraded: true, channel };
        deliver(`${cfg.gateway}/v1/bus/emit`, { type: 'context.degraded', source: cfg.runtime, subject: session,
          payload: { run_id: run?.run_id || null, stage: 'preflight_unreachable', reason: outcome(e) },
          dedupe_key: run?.run_id ? `context.degraded/${run.run_id}` : null }, { auth, timeoutMs: 3000 }).catch(() => {});
        const text = await legacy().catch(() => '');
        return text ? `${DEGRADED}\n\n${text}` : (channel === 'machine' ? '' : DEGRADED);
      }
    }
    source = 'legacy';                           // a local_only message never leaves for the preflight: by design
    return legacy();
  })().catch(() => '');
  const [[mem, memoryMs], [sk, skillsMs]] = await Promise.all([timed(memory), skills]);
  const parts = [mem, sk].filter(Boolean);
  // a measurement, not an observation: numbers only (latency against 04-BASELINE, what was injected)
  try { observe(cfg, { kind: 'intake', session, turn, step, message_sha: sha16(message.slice(0, 6000)), run_id: run?.run_id || null,
    privacy_class: run?.privacy_class || null, run_outcome: runOutcome, context_source: source, level: plan?.level || null, effort: plan?.effort || null,
    previous_sent: Boolean(lastTurn), memory_chars: mem.length, skills_chars: sk.length,
    run_ms: run?.ms ?? null, memory_ms: memoryMs, skills_ms: skillsMs, native_ms: Math.round(performance.now() - t0) }); } catch { /* never on the turn's path */ }
  return { run_id: run?.run_id || null, plan, text: parts.length ? `<walter-context>\n${parts.join('\n\n')}\n</walter-context>` : '' };
}

/** The window of this owner turn: walter-context decides what the completed turns become (its DSH port, `window`),
 * the kernel's own transaction applies it, before the new message enters the session. Fails open, measured. */
export async function windowTurn(ctx, cfg, agent, plan, signal, row = {}) {
  // walter-context publishes its window entry in-process (its DSH port; the host isolates the compaction service
  // in its own plugin group, so it cannot be injected from here). Absent = a host without walter-context: said once.
  const entry = globalThis[WINDOW_ENTRY];
  if (typeof entry !== 'function') {
    if (!windowTurn.warned) { windowTurn.warned = true; ctx.logger?.warn?.('walter-intake: no walter-context window entry, the window is not managed'); }
    try { observe(cfg, { kind: 'window', ...row, applied: false, reason: 'no_entry' }); } catch { /* never on the turn's path */ }
    return null;
  }
  const t0 = performance.now();
  let report;
  try { report = await entry(agent, { plan: plan?.thread ? { thread: plan.thread } : null }, signal); }
  catch (e) { report = { applied: false, reason: 'error', error: String(e?.message || e).slice(0, 160) }; ctx.logger?.warn?.(`walter-intake window: ${report.error}`); }
  try { observe(cfg, { kind: 'window', ...row, applied: Boolean(report?.applied), reason: report?.reason || null, warm: report?.warm ?? null,
    turns: report?.turns || null, tokens: report?.tokens || null, measured_tokens: report?.measured_tokens ?? null,
    ...(report?.error ? { error: report.error } : {}), window_ms: Math.round(performance.now() - t0) }); } catch { /* never on the turn's path */ }
  return report;
}

export function apply(ctx, config) {
  const cfg = settings(config);
  const pending = new Set();
  ctx.on('agent/pre-step', async ({ agent, messages, turn, step, signal }, next) => {
    const session = sessionKey(cfg.runtime, agent);
    const message = ownerText(messages);
    if (!session || !message) return next();
    const parentId = parentIdOf(agent);         // an in-process sub-agent: its parent's session (E5)
    const requestId = (messages || []).find((m) => m?.source?.kind === 'user' && m.source.rpcId)?.source.rpcId || null;
    const input = { session, turn, step, message, parent: parentId ? `${cfg.runtime}/vm/${parentId}` : null,
      previous: lastExchange(agent.session), requestId };
    if (cfg.mode === 'shadow') {                 // never on the step's path: the observation runs beside it
      const p = shadowTurn(cfg, input).catch((e) => ctx.logger.warn(`walter-intake shadow: ${String(e)}`))
        .finally(() => pending.delete(p));
      pending.add(p);
      return next();
    }
    const { text, plan } = await nativeTurn(cfg, input)
      .catch((e) => { ctx.logger.warn(`walter-intake: ${String(e)}`); return { text: '', plan: null }; });
    if (plan) turnPlans.set(session, { ...plan, turn }); else turnPlans.delete(session);
    // Context holds the window: decided now, with what was understood of the message, before it enters the session.
    await windowTurn(ctx, cfg, agent, plan, signal, { session, turn, step });
    const downstream = await next();
    if (!text || downstream.kind !== 'enter') return downstream;
    const { createUserMessage } = hostRequire('@deepseek-ai/dsh-llm');
    // the pack carries the thread of its turn: the window policy reads it back from the journal on later turns
    const source = { ...SOURCE, ...(plan?.thread ? { thread: plan.thread } : {}), ...(plan?.act ? { act: plan.act } : {}),
      ...(plan?.level ? { level: plan.level } : {}), ...(plan?.degraded ? { degraded: true } : {}) };
    return { ...downstream, messages: [...downstream.messages, createUserMessage({ content: [{ type: 'text', text }], source })] };
  }, { prepend: true });
  ctx.on('dispose', () => Promise.allSettled([...pending]));
}
