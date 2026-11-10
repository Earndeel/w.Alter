// Engine API (lot E4): addresses, idempotent submit, result of a turn, cancel, approvals, door published to the
// policy, HTTP token. Kernel stand-in: a sessionController with the same five methods the plugin uses.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { Bindings, doors, engineSessionId, sessionMeta } from '../bindings.mjs';
import { TurnWatch, toClientEvent } from '../events.mjs';
import { EngineApi, ensureToken, handler, routerValidate } from '../index.mjs';
import { interfaceOf } from '../../../engine/plugins/policy/index.mjs';

class FakeSessions {
  constructor() { this.logs = new Map(); this.subs = new Map(); this.n = 0; this.prompts = []; this.cancelled = []; this.answer = 'ok'; }
  async create() { const id = `k${++this.n}`; this.logs.set(id, []); return { sessionId: id }; }
  async inspect(id) { if (!this.logs.has(id)) throw Object.assign(new Error('missing'), { code: 'session/missing' }); return { id }; }
  append(id, type, data) {
    const log = this.logs.get(id); const ev = { type, seq: log.length + 1, time: Date.now(), data }; log.push(ev);
    for (const s of this.subs.get(id) || []) s(ev);
  }
  async prompt({ requestId, sessionId, content }) {
    if (this.prompts.some((p) => p.requestId === requestId)) return { accepted: true };   // kernel idempotence
    this.prompts.push({ requestId, sessionId, text: content[0].text });
    const turn = this.logs.get(sessionId).filter((e) => e.type === 'turn/start').length + 1;
    setTimeout(() => {
      this.append(sessionId, 'turn/start', { turn });
      this.append(sessionId, 'user/message', { role: 'user', source: { kind: 'user', rpcId: requestId }, content });
      this.append(sessionId, 'tool/call', { turn, step: 1, name: 'read', callId: 'c1', arguments: {} });
      this.append(sessionId, 'tool/result', { turn, step: 1 });
      this.append(sessionId, 'assistant/message', { turn, step: 2, message: { role: 'assistant', content: [{ type: 'text', text: `${this.answer}:${content[0].text}` }] } });
      this.append(sessionId, 'turn/end', { turn, reason: { kind: 'completed' } });
    }, 5);
    return { accepted: true };
  }
  cancel({ sessionId }) { this.cancelled.push(sessionId); return { accepted: true }; }
  async selectModel(sel) { (this.selected ||= []).push(sel); return { selected: sel }; }
  async *follow({ address }, signal) {
    const id = address.sessionId; const q = []; let wake;
    const sub = (ev) => { q.push(ev); wake?.(); };
    if (!this.subs.has(id)) this.subs.set(id, new Set());
    this.subs.get(id).add(sub);
    try {
      yield { type: 'snapshot', records: this.logs.get(id).map((event) => ({ type: 'event', event })) };
      while (!signal.aborted) {
        if (!q.length) await new Promise((r) => { wake = r; signal.addEventListener('abort', r, { once: true }); });
        while (q.length) yield { type: 'event', event: q.shift() };
      }
    } finally { this.subs.get(id).delete(sub); }
  }
}

const owner = { kind: 'owner', id: 'lucas' };
function make(extra = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'walter-api-'));
  const sessions = new FakeSessions();
  const bindings = new Bindings(join(dir, 'bindings.json')).load();
  const api = new EngineApi({ sessions, bindings, workspace: dir, ...extra });
  return { dir, sessions, bindings, api };
}
const open = (api, o = {}) => api.op({ version: 1, op: 'session.open', interface: 'telegram', conversation: 'chat-1', principal: owner, mode: 'interactive', ...o });

test('session ids follow the contract; bad parts are refused', () => {
  assert.equal(engineSessionId('telegram', 'lucas', '42'), 'telegram/lucas/42');
  assert.throws(() => engineSessionId('fax', 'lucas', '1'));
  assert.throws(() => engineSessionId('api', 'a/b', '1'));
  assert.throws(() => engineSessionId('api', 'lucas', ''));
});

