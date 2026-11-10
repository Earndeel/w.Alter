// Lot E2: engine intake and events plugins against fake Walter services (gateway, preflight, skills).
// Run: node --test core/engine/tests/plugins.test.mjs  (also run by tests/test_engine_plugins.py)
import { test, beforeEach, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import * as intake from '../plugins/intake/index.mjs';
import * as events from '../plugins/events/index.mjs';
import { currentRuns, ownerText } from '../plugins/shared.mjs';

const calls = [];
let behaviour = {};
const server = createServer((req, res) => {
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', () => {
    const data = body ? JSON.parse(body) : null;
    calls.push({ path: req.url, auth: req.headers.authorization || null, body: data });
    const reply = (code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
    if (behaviour[req.url]) return behaviour[req.url](data, reply);
    if (req.url === '/v1/privacy/classify') return reply(200, { privacy_class: /sk-/.test(data.text) ? 'local_only' : 'cloud_allowed' });
    if (req.url === '/v1/runs/start') return reply(200, { run_id: `run-${calls.length}`, privacy_class: /sk-/.test(data.goal) ? 'local_only' : 'cloud_allowed' });
    if (req.url === '/v1/runs/end') return reply(200, { run_id: data.run_id });
    if (req.url === '/v1/bus/emit') return reply(200, { id: 1, duplicate: false });
    if (req.url === '/v1/context') return reply(200, { text: 'souvenir daté' });
    if (req.url === '/preflight') return reply(200, { act: 'continue', level: 'L3', model_profile: { task: 'general', level: 'L1' } });
    if (req.url === '/preflight?inject=1') return reply(200, { plan: { level: 'L3' }, text: 'PACK' });
    if (req.url === '/v1/expose') return reply(200, { text: 'SKILLS' });
    return reply(404, {});
  });
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
after(() => server.close());

const dir = mkdtempSync(join(tmpdir(), 'walter-engine-'));
const tokenFile = join(dir, '.env');
writeFileSync(tokenFile, 'WALTER_MEMORY_GATEWAY_TOKEN=t-test\n', { mode: 0o600 });
const config = (mode, extra = {}) => ({ mode, gateway: base, preflight: base, skills: base, tokenFile,
  stateDir: join(dir, `state-${mode}-${Math.random()}`), runsDir: join(dir, 'runs'), ...extra });
const paths = () => calls.map((c) => c.path);
const msg = (kind, text) => ({ role: 'user', source: { kind }, content: [{ type: 'text', text }] });
const agent = (id = 'session-1') => ({ session: { header: { id } } });

function fakeCtx() {
  const handlers = {};
  return { handlers, logger: { warn: () => {} }, on(name, fn) { (handlers[name] ||= []).push(fn); } };
}
const observations = (cfg) => readdirSync(cfg.stateDir).flatMap((f) =>
  readFileSync(join(cfg.stateDir, f), 'utf8').trim().split('\n').map((l) => JSON.parse(l)));

beforeEach(() => { calls.length = 0; behaviour = {}; currentRuns.clear(); });

test('owner text is what the owner wrote, as the hook keeps it', () => {
  assert.equal(ownerText([msg('user-approval', 'policy changed'), msg('user', '  bonjour  '), msg('user', ' '), msg('user', 'ça va ?')]),
    'bonjour\nça va ?');
  assert.equal(ownerText([msg('hooks-claude-code', '<walter-context>x</walter-context>')]), '');
});

test('shadow: the step goes on at once; only a plan request without run, never a run, a bus event or an injection', async () => {
  const cfg = config('shadow');
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  let resolveSlow;
  behaviour['/preflight'] = (data, reply) => { resolveSlow = () => reply(200, { act: 'continue', level: 'L2' }); };
  const downstream = { kind: 'enter', messages: [] };
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'quel temps fait-il à Bangkok ?')], turn: 3, step: 0 },
    async () => downstream);
  assert.equal(out, downstream);                       // untouched, and returned before the preflight answered
  while (!resolveSlow) await new Promise((r) => setTimeout(r, 5));
  resolveSlow();
  await new Promise((r) => setTimeout(r, 50));
  assert.deepEqual(paths(), ['/v1/privacy/classify', '/preflight']);
  assert.equal(calls[1].body.run_id, null);
  assert.equal(calls[1].body.session_id, 'dsh/vm/session-1');
  assert.equal(calls[0].auth, 'Bearer t-test');       // the credential travels in a header
  const [row] = observations(cfg);
  assert.equal(row.observation, true);
  assert.equal(row.plan.level, 'L2');
  assert.ok(!JSON.stringify(row).includes('Bangkok'));  // hashes and numbers, never the owner's text
});

