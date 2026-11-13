// W.Alter engine plugins — what intake and events share (lot E2, 2026-11-10).
// Stdlib only: these files are loaded by the frozen DSH/Cordis kernel from outside its node_modules.
// One module instance per process, so the session → current run map is shared by both plugins.
import { createHash } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const MODES = ['shadow', 'native'];

/** Runtime notices that reach the loop as prompts (same list as walter_hook.MACHINE_PROMPTS). */
export const MACHINE_PROMPTS = ['<task-notification', '[SYSTEM NOTIFICATION', 'Another Claude session sent a message',
  '<cross-session-message', '<side-sessions-event>', '<ci-monitor-event>', '[Subagent hand-back]', '<system-reminder',
  '[ASYNC DELEGATION', '[CONTEXT COMPACTION', '[System:', '[SYSTEM:'];

export const machinePrompt = (text) => MACHINE_PROMPTS.some((m) => (text || '').trimStart().slice(0, 400).includes(m));

export const sha16 = (text) => createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16);

/** The part of a step the owner wrote: DSH marks it source.kind === 'user' (runtime notices have other kinds). */
export function ownerText(messages) {
  return (messages || []).filter((m) => m?.source?.kind === 'user')
    .map((m) => (m.content || []).filter((b) => b.type === 'text').map((b) => b.text).join(''))
    .filter((p) => p.trim()).map((p) => p.trim()).join('\n');   // as walter_hook.dsh_owner_prompt
}

/** Walter's session key, the same everywhere (skills.retrievals, walter_logs, runs): <runtime>/vm/<native id>. */
export const sessionKey = (runtime, agent) => {
  const id = agent?.session?.header?.id;
  return id ? `${runtime}/vm/${id}` : null;
};

export function settings(config = {}) {
  const env = process.env;
  const mode = config.mode || env.WALTER_ENGINE_INTAKE || 'shadow';
  if (!MODES.includes(mode)) throw new Error(`walter engine plugin: unknown mode ${mode}`);
  return {
    mode,
    runtime: config.runtime || 'dsh',
    stateDir: config.stateDir || env.WALTER_ENGINE_STATE || null,         // observations (shadow) and the run record
    runsDir: config.runsDir || null,                                     // <instance>/state/runs/current (MCP lookup)
    gateway: config.gateway || 'http://127.0.0.1:8890',
    tokenFile: config.tokenFile || null,
    preflight: config.preflight || `http://127.0.0.1:${env.WALTER_CONTEXT_PREFLIGHT_PORT || '8897'}`,
    skills: config.skills || env.WALTER_SKILLS_URL || 'http://127.0.0.1:8891',
    inject: config.inject || 'pack',
    preflightTimeoutMs: config.preflightTimeoutMs || 7000,
  };
}