test('session.open creates once, resumes after a restart, publishes the door for the policy', async () => {
  const { dir, sessions, api } = make();
  const a = await open(api);
  assert.equal(a.session_id, 'telegram/lucas/chat-1'); assert.equal(a.resumed, false);
  assert.match(a.walter_session, /^dsh\/vm\/k1$/);
  const b = await open(api);
  assert.equal(b.resumed, true); assert.equal(sessions.n, 1);
  // a new process reads the same table: same kernel session, door known again
  doors().clear();
  const again = new EngineApi({ sessions, bindings: new Bindings(join(dir, 'bindings.json')).load(), workspace: dir });
  assert.equal((await open(again)).walter_session, 'dsh/vm/k1');
  assert.equal(interfaceOf({ session: { header: { id: 'k1' } } }, 'web'), 'telegram');
  assert.equal(interfaceOf({ parentAgent: { session: { header: { id: 'k1' } } } }, 'web'), 'telegram', 'a child is judged under its root door');
  assert.equal(interfaceOf({ session: { header: { id: 'other' } } }, 'web'), 'web');
  // the real kernel: no parentAgent on a child, its header names its parent session (E5)
  assert.equal(interfaceOf({ session: { header: { id: 'c-1', parentSession: 'k1', origin: 'subagent', delegationDepth: 1 } } }, 'web'), 'telegram');
  assert.equal(interfaceOf({ session: { header: { id: 'c-2', parentSession: 'c-1', origin: 'subagent', delegationDepth: 2 } } }, 'web'), 'telegram', 'a grandchild too');
  assert.equal(statSync(join(dir, 'bindings.json')).mode & 0o777, 0o600);
});

test('permissions can only narrow; command mode is the command door', async () => {
  const { api } = make();
  await assert.rejects(open(api, { permissions: 'web-owner' }), { code: 'permissions_wider_than_door' });
  const c = await open(api, { conversation: 'router-1', mode: 'command', interface: 'api' });
  assert.equal(c.door, 'command');
  const n = await open(api, { conversation: 'narrow', permissions: 'command' });
  assert.equal(n.door, 'command');
  await assert.rejects(open(api, { conversation: 'narrow' }), { code: 'door_mismatch' });
});

test('continuity: an owner carries an existing Walter session into a conversation, once', async () => {
  const { api, sessions } = make();
  const web = (await sessions.create()).sessionId;
  const r = await open(api, { conversation: 'cont', continue_session: `dsh/vm/${web}` });
  assert.equal(r.walter_session, `dsh/vm/${web}`);
  await assert.rejects(open(api, { conversation: 'cont2', continue_session: web }), { code: 'already_bound' });
  await assert.rejects(open(api, { conversation: 'cont3', continue_session: 'nope' }), { code: 'unknown_walter_session' });
  await assert.rejects(open(api, { conversation: 'cont4', continue_session: web, principal: { kind: 'machine', id: 'router' } }), { code: 'owner_only' });
});

test('turn.submit waits for the result; same idempotency key = one prompt; result readable later', async () => {
  const { api, sessions } = make();
  await open(api);
  const r = await api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: 'bonjour' }, channel: 'owner', idempotency_key: 'tg-msg-0001', wait_ms: 2000 });
  assert.equal(r.result.done, true); assert.equal(r.result.status, 'ok');
  assert.equal(r.result.text, 'ok:bonjour'); assert.deepEqual(r.result.tools, ['read']);
  await api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: 'bonjour' }, idempotency_key: 'tg-msg-0001' });
  assert.equal(sessions.prompts.length, 1, 'replay of the same Telegram message never runs twice');
  const later = await api.op({ version: 1, op: 'turn.result', session_id: 'telegram/lucas/chat-1', request_id: 'tg-msg-0001' });
  assert.equal(later.result.text, 'ok:bonjour');
  await assert.rejects(api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/none', message: { text: 'x' }, idempotency_key: 'k-00000001' }), { code: 'unknown_session' });
  await assert.rejects(api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: 'x' } }), { code: 'idempotency_key_required' });
  await assert.rejects(api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: '  ' }, idempotency_key: 'k-00000002' }), { code: 'empty_message' });
});