test('shadow: a message holding a secret never reaches the preflight', async () => {
  const cfg = config('shadow');
  const row = await intake.shadowTurn(cfg, { session: 'dsh/vm/s', turn: 1, step: 0, message: 'ma clé sk-abc123' });
  assert.deepEqual(paths(), ['/v1/privacy/classify']);
  assert.equal(row.skipped, 'local_only');
});

test('shadow: events are recorded, never sent', async () => {
  const cfg = config('shadow');
  const ctx = fakeCtx();
  events.apply(ctx, cfg);
  await ctx.handlers['agent/turn-stopping'][0]({ agent: agent(), turn: 2 });
  ctx.handlers['workspace/session-stop'][0]({ sessionId: 'session-1' });
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(paths(), []);
  assert.deepEqual(observations(cfg).map((r) => [r.type, r.observation]), [['turn.ended', true], ['session.ended', true]]);
});

test('native: one run, then the pack and skills injected as one tagged message', async () => {
  const cfg = config('native');
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'où en est le lot E2 ?')], turn: 1, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  const start = calls.find((c) => c.path === '/v1/runs/start');
  assert.equal(start.body.origin.session_id, 'dsh/vm/session-1');
  assert.match(start.body.dedupe_key, /^dsh\/vm\/session-1:1:0:[0-9a-f]{16}$/);
  const pack = calls.find((c) => c.path === '/preflight?inject=1');
  assert.equal(pack.body.run_id, currentRuns.get('dsh/vm/session-1').run_id);
  assert.equal(out.messages.length, 1);
  assert.equal(out.messages[0].source.kind, 'walter-intake');
  assert.equal(out.messages[0].content[0].text, '<walter-context>\nPACK\n\nSKILLS\n</walter-context>');
  const record = JSON.parse(readFileSync(join(cfg.runsDir, `${process.pid}.json`), 'utf8'));
  assert.equal(record.run_id, pack.body.run_id);
});

test('native: the same step replayed carries the same idempotency key; a new turn cancels the unfinished run', async () => {
  const cfg = config('native');
  const input = { session: 'dsh/vm/s2', turn: 4, step: 0, message: 'refais le point' };
  await intake.nativeTurn(cfg, input);
  const first = calls.filter((c) => c.path === '/v1/runs/start');
  await intake.nativeTurn(cfg, input);
  const starts = calls.filter((c) => c.path === '/v1/runs/start');
  assert.equal(first.length, 1);
  assert.equal(starts[0].body.dedupe_key, starts[1].body.dedupe_key);
  assert.equal(starts[1].body.cancel_run_id, null);           // a replay never cancels its own run
  await intake.nativeTurn(cfg, { ...input, turn: 5, message: 'autre chose' });
  const third = calls.filter((c) => c.path === '/v1/runs/start')[2];
  assert.ok(third.body.cancel_run_id);
});

