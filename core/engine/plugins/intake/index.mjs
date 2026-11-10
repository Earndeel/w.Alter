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
import { currentRuns, machinePrompt, observe, outcome, ownerText, post, recordRun, sessionKey, settings, sha16, token } from '../shared.mjs';

export const name = 'walter-intake';

let hostRequire = createRequire(import.meta.url);
try { hostRequire.resolve('@deepseek-ai/dsh-llm'); }
catch { hostRequire = createRequire(process.env.WALTER_DSH_PACKAGE || '/opt/dsh/package.json'); }

const SOURCE = { kind: 'walter-intake' };
// walter_hook.HEADER, so the legacy block reads the same whichever adapter delivers it
const HEADER = "Mémoire W.Alter (injectée automatiquement pour ce message ; souvenirs datés : réponds à partir d'eux en citant "
  + "la date, le plus récent l'emporte ; si l'état réel compte et que tu as les outils, vérifie-le ; approfondir "
  + 'avec memory_search / person_lookup) :';

/** The preflight request walter_hook.context_pack sends for the same message (DSH has no transcript path). */
export function planRequest(cfg, session, message, runId = null, at = Date.now()) {
  return {
    turn_id: `${session}:${at}`, message: message.slice(0, 6000), previous: null, runtime: cfg.runtime,
    session_id: session, privacy_class: 'cloud_allowed', run_id: runId, exclude_blocks: ['capabilities'],
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
export async function nativeTurn(cfg, { session, turn, step, message }) {
  const t0 = performance.now();
  const auth = token(cfg);
  // a bench or Lab run (walter-scenario sets WALTER_RUN_CHANNEL=test): walter-llm caps its paid spend, as with the hook
  const channel = process.env.WALTER_RUN_CHANNEL || (machinePrompt(message) ? 'machine' : 'owner');
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
      origin: { channel, runtime: cfg.runtime, session_id: session }, goal: message, dedupe_key: key,
      // the previous turn never got its end: interrupted. A replay of this same turn is not a new turn.
      cancel_run_id: previous && previous.key !== key ? previous.run_id : null,
      routing: { applied: false, configured: true, via: 'walter-llm poste (DSH provider walter)' },
    }, { auth, timeoutMs: 5000 });
    currentRuns.set(session, { run_id: run.run_id, turn, key });
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
  const memory = (async () => {
    if (cfg.inject === 'pack' && !local) {
      try {
        const out = await post(`${cfg.preflight}/preflight?inject=1`, planRequest(cfg, session, message, run?.run_id || null),
          { timeoutMs: 7000 });
        if (out?.error || !out?.plan) throw new Error(out?.error || 'no plan');
        source = 'pack';
        return out.text || '';                   // empty = the plan's own decision (L0: nothing beyond the message)
      } catch { /* never lose the context: legacy block instead */ }
    }
    source = 'legacy';
    return legacy();
  })().catch(() => '');
  const [[mem, memoryMs], [sk, skillsMs]] = await Promise.all([timed(memory), skills]);
  const parts = [mem, sk].filter(Boolean);
  // a measurement, not an observation: numbers only (latency against 04-BASELINE, what was injected)
  try { observe(cfg, { kind: 'intake', session, turn, step, message_sha: sha16(message.slice(0, 6000)), run_id: run?.run_id || null,
    privacy_class: run?.privacy_class || null, run_outcome: runOutcome, context_source: source, memory_chars: mem.length, skills_chars: sk.length,
    run_ms: run?.ms ?? null, memory_ms: memoryMs, skills_ms: skillsMs, native_ms: Math.round(performance.now() - t0) }); } catch { /* never on the turn's path */ }
  return { run_id: run?.run_id || null, text: parts.length ? `<walter-context>\n${parts.join('\n\n')}\n</walter-context>` : '' };
}

export function apply(ctx, config) {
  const cfg = settings(config);
  const pending = new Set();
  ctx.on('agent/pre-step', async ({ agent, messages, turn, step }, next) => {
    const session = sessionKey(cfg.runtime, agent);
    const message = ownerText(messages);
    if (!session || !message) return next();
    const input = { session, turn, step, message };
    if (cfg.mode === 'shadow') {                 // never on the step's path: the observation runs beside it
      const p = shadowTurn(cfg, input).catch((e) => ctx.logger.warn(`walter-intake shadow: ${String(e)}`))
        .finally(() => pending.delete(p));
      pending.add(p);
      return next();
    }
    const work = nativeTurn(cfg, input).catch((e) => { ctx.logger.warn(`walter-intake: ${String(e)}`); return { text: '' }; });
    const downstream = await next();
    const { text } = await work;
    if (!text || downstream.kind !== 'enter') return downstream;
    const { createUserMessage } = hostRequire('@deepseek-ai/dsh-llm');
    return { ...downstream, messages: [...downstream.messages, createUserMessage({ content: [{ type: 'text', text }], source: SOURCE })] };
  }, { prepend: true });
  ctx.on('dispose', () => Promise.allSettled([...pending]));
}