test('delegate: one engine session per task, parent run published, task model, depth limit, never asks', async () => {
  const asked = [];
  const { api, sessions } = make({ validateModel: async (m) => (asked.push(m), m.id === 'claude-opus-5-5' ? { ok: true } : { ok: false, error: `modèle inconnu du router : ${m.id}` }) });
  const d = { version: 1, goal: 'Trouve la date du jour', task: 'general', budget_seconds: 60, idempotency_key: 'walter-run-0001',
    parent: { run_id: 'run-parent', session_id: 'mcp/claude/s1', depth: 0 } };
  const r = await api.op({ version: 1, op: 'delegate', caller: 'claude', delegation: d });
  assert.equal(r.ok, true); assert.match(r.output, /^ok:\[Délégation Walter\]/); assert.match(r.session_id, /^mcp\/claude\/task-/);
  const kernel = r.walter_session.replace('dsh/vm/', '');
  assert.deepEqual(sessionMeta().get(kernel), { channel: 'machine', parent_run_id: 'run-parent', model: null });
  assert.deepEqual(sessions.selected, [{ sessionId: kernel, provider: 'walter', model: 'general' }]);
  const again = await api.op({ version: 1, op: 'delegate', caller: 'claude', delegation: d });
  assert.equal(again.resumed, true); assert.equal(sessions.prompts.length, 1, 'a replayed delegation runs once');
  await assert.rejects(api.op({ version: 1, op: 'delegate', delegation: { ...d, idempotency_key: 'walter-run-0002', parent: { ...d.parent, depth: 3 } } }), { code: 'max_depth' });
  await assert.rejects(api.op({ version: 1, op: 'delegate', delegation: { ...d, idempotency_key: undefined } }), { code: 'idempotency_key_required' });
  assert.equal(await api.approval({ agent: { session: { header: { id: kernel } } }, toolName: 'bash' }, async () => 'next'), 'rejected', 'nobody to ask');
  // a model named by the owner (validated by Walter Router): published for the run plan, no poste selected
  const named = await api.op({ version: 1, op: 'delegate', caller: 'claude', delegation: { ...d, idempotency_key: 'walter-run-0003', model: { id: 'claude-opus-5-5', provider: 'venice' } } });
  const nk = named.walter_session.replace('dsh/vm/', '');
  assert.deepEqual(sessionMeta().get(nk).model, { id: 'claude-opus-5-5', provider: 'venice' });
  assert.equal(sessions.selected.length, 1, 'no poste chosen when a model is named');
  assert.deepEqual(named.model, { id: 'claude-opus-5-5', provider: 'venice' });
  await assert.rejects(api.op({ version: 1, op: 'delegate', delegation: { ...d, idempotency_key: 'walter-run-0004', model: { id: 'x; rm -rf' } } }), { code: 'invalid_model' });
  // a model Walter Router refuses: explicit error before any session opens, never the former loop
  const before = sessions.prompts.length;
  await assert.rejects(api.op({ version: 1, op: 'delegate', delegation: { ...d, idempotency_key: 'walter-run-0005', model: 'nope-model' } }), { code: 'model_unavailable', message: /inconnu/ });
  assert.equal(sessions.prompts.length, before); assert.deepEqual(asked.map((m) => m.id), ['claude-opus-5-5', 'nope-model']);
  // without a Router to ask, a named model is refused too
  const bare = make().api;
  await assert.rejects(bare.op({ version: 1, op: 'delegate', delegation: { ...d, idempotency_key: 'walter-run-0006', model: 'claude-opus-5-5' } }), { code: 'model_validation_unavailable' });
});