test('native: a session opened by the Engine API files its runs under its channel and its parent run (E5)', async () => {
  const cfg = config('native');
  const meta = (globalThis[Symbol.for('walter.engine.sessionMeta')] ||= new Map());
  meta.set('s-deleg', { channel: 'machine', parent_run_id: 'run-parent-1' });
  await intake.nativeTurn(cfg, { session: 'dsh/vm/s-deleg', turn: 1, step: 0, message: '[Délégation Walter] Objectif : trouver la date' });
  const start = calls.filter((c) => c.path === '/v1/runs/start').at(-1);
  assert.equal(start.body.origin.channel, 'machine');
  assert.equal(start.body.parent_run_id, 'run-parent-1');
  await intake.nativeTurn(cfg, { session: 'dsh/vm/s-plain', turn: 1, step: 0, message: 'une question ordinaire du propriétaire' });
  const plain = calls.filter((c) => c.path === '/v1/runs/start').at(-1);
  assert.equal(plain.body.origin.channel, 'owner'); assert.equal(plain.body.parent_run_id, undefined);
  meta.set('s-named', { channel: 'machine', parent_run_id: null, model: { id: 'claude-opus-5-5', provider: 'venice' } });
  await intake.nativeTurn(cfg, { session: 'dsh/vm/s-named', turn: 1, step: 0, message: '[Délégation Walter] Objectif : x' });
  const named = calls.filter((c) => c.path === '/v1/runs/start').at(-1);
  assert.deepEqual(named.body.routing.requested, { model: 'claude-opus-5-5', provider: 'venice' });
  meta.delete('s-deleg'); meta.delete('s-named');
});

test('native: an in-process sub-agent turn is a machine run filed under its parent\'s current run (E5)', async () => {
  const cfg = config('native');
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const parent = agent();
  await ctx.handlers['agent/pre-step'][0]({ agent: parent, messages: [msg('user', 'lance deux sous-agents pour vérifier')], turn: 1, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  const parentRun = currentRuns.get('dsh/vm/session-1').run_id;
  const child = { session: { header: { id: 'child-7', parentSession: 'session-1', origin: 'subagent', delegationDepth: 1 } } };   // as the kernel writes it
  await ctx.handlers['agent/pre-step'][0]({ agent: child, messages: [msg('user', 'Calcule 17*23 et réponds le nombre.')], turn: 1, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  const start = calls.filter((c) => c.path === '/v1/runs/start').at(-1);
  assert.equal(start.body.origin.session_id, 'dsh/vm/child-7');
  assert.equal(start.body.origin.channel, 'machine');
  assert.equal(start.body.parent_run_id, parentRun);
});

test('native: no pack (failure or secret) → the legacy memory block, cloud-safe, with its header', async () => {
  const cfg = config('native');
  behaviour['/preflight?inject=1'] = (d, reply) => reply(500, {});
  const out = await intake.nativeTurn(cfg, { session: 'dsh/vm/s3', turn: 1, step: 0, message: 'que sais-tu de Sagora ?' });
  assert.match(out.text, /^<walter-context>\nMémoire W\.Alter/);
  assert.equal(calls.find((c) => c.path === '/v1/context').body.cloud_safe, true);
  calls.length = 0;
  await intake.nativeTurn(cfg, { session: 'dsh/vm/s3', turn: 2, step: 0, message: 'garde cette clé sk-zzz pour moi' });
  assert.ok(!paths().includes('/preflight?inject=1'));
});

test('native: every Walter source down → the step goes on with nothing injected', async () => {
  const cfg = config('native', { gateway: 'http://127.0.0.1:9', preflight: 'http://127.0.0.1:9', skills: 'http://127.0.0.1:9' });
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const downstream = { kind: 'enter', messages: [] };
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'bonjour, tu es là ?')], turn: 1, step: 0 },
    async () => downstream);
  assert.equal(out, downstream);
});

test('native: a turn end closes its run and emits turn.ended once per run; archive emits session.ended; unload does not', async () => {
  const cfg = config('native');
  currentRuns.set('dsh/vm/session-1', { run_id: 'run-x', turn: 1 });
  const ctx = fakeCtx();
  events.apply(ctx, cfg);
  await ctx.handlers['agent/turn-stopping'][0]({ agent: agent(), turn: 1 });
  assert.deepEqual(paths(), ['/v1/runs/end', '/v1/bus/emit']);
  assert.equal(calls[0].body.run_id, 'run-x');
  assert.equal(calls[1].body.dedupe_key, 'turn.ended/run-x');
  assert.equal(currentRuns.has('dsh/vm/session-1'), false);
  calls.length = 0;
  ctx.handlers['agent/disposed'][0]({ agent: agent() });
  ctx.handlers['workspace/session-stop'][0]({ sessionId: 'session-1' });
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(calls.map((c) => [c.path, c.body.type, c.body.payload.reason]), [['/v1/bus/emit', 'session.ended', 'archived']]);
});

