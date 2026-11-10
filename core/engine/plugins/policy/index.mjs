// W.Alter engine — policy strategy (lot E3, 2026-11-10; 02-ARCHITECTURE § 4.4, core/security).
// One decision before every tool call of every agent of the engine — the owner's agent, its children (subagents,
// teammates) and the nested calls of run_code — from Walter's one policy (core/security/policy.json, the same rules
// the MCP server applies to every other client). Order, the most restrictive wins:
//   never (secret files and secret-revealing commands, delegation depth) → a monotonic guard: no later listener can
//     turn it back into permission;
//   disclosure (outgoing messages) → Memory's check through the gateway: block ⇒ deny, ask ⇒ ask, failure ⇒ ask;
//   the class of the tool under the preset of the session's door (web, telegram, api, command), a child never above
//     its parent → allow | ask | deny;
//   then the kernel's own listeners (sandbox, approval). `ask` goes to the kernel's approval seam: the door's answerer
//   (web dialog, Telegram buttons) or, without one, a refusal (fail closed).
import { rootIdOf } from '../lineage.mjs';
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { decide, load, strictest } from '../../../security/policy.mjs';
import { post, token } from '../shared.mjs';

export const name = 'walter-policy';
export const inject = ['tools'];

// Strict stand-in when the policy cannot be read: every call asks (fails closed without an answerer).
const FALLBACK = { decide: (req) => ({ decision: 'ask', rule: 'fallback', reason: 'politique Walter illisible : accord requis', class: 'unknown', tool: req.tool }) };

export function depthOf(agent) {
  let d = 0;
  for (let a = agent?.parentAgent; a && d < 64; a = a.parentAgent) d += 1;
  return Math.max(d, Number(agent?.session?.header?.delegationDepth ?? agent?.session?.header?.meta?.delegationDepth ?? 0) || 0);
}

// The door a session came through: set by the interface that opened it (Engine API, Telegram), else the profile's.
export function interfaceOf(agent, fallback) {
  let a = agent;
  while (a?.parentAgent) a = a.parentAgent;
  const id = rootIdOf(agent);                                   // a child is judged under its root's door (E5)
  const doors = globalThis[Symbol.for('walter.engine.doors')];  // published by the Engine API (core/interfaces/api)
  return (id && doors instanceof Map && doors.get(id)) || a?.session?.header?.walter?.interface || fallback;
}

function record(cfg, row) {
  if (!cfg.stateDir) return;
  try {
    mkdirSync(cfg.stateDir, { recursive: true, mode: 0o700 });
    appendFileSync(join(cfg.stateDir, `policy-${new Date().toISOString().slice(0, 10)}.jsonl`),
      `${JSON.stringify({ at: new Date().toISOString(), ...row })}\n`, { mode: 0o600 });
  } catch { /* the decision stands even when it cannot be journaled */ }
}

export async function judge(cfg, policy, exec) {
  const req = { tool: exec.name, args: exec.arguments, iface: interfaceOf(exec.agent, cfg.interface), depth: depthOf(exec.agent), home: cfg.home };
  let out = policy === FALLBACK ? FALLBACK.decide(req) : decide(policy, req);
  if (out.decision === 'check') {
    try {
      const res = await post(`${cfg.gateway}/v1/disclosure/check`, { tool: out.tool, args: exec.arguments?.tool ? exec.arguments.arguments || {} : exec.arguments || {} },
        { auth: token(cfg), timeoutMs: 15000 });
      out = { ...out, decision: { allow: 'allow', ask: 'ask', block: 'deny' }[res.action] || 'ask', rule: `disclosure.${res.action}`, reason: res.reason || out.reason };
    } catch {
      out = { ...out, decision: 'ask', rule: 'disclosure.unavailable', reason: 'contrôle de divulgation indisponible : accord de Monsieur requis' };
    }
  }
  return { ...out, iface: req.iface, depth: req.depth };
}

export function apply(ctx, config = {}) {
  const cfg = { interface: config.interface || 'web', home: config.home || process.env.HOME || '/root', stateDir: config.stateDir,
    gateway: config.gateway || 'http://127.0.0.1:8890', tokenFile: config.tokenFile };
  let policy;
  try { policy = load(config.policyPath || undefined); } catch (e) {
    ctx.logger?.warn?.(`walter-policy: policy unreadable, strict fallback (${String(e)})`);
    policy = FALLBACK;
  }
  // never: synchronous, monotonic, after every pre-execute listener (incl. ones registered later with prepend)
  ctx.tools.guard((exec) => {
    if (policy === FALLBACK) return undefined;
    const out = decide(policy, { tool: exec.name, args: exec.arguments, iface: interfaceOf(exec.agent, cfg.interface), depth: depthOf(exec.agent), home: cfg.home });
    if (out.decision !== 'deny') return undefined;
    record(cfg, { decision: 'deny', stage: 'guard', tool: out.tool, class: out.class, rule: out.rule });
    return out.reason;
  });
  ctx.on('tools/pre-execute', async (exec, next) => {
    const out = await judge(cfg, policy, exec);
    if (out.decision !== 'allow') record(cfg, { decision: out.decision, stage: 'pre-execute', tool: out.tool, class: out.class, rule: out.rule, iface: out.iface, depth: out.depth });
    if (out.decision === 'deny') return { kind: 'deny', reason: out.reason, info: { name: 'WalterPolicy', code: 'WALTER_POLICY_DENIED', reason: out.reason } };
    const downstream = await next();                       // the kernel still decides (sandbox, its own asks)
    if (out.decision === 'ask' && downstream.kind === 'allow') {
      return { kind: 'ask', reason: `${out.reason} (${out.tool})`, displayReason: { en: `Walter asks before: ${out.tool}`, fr: `${out.reason} : ${out.tool}` } };
    }
    if (out.decision === 'ask' && downstream.kind === 'ask') return downstream;
    return downstream;
  }, { prepend: true });
}

export { strictest };