test('routerValidate asks the walter-router CLI and refuses when it cannot answer', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'walter-rv-'));
  const bin = join(dir, 'walter-router');
  writeFileSync(bin, '#!/bin/sh\ncase "$4" in good) echo \'{"mode":"delegate","model_id":"good","execution":[{"provider":"p"}]}\';; '
    + 'bad) echo \'{"mode":"none","error":"modèle inconnu du router : bad"}\';; *) exit 3;; esac\n', { mode: 0o755 });
  assert.deepEqual(await routerValidate({ id: 'good' }, { bin }), { ok: true, model_id: 'good' });
  assert.deepEqual(await routerValidate({ id: 'bad' }, { bin }), { ok: false, error: 'modèle inconnu du router : bad' });
  assert.match((await routerValidate({ id: 'other' }, { bin })).error, /^router_unavailable/);
});

test('a key replayed before the kernel logged it is still one turn', async () => {
  const { api, sessions } = make();
  await open(api);
  let calls = 0;                                   // the real kernel only dedupes what it has already logged
  const prompt = sessions.prompt.bind(sessions);
  sessions.prompt = async (...a) => { calls += 1; return prompt(...a); };
  const body = { version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: 'un' }, idempotency_key: 'tg-1-990001' };
  const [a, b] = await Promise.all([api.op(body), api.op(body)]);
  assert.equal(calls, 1, 'one prompt reaches the kernel for one key');
  assert.equal(a.request_id, b.request_id); assert.equal(Boolean(a.replayed) !== Boolean(b.replayed), true);
  await api.op({ ...body, idempotency_key: 'tg-1-990002' });
  assert.equal(calls, 2);
});

test('the kernel approval audit pair is not a client event (only the API id can be answered)', () => {
  assert.equal(toClientEvent({ seq: 3, time: 1, type: 'approval/asked', data: { id: 'kernel-id', toolName: 'bash' } }), null);
  assert.equal(toClientEvent({ seq: 4, time: 1, type: 'approval/decided', data: { id: 'kernel-id', outcome: 'rejected' } }), null);
});

test('turn.cancel reaches the kernel', async () => {
  const { api, sessions } = make();
  await open(api);
  await assert.rejects(api.op({ version: 1, op: 'turn.cancel', session_id: 'telegram/lucas/chat-1' }), { code: 'reason_required' });
  await api.op({ version: 1, op: 'turn.cancel', session_id: 'telegram/lucas/chat-1', reason: '/stop' });
  assert.deepEqual(sessions.cancelled, ['k1']);
  await assert.rejects(api.op({ version: 1, op: 'delegate', delegation: {} }), { code: 'invalid_delegation' });
});

test('approvals: API sessions are answered by their owner, web sessions keep their dialog, commands never ask', async () => {
  const { api } = make({ approvalTimeoutMs: 200 });
  await open(api);
  await open(api, { conversation: 'cmd', mode: 'command', interface: 'api' });
  const agent = { session: { header: { id: 'k1' } } };
  const asked = api.approval({ agent: { parentAgent: agent }, toolName: 'browser_session', reason: 'agir au nom de Monsieur' }, async () => 'unavailable');
  const [p] = (await api.op({ version: 1, op: 'approval.list', session_id: 'telegram/lucas/chat-1' })).approvals;
  assert.equal(p.tool, 'browser_session'); assert.equal(p.child, true);
  await assert.rejects(api.op({ version: 1, op: 'approval.answer', request_id: p.request_id, decision: 'allow_once', principal: { kind: 'owner', id: 'someone' } }), { code: 'not_the_owner' });
  await api.op({ version: 1, op: 'approval.answer', request_id: p.request_id, decision: 'allow_once', principal: owner });
  assert.equal(await asked, 'allowed-once');
  // a real kernel child (header names its parent): its request reaches the root's client too (E5)
  const real = api.approval({ agent: { session: { header: { id: 'kc', parentSession: 'k1', origin: 'subagent' } } }, toolName: 'browser_session' }, async () => 'next');
  const [q] = (await api.op({ version: 1, op: 'approval.list', session_id: 'telegram/lucas/chat-1' })).approvals;
  assert.equal(q.child, true);
  await api.op({ version: 1, op: 'approval.answer', request_id: q.request_id, decision: 'deny', principal: owner });
  assert.equal(await real, 'rejected');
  // unanswered = refused
  assert.equal(await api.approval({ agent, toolName: 'x' }, async () => 'unavailable'), 'rejected');
  // web session (not bound) goes on to the web dialog
  assert.equal(await api.approval({ agent: { session: { header: { id: 'webk' } } }, toolName: 'x' }, async () => 'next'), 'next');
  assert.equal(await api.approval({ agent: { session: { header: { id: 'k2' } } }, toolName: 'x' }, async () => 'next'), 'rejected');
  // withdrawn by the kernel
  const ctrl = new AbortController();
  const w = api.approval({ agent, toolName: 'y', signal: ctrl.signal }, async () => 'unavailable');
  ctrl.abort(); assert.equal(await w, 'cancelled');
});

