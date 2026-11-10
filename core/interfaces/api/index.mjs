// W.Alter Engine API — the canonical door of the engine for every client (lot E4, 2026-11-10).
// Contract: core/engine/contracts/engine-api.v1.json. A host plugin of the engine itself, on loopback only, with an
// agent token in a header: Telegram, the web, Walter modules and tests submit, follow, find again, interrupt and
// answer approvals through it. It owns no session, run or bus of its own: kernel sessions (sessionController:
// create / prompt / cancel / follow, idempotent prompts by requestId), the Run Plane and the bus (opened by the
// intake/events plugins for every turn whatever its door) and Walter's execution policy (door published to it).
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { Bindings, DOORS, SESSION_ID, effectiveDoor, engineSessionId } from './bindings.mjs';
import { TurnWatch, toClientEvent, turnStatus } from './events.mjs';

export const name = 'walter-engine-api';
export const inject = ['sessionController'];

const MAX_BODY = 1 << 20;
const PRESET_OF = { web: 'web-owner', telegram: 'telegram-owner', api: 'api', command: 'command', mcp: 'api',
  schedule: 'api', webhook: 'api', lab: 'api' };

export class ApiError extends Error {
  constructor(status, code, message) { super(message || code); this.status = status; this.code = code; }
}

/** The token clients present; created once (0600) where the composition says, never logged, never in a URL. */
export function ensureToken(file) {
  try { const t = readFileSync(file, 'utf8').trim(); if (t.length >= 32) return t; } catch (e) { if (e.code !== 'ENOENT') throw e; }
  mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
  const t = randomBytes(32).toString('hex');
  writeFileSync(file, `${t}\n`, { mode: 0o600, flag: 'w' });
  return t;
}

const same = (a, b) => { const x = Buffer.from(String(a)); const y = Buffer.from(String(b)); return x.length === y.length && timingSafeEqual(x, y); };

const kernelOf = (row) => row.kernel;
const walterKey = (kernel) => `dsh/vm/${kernel}`;
const rootOf = (agent) => { let a = agent; while (a?.parentAgent) a = a.parentAgent; return a; };

/** The engine side of the API, independent of HTTP (tests drive it with a stand-in sessionController). */
export class EngineApi {
  constructor({ sessions, bindings, workspace, approvalTimeoutMs = 10 * 60_000, log = () => {} }) {
    this.sessions = sessions; this.bindings = bindings; this.workspace = workspace;
    this.approvalTimeoutMs = approvalTimeoutMs; this.log = log;
    this.pending = new Map();             // approval id → { row, resolve, timer }
    this.listeners = new Set();           // live approval notices for SSE subscribers
  }

  row(sessionId) {
    if (!SESSION_ID.test(String(sessionId || ''))) throw new ApiError(400, 'invalid_session_id');
    const row = this.bindings.get(sessionId);
    if (!row) throw new ApiError(404, 'unknown_session', 'session.open first');
    return row;
  }

  async op(body) {
    if (!body || body.version !== 1) throw new ApiError(400, 'version', 'version must be 1');
    switch (body.op) {
      case 'health': return this.health();
      case 'session.open': return this.open(body);
      case 'session.list': return { sessions: this.bindings.list({ iface: body.interface, account: body.account }).map(this.view) };
      case 'turn.submit': return this.submit(body, 'queue', true);
      case 'turn.queue': return this.submit(body, 'queue');
      case 'turn.steer': return this.submit(body, 'steer');
      case 'turn.result': return this.result(body);
      case 'turn.cancel': return this.cancel(body);
      case 'approval.list': return { approvals: [...this.pending.values()].map((p) => p.row).filter((r) => !body.session_id || r.session_id === body.session_id) };
      case 'approval.answer': return this.answer(body);
      case 'delegate': throw new ApiError(501, 'not_yet', 'delegation through the API arrives with lot E5');
      default: throw new ApiError(400, 'unknown_op');
    }
  }

  view = (row) => ({ session_id: row.session_id, interface: row.interface, door: row.door, mode: row.mode,
    principal: row.principal, walter_session: walterKey(row.kernel), created_at: row.created_at });

  health() {
    return { ok: true, version: 1, sessions: Object.keys(this.bindings.rows).length, pending_approvals: this.pending.size };
  }