let cachedToken = null;
export function token(cfg) {
  if (cachedToken) return cachedToken;
  if (!cfg.tokenFile) throw new Error('no gateway credential configured');
  const line = readFileSync(cfg.tokenFile, 'utf8').split('\n').find((l) => l.startsWith('WALTER_MEMORY_GATEWAY_TOKEN='));
  const value = line?.split('=').slice(1).join('=').trim().replace(/^['"]|['"]$/g, '');
  if (!value) throw new Error('gateway credential unavailable');
  return (cachedToken = value);
}

/** POST JSON with a deadline; the credential travels in a header, never in the URL. */
export async function post(url, body, { timeoutMs = 7000, auth = null } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) headers.Authorization = `Bearer ${auth}`;
  const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) {
    const err = new Error(`${new URL(url).pathname} ${res.status}`);
    err.status = res.status;
    err.refused = res.status === 401 || res.status === 403
      ? (await res.json().catch(() => ({})))?.detail?.refused || 'unauthorised' : null;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

// What became of a call: an authorisation refusal (expected, by design: 401/403) is never a transmission defect
// (no answer, timeout, 5xx), nor a malformed request (other 4xx). Only a transmission defect is worth a retry.
export function outcome(err) {
  if (!err) return 'delivered';
  if (err.refused) return 'refused';
  if (err.status && err.status < 500) return 'invalid';
  return 'transport';
}

// POST that retries once after a transmission defect only (callers send idempotent bodies: dedupe keys, run ids).
export async function deliver(url, body, opts = {}) {
  try {
    return { result: await post(url, body, opts), outcome: 'delivered' };
  } catch (e) {
    if (outcome(e) !== 'transport') return { error: e, outcome: outcome(e) };
    await new Promise((r) => setTimeout(r, opts.retryDelayMs ?? 500));
    try {
      return { result: await post(url, body, opts), outcome: 'delivered', retried: true };
    } catch (e2) {
      return { error: e2, outcome: outcome(e2), retried: true };
    }
  }
}

/** Shadow observations: one private JSONL per day. Hashes and numbers, never the owner's text. */
export function observe(cfg, row) {
  if (!cfg.stateDir) return;
  mkdirSync(cfg.stateDir, { recursive: true, mode: 0o700 });
  const day = new Date().toISOString().slice(0, 10);
  appendFileSync(join(cfg.stateDir, `observations-${day}.jsonl`),
    JSON.stringify({ at: new Date().toISOString(), observation: cfg.mode === 'shadow', ...row }) + '\n', { mode: 0o600 });
}

/** Current run per session (native mode): the turn that opened it, for its end and for a steering message. */
export const currentRuns = new Map();

/** What the preflight understood of the session's current owner turn ({thread, act, level, degraded}), published by
 * the intake for the strategies that apply it: the budget (effort checkpoint of the level) and the events (outcome). */
export const turnPlans = new Map();

/** The last completed exchange of a session, read from its journal (never from the surface: a record may have
 * replaced it): the owner's words, the final answer, how long ago, and the thread its context pack carried. The
 * preflight judges a new message in its conversation with it (short replies, floor of the plan). */
export function lastExchange(session, now = Date.now(), limit = 1200) {
  if (!session?.eventAt) return null;
  const text = (m) => (m?.content || []).filter((b) => b.type === 'text').map((b) => b.text).join('').trim();
  let ended = null, answer = '', message = '', thread = null;
  for (let seq = session.seq - 1, scanned = 0; seq >= 0 && scanned < 5000; seq -= 1, scanned += 1) {
    const event = session.eventAt(seq);
    if (ended === null) { if (event.type === 'turn/end') ended = event.time; continue; }
    if (event.type === 'turn/start') break;
    if (event.surfaceOp !== 'append') continue;
    if (event.type === 'assistant/message' && !answer) answer = text(event.data?.message);
    if (event.type === 'user/message') {
      const kind = event.data?.source?.kind;
      if (kind === 'walter-intake' && event.data.source.thread) thread = String(event.data.source.thread);
      if (kind === 'user') message = text(event.data) + (message ? `\n${message}` : '');
    }
  }
  if (ended === null || (!message && !answer)) return null;
  return { message: message.slice(0, limit), answer: answer.slice(0, limit),
    age_s: Math.max(0, Math.round((now - ended) / 1000)), thread_id: thread };
}

/** What a turn did, counted from the session journal (numbers only): model steps, tool calls, tool errors. */
export function turnStats(session) {
  const out = { steps: 0, tool_calls: 0, tool_errors: 0 };
  if (!session?.eventAt) return out;
  for (let seq = session.seq - 1, scanned = 0; seq >= 0 && scanned < 20000; seq -= 1, scanned += 1) {
    const event = session.eventAt(seq);
    if (event.type === 'turn/start') break;
    if (event.type === 'step/start') out.steps += 1;
    else if (event.type === 'tool/call') out.tool_calls += 1;
    else if (event.type === 'tool/result' && event.surfaceOp === 'append' && event.data?.message?.isError) out.tool_errors += 1;
  }
  return out;
}

// The runs this engine process holds open, kept on disk so the next process can close what a restart interrupted
// (the gateway closes a session's older run when its next turn starts; a session that never speaks again would keep
// its run open for ever). One file per engine state directory; each row names the process that opened it.
const openFile = (cfg) => (cfg.stateDir ? join(cfg.stateDir, 'open-runs.json') : null);
function readOpen(cfg) {
  try { const rows = JSON.parse(readFileSync(openFile(cfg), 'utf8')); return rows && typeof rows === 'object' ? rows : {}; }
  catch { return {}; }
}
function writeOpen(cfg, rows) {
  const file = openFile(cfg);
  mkdirSync(cfg.stateDir, { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(rows), { mode: 0o600 });
  renameSync(tmp, file);
}
/** Note a run as open (run given) or closed (run null) for a session. Never on the turn's path. */
export function trackRun(cfg, session, run = null) {
  if (!openFile(cfg)) return;
  try {
    const rows = readOpen(cfg);
    if (run?.run_id) rows[session] = { run_id: run.run_id, turn: run.turn ?? null, pid: process.pid, at: Date.now() };
    else if (rows[session]?.pid === process.pid || !alive(rows[session]?.pid)) delete rows[session];
    else return;
    writeOpen(cfg, rows);
  } catch { /* a measurement of last resort: the gateway's own sweep still closes abandoned runs */ }
}
const alive = (pid) => { try { return Boolean(pid) && (process.kill(pid, 0), true); } catch (e) { return e?.code === 'EPERM'; } };
/** The runs left open by an engine process that no longer exists: [{session, run_id, turn}], removed from the file. */
export function orphanRuns(cfg) {
  if (!openFile(cfg)) return [];
  try {
    const rows = readOpen(cfg);
    const gone = Object.entries(rows).filter(([, r]) => r?.pid !== process.pid && !alive(r?.pid));
    if (!gone.length) return [];
    for (const [session] of gone) delete rows[session];
    writeOpen(cfg, rows);
    return gone.map(([session, r]) => ({ session, run_id: r.run_id, turn: r.turn ?? null }));
  } catch { return []; }
}

/** The run record the walter MCP server (a child of this process) reads back, as walter_hook/runctx writes it. */
export function recordRun(cfg, runId, session) {
  if (!cfg.runsDir) return;
  mkdirSync(cfg.runsDir, { recursive: true, mode: 0o700 });
  const file = join(cfg.runsDir, `${process.pid}.json`);
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify({ run_id: runId, session_id: session, runtime: cfg.runtime, at: Date.now() / 1000 }),
    { mode: 0o600 });
  renameSync(tmp, file);
}