test('events: live client events of a session, approval notices included', async () => {
  const { api } = make();
  await open(api);
  const ctrl = new AbortController();
  const it = api.events('telegram/lucas/chat-1', null, ctrl.signal);
  const seen = [];
  const reader = (async () => { for await (const e of it) { seen.push(e.type); if (e.type === 'turn.ended') break; } })();
  await new Promise((r) => setTimeout(r, 10));
  await api.op({ version: 1, op: 'turn.submit', session_id: 'telegram/lucas/chat-1', message: { text: 'salut' }, idempotency_key: 'tg-msg-0002' });
  await reader; ctrl.abort();
  assert.deepEqual(seen, ['turn.started', 'message.user', 'tool.called', 'tool.result', 'message.assistant', 'turn.ended']);
});

test('TurnWatch: queued message counts for the next turn; other turns are ignored', () => {
  const w = new TurnWatch('r1');
  const ev = (type, data) => ({ type, seq: 0, data });
  w.feed(ev('turn/start', { turn: 1 })).feed(ev('user/message', { source: { kind: 'user', rpcId: 'r0' } }))
    .feed(ev('user/message', { source: { kind: 'user', rpcId: 'r1' } }));
  assert.equal(w.turn, 1, 'received while turn 1 runs (steer)');
  const q = new TurnWatch('r2');
  q.feed(ev('user/message', { source: { kind: 'user', rpcId: 'r2' } })).feed(ev('turn/start', { turn: 3 }))
    .feed(ev('assistant/message', { turn: 3, message: { content: [{ type: 'text', text: 'fini' }] } }))
    .feed(ev('turn/end', { turn: 3, reason: { kind: 'aborted', reason: 'user' } }));
  assert.deepEqual([q.done, q.result().status, q.result().text], [true, 'cancelled', 'fini']);
  assert.equal(toClientEvent(ev('user/message', { source: { kind: 'hook' } })), null, 'injected context is not shown as the owner');
});

test('HTTP: token required (header only), JSON envelope, token file 0600', async () => {
  const { dir, api } = make();
  const token = ensureToken(join(dir, 'tok', 'api.token'));
  assert.equal(statSync(join(dir, 'tok', 'api.token')).mode & 0o777, 0o600);
  assert.equal(ensureToken(join(dir, 'tok', 'api.token')), token, 'stable across restarts');
  const { createServer } = await import('node:http');
  const srv = createServer(handler(api, token)); await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  try {
    assert.equal((await fetch(`${base}/v1/health`)).status, 401);
    assert.equal((await fetch(`${base}/v1/health?token=${token}`)).status, 401);
    const h = await fetch(`${base}/v1/health`, { headers: { Authorization: `Bearer ${token}` } });
    assert.equal(h.status, 200); assert.equal((await h.json()).ok, true);
    const bad = await fetch(`${base}/v1`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ version: 2, op: 'health' }) });
    assert.equal(bad.status, 400);
    const ev = await fetch(`${base}/v1/events?session_id=telegram/lucas/none`, { headers: { Authorization: `Bearer ${token}` } });
    assert.equal(ev.status, 404);
  } finally { srv.close(); }
  assert.ok(!readFileSync(join(dir, 'tok', 'api.token'), 'utf8').includes('\n\n'));
});