  async open({ interface: iface, conversation, principal, mode = 'interactive', permissions, continue_session: cont }) {
    if (!DOORS.includes(iface)) throw new ApiError(400, 'invalid_interface');
    if (!principal || !['owner', 'machine', 'test'].includes(principal.kind)) throw new ApiError(400, 'invalid_principal');
    if (!['interactive', 'command'].includes(mode)) throw new ApiError(400, 'invalid_mode');
    let id;
    try { id = engineSessionId(iface, principal.id, conversation); } catch (e) { throw new ApiError(400, 'invalid_session_id', e.message); }
    const door = effectiveDoor(iface, mode);
    // A caller can only narrow: today a session runs under its door's preset (or the command preset, stricter).
    if (permissions && permissions !== PRESET_OF[door] && permissions !== 'command') throw new ApiError(403, 'permissions_wider_than_door', `door ${door} allows at most ${PRESET_OF[door]}`);
    const finalDoor = permissions === 'command' ? 'command' : door;
    const known = this.bindings.get(id);
    if (known) {
      if (known.door !== finalDoor) throw new ApiError(409, 'door_mismatch', `session ${id} runs as ${known.door}`);
      return { ...this.view(known), resumed: true };
    }
    let kernel;
    if (cont) {   // continuity: carry an existing Walter session (e.g. one begun on the web) into this conversation
      if (principal.kind !== 'owner') throw new ApiError(403, 'owner_only');
      kernel = String(cont).replace(/^dsh\/vm\//, '');
      if (this.bindings.byKernel(kernel)) throw new ApiError(409, 'already_bound');
      const seen = await this.sessions.inspect(kernel).catch(() => null);
      if (!seen) throw new ApiError(404, 'unknown_walter_session');
    } else {
      kernel = (await this.sessions.create({ cwd: this.workspace })).sessionId;
    }
    const row = this.bindings.set({ session_id: id, kernel, interface: iface, door: finalDoor, mode, principal,
      created_at: new Date().toISOString() });
    this.log('session.open', { session_id: id, door: finalDoor, continued: Boolean(cont) });
    return { ...this.view(row), resumed: false };
  }

  async submit({ session_id: sid, message, channel = 'owner', idempotency_key: key, wait_ms: waitMs }, mode, keyed = false) {
    const row = this.row(sid);
    const text = typeof message?.text === 'string' ? message.text : '';
    if (!text.trim()) throw new ApiError(400, 'empty_message');
    if (!['owner', 'machine', 'test'].includes(channel)) throw new ApiError(400, 'invalid_channel');
    if (keyed && !key) throw new ApiError(400, 'idempotency_key_required', 'turn.submit needs the message id of its door (never run twice)');
    const requestId = key ? String(key) : randomUUID();
    if (requestId.length < 8 || requestId.length > 200) throw new ApiError(400, 'invalid_idempotency_key');
    const kernel = kernelOf(row);
    const watch = waitMs ? this.watch(kernel, requestId, Math.min(Number(waitMs) || 0, 30 * 60_000)) : null;
    try {
      await this.sessions.prompt({ requestId, sessionId: kernel, mode, content: [{ type: 'text', text }] }, AbortSignal.timeout(60_000));
    } catch (e) {
      watch?.abort();
      throw new ApiError(e?.code === 'session/writer-held' ? 409 : 502, e?.code || 'prompt_failed', String(e?.message || e).slice(0, 200));
    }
    const out = { accepted: true, session_id: sid, request_id: requestId, walter_session: walterKey(kernel), mode };
    if (!watch) return out;
    return { ...out, result: await watch.promise };
  }

  async result({ session_id: sid, request_id: requestId, wait_ms: waitMs = 0 }) {
    const row = this.row(sid);
    if (!requestId) throw new ApiError(400, 'request_id_required');
    const w = this.watch(kernelOf(row), String(requestId), Math.min(Number(waitMs) || 0, 30 * 60_000));
    return { session_id: sid, request_id: requestId, result: await w.promise };
  }

  /** Reads the session's log (opening page, then live) until the request's turn ends or the deadline passes. */
  watch(kernel, requestId, waitMs) {
    const ctrl = new AbortController();
    const tw = new TurnWatch(requestId);
    const promise = (async () => {
      const timer = setTimeout(() => ctrl.abort(), Math.max(waitMs, 1));
      try {
        for await (const frame of this.sessions.follow({ address: { kind: 'session', sessionId: kernel } }, ctrl.signal)) {
          if (frame.type === 'snapshot') for (const r of frame.records || []) tw.feed(r.event);
          else if (frame.type === 'event') tw.feed(frame.event);
          if (tw.done) break;
          if (frame.type === 'snapshot' && !waitMs) break;    // a read, not a wait
        }
      } catch (e) {
        if (!ctrl.signal.aborted) throw new ApiError(502, e?.code || 'follow_failed', String(e?.message || e).slice(0, 200));
      } finally { clearTimeout(timer); ctrl.abort(); }
      return tw.result();
    })();
    return { promise, abort: () => ctrl.abort() };
  }

  async cancel({ session_id: sid, reason }) {
    const row = this.row(sid);
    if (!reason) throw new ApiError(400, 'reason_required');
    try { this.sessions.cancel({ sessionId: kernelOf(row) }); }
    catch (e) { throw new ApiError(409, e?.code || 'not_running', String(e?.message || e).slice(0, 200)); }
    this.log('turn.cancel', { session_id: sid });
    return { accepted: true, session_id: sid };
  }

  /** Answerer for sessions this API opened (the web keeps its own dialog): the client decides, no answer = refused. */
  async approval(req, next) {
    const root = rootOf(req.agent);
    const row = this.bindings.byKernel(root?.session?.header?.id);
    if (!row || row.door === 'web') return next();
    if (row.door === 'command') return 'rejected';          // a command never asks: it is refused
    const id = randomUUID();
    const view = { request_id: id, session_id: row.session_id, tool: req.toolName, reason: req.reason ?? null,
      child: root !== req.agent, at: new Date().toISOString() };
    return new Promise((resolve) => {
      const settle = (outcome) => {
        const p = this.pending.get(id); if (!p) return;
        this.pending.delete(id); clearTimeout(p.timer);
        this.emit(row.session_id, { type: 'approval.answered', request_id: id, outcome });
        resolve(outcome);
      };
      const timer = setTimeout(() => settle('rejected'), this.approvalTimeoutMs);
      this.pending.set(id, { row: view, settle, timer, principal: row.principal });
      req.signal?.addEventListener?.('abort', () => settle('cancelled'), { once: true });
      this.emit(row.session_id, { type: 'approval.requested', ...view });
      this.log('approval.requested', { session_id: row.session_id, tool: req.toolName });
    });
  }

  answer({ request_id: id, decision, principal }) {
    const p = this.pending.get(id);
    if (!p) throw new ApiError(404, 'unknown_request', 'already answered, withdrawn or expired');
    if (!['allow_once', 'deny'].includes(decision)) throw new ApiError(400, 'invalid_decision');
    if (principal?.kind !== 'owner' || principal?.id !== p.principal?.id) throw new ApiError(403, 'not_the_owner');
    p.settle(decision === 'allow_once' ? 'allowed-once' : 'rejected');
    return { accepted: true, request_id: id, outcome: decision };
  }

  emit(sessionId, event) { for (const l of this.listeners) l(sessionId, { ...event, at: Date.now() }); }

  /** Live client events of one session: kernel log entries after `sinceSeq` plus approval notices. */
  async *events(sid, sinceSeq, signal) {
    const row = this.row(sid);
    const queue = []; let wake = null;
    const push = (e) => { queue.push(e); wake?.(); };
    const onNotice = (s, e) => { if (s === sid) push(e); };
    this.listeners.add(onNotice);
    for (const p of this.pending.values()) if (p.row.session_id === sid) push({ type: 'approval.requested', ...p.row });
    (async () => {
      try {
        for await (const frame of this.sessions.follow({ address: { kind: 'session', sessionId: kernelOf(row) } }, signal)) {
          const evs = frame.type === 'snapshot' ? (frame.records || []).map((r) => r.event) : frame.type === 'event' ? [frame.event] : [];
          for (const ev of evs) {
            if (sinceSeq != null && ev.seq <= sinceSeq) continue;
            if (frame.type === 'snapshot' && sinceSeq == null) continue;   // live only unless asked to replay
            const ce = toClientEvent(ev); if (ce) push(ce);
          }
        }
      } catch (e) { if (!signal.aborted) push({ type: 'stream.error', code: e?.code || 'follow_failed' }); }
      push(null);
    })();
    try {
      while (!signal.aborted) {
        if (!queue.length) await new Promise((r) => { wake = r; signal.addEventListener('abort', r, { once: true }); });
        wake = null;
        while (queue.length) { const e = queue.shift(); if (e === null) return; yield e; }
      }
    } finally { this.listeners.delete(onNotice); }
  }
}

async function readJson(req) {
  let size = 0; const chunks = [];
  for await (const c of req) { size += c.length; if (size > MAX_BODY) throw new ApiError(413, 'too_large'); chunks.push(c); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { throw new ApiError(400, 'invalid_json'); }
}

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

/** HTTP face: POST /v1 {version, op, …} (engine-api.v1), GET /v1/health, GET /v1/events?session_id=&since_seq= (SSE). */
export function handler(api, token) {
  return async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    try {
      const auth = req.headers.authorization || '';
      if (!auth.startsWith('Bearer ') || !same(auth.slice(7).trim(), token)) throw new ApiError(401, 'unauthorised');
      if (req.method === 'GET' && url.pathname === '/v1/health') return send(res, 200, api.health());
      if (req.method === 'POST' && url.pathname === '/v1') return send(res, 200, await api.op(await readJson(req)));
      if (req.method === 'GET' && url.pathname === '/v1/events') {
        const ctrl = new AbortController();
        req.on('close', () => ctrl.abort());
        const since = url.searchParams.get('since_seq');
        const it = api.events(url.searchParams.get('session_id'), since == null ? null : Number(since), ctrl.signal);
        const first = await it.next();                     // errors (unknown session) still answer as JSON
        res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' });
        res.write(': walter engine events\n\n');
        const ping = setInterval(() => res.write(': ping\n\n'), 15_000);
        try {
          for (let r = first; !r.done; r = await it.next()) res.write(`event: ${r.value.type}\ndata: ${JSON.stringify(r.value)}\n\n`);
        } finally { clearInterval(ping); ctrl.abort(); res.end(); }
        return undefined;
      }
      throw new ApiError(404, 'not_found');
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 500;
      if (!res.headersSent) send(res, status, { error: e instanceof ApiError ? e.code : 'internal', detail: String(e?.message || e).slice(0, 300) });
      else res.end();
    }
    return undefined;
  };
}

export function apply(ctx, config = {}) {
  const host = config.host || '127.0.0.1';
  if (!['127.0.0.1', '::1', 'localhost'].includes(host)) throw new Error('walter-engine-api: loopback only');
  const stateDir = config.stateDir;
  if (!stateDir || !config.tokenFile || !config.workspace) throw new Error('walter-engine-api: stateDir, tokenFile and workspace are required');
  const bindings = new Bindings(join(stateDir, 'bindings.json')).load();
  const journal = (kind, row) => {
    try { mkdirSync(stateDir, { recursive: true, mode: 0o700 }); writeFileSync(join(stateDir, `api-${new Date().toISOString().slice(0, 10)}.jsonl`), `${JSON.stringify({ at: new Date().toISOString(), kind, ...row })}\n`, { flag: 'a', mode: 0o600 }); }
    catch { /* journal is best effort */ }
  };
  const api = new EngineApi({ sessions: ctx.sessionController, bindings, workspace: config.workspace,
    approvalTimeoutMs: config.approvalTimeoutMs, log: journal });
  ctx.on('approval/request', (req, next) => api.approval(req, next), { prepend: true });
  const server = createServer(handler(api, ensureToken(config.tokenFile)));
  server.listen(Number(config.port || 8895), host);
  server.on('error', (e) => ctx.logger?.warn?.(`walter-engine-api: ${e.message}`));
  ctx.on('dispose', () => new Promise((r) => { for (const p of api.pending.values()) p.settle('cancelled'); server.close(() => r()); server.closeAllConnections?.(); }));
  return api;
}

export { DOORS, turnStatus };