test('delivery: a refusal by design is recorded as refused, never retried; a transmission defect is retried once', async () => {
  const cfg = config('native');
  let emits = 0;
  behaviour['/v1/bus/emit'] = (data, reply) => { emits += 1; reply(403, { detail: { refused: 'observation_not_on_production_bus' } }); };
  currentRuns.set('dsh/vm/r1', { run_id: 'run-r1', turn: 1 });
  await assert.rejects(events.turnEnded(cfg, 'dsh/vm/r1', 1));
  assert.equal(emits, 1);                                       // refused: no retry
  let [row] = observations(cfg).filter((r) => r.kind === 'delivery');
  assert.deepEqual(row.steps.emit, { outcome: 'refused', status: 403, refused: 'observation_not_on_production_bus', retried: false });

  const cfg2 = config('native');
  emits = 0;
  behaviour['/v1/bus/emit'] = (data, reply) => { emits += 1; return emits === 1 ? reply(503, {}) : reply(200, { id: 7, duplicate: false }); };
  currentRuns.set('dsh/vm/r2', { run_id: 'run-r2', turn: 1 });
  assert.equal(await events.turnEnded(cfg2, 'dsh/vm/r2', 1), 'run-r2');
  assert.equal(emits, 2);                                       // transport: one retry, same dedupe key
  [row] = observations(cfg2).filter((r) => r.kind === 'delivery');
  assert.deepEqual(row.steps.emit, { outcome: 'delivered', status: null, refused: null, retried: true });
  const keys = calls.filter((c) => c.path === '/v1/bus/emit' && c.body.subject === 'dsh/vm/r2').map((c) => c.body.dedupe_key);
  assert.deepEqual(keys, ['turn.ended/run-r2', 'turn.ended/run-r2']);
});

test('delivery: an unanswered gateway is a transport defect, not a refusal', async () => {
  const cfg = config('native', { gateway: 'http://127.0.0.1:9' });
  await assert.rejects(events.sessionEnded(cfg, 'dsh/vm/r3', 'archived'));
  const [row] = observations(cfg).filter((r) => r.kind === 'delivery');
  assert.equal(row.steps.emit.outcome, 'transport');
  assert.equal(row.steps.emit.retried, true);
});

test('native: a turn interrupted (idle without its stop boundary) closes its run cancelled; after an error, failed', async () => {
  const cfg = config('native');
  const ctx = fakeCtx();
  events.apply(ctx, cfg);
  currentRuns.set('dsh/vm/session-1', { run_id: 'run-c', turn: 4 });
  ctx.handlers['agent/status'][0]({ agent: agent(), status: 'idle' });
  await new Promise((r) => setTimeout(r, 30));
  const end = calls.find((c) => c.path === '/v1/runs/end');
  assert.equal(end.body.status, 'cancelled');
  assert.equal(calls.find((c) => c.path === '/v1/bus/emit').body.payload.status, 'cancelled');
  calls.length = 0;
  currentRuns.set('dsh/vm/session-1', { run_id: 'run-f', turn: 5 });
  ctx.handlers['agent/error'][0]({ agent: agent() });
  ctx.handlers['agent/status'][0]({ agent: agent(), status: 'idle' });
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(calls.find((c) => c.path === '/v1/runs/end').body.status, 'failed');
  calls.length = 0;
  ctx.handlers['agent/status'][0]({ agent: agent(), status: 'idle' });          // nothing open: nothing sent
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(paths(), []);
});

test('planRequest: a sub-agent mission says so (one tier lower), an owner message does not', () => {
  const cfg = { runtime: 'dsh' };
  assert.equal(intake.planRequest(cfg, 's', 'm', 'r', 1, 'machine').channel, 'machine');
  assert.equal('channel' in intake.planRequest(cfg, 's', 'm', 'r', 1, 'owner'), false);
});
