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
import { currentRuns, lastExchange, ownerText, trackRun, turnPlans, turnStats } from '../plugins/shared.mjs';

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
const observations = (cfg) => readdirSync(cfg.stateDir).filter((f) => f.endsWith('.jsonl')).flatMap((f) =>
  readFileSync(join(cfg.stateDir, f), 'utf8').trim().split('\n').map((l) => JSON.parse(l)));

beforeEach(() => { calls.length = 0; behaviour = {}; currentRuns.clear(); turnPlans.clear(); });

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

test('native: every Walter source down → the step goes on, and the model is told its context is degraded', async () => {
  const cfg = config('native', { gateway: 'http://127.0.0.1:9', preflight: 'http://127.0.0.1:9', skills: 'http://127.0.0.1:9' });
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'bonjour, tu es là ?')], turn: 1, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  assert.equal(out.kind, 'enter');
  assert.equal(out.messages.length, 1);                          // never a silent fallback (decision A2)
  assert.match(out.messages[0].content[0].text, /^<walter-context>\nContexte dégradé/);
  assert.equal(out.messages[0].source.degraded, true);
  assert.equal(observations(cfg).find((r) => r.kind === 'intake').context_source, 'legacy_degraded');
});

test('native: preflight down, Memory up → the default memory block, announced as degraded, and context.degraded on the bus', async () => {
  const { settings } = await import('../plugins/shared.mjs');
  const cfg = settings(config('native', { preflight: 'http://127.0.0.1:9' }));
  const out = await intake.nativeTurn(cfg, { session: 'dsh/vm/d1', turn: 1, step: 0, message: 'où en est le dossier ?' });
  assert.match(out.text, /^<walter-context>\nContexte dégradé[^\n]+\n\n/);
  assert.ok(out.text.includes('souvenir daté'));
  assert.deepEqual({ degraded: out.plan.degraded, level: out.plan.level }, { degraded: true, level: null });
  await new Promise((r) => setTimeout(r, 30));
  const emit = calls.find((c) => c.path === '/v1/bus/emit');
  assert.equal(emit.body.type, 'context.degraded');
  assert.equal(emit.body.payload.stage, 'preflight_unreachable');
  assert.ok(!JSON.stringify(emit.body).includes('dossier'));     // a signal, never the owner's words
});

test('native: the preflight\'s own degraded plan is carried as such (source, plan, pack message)', async () => {
  behaviour['/preflight?inject=1'] = (data, reply) => reply(200, { degraded: true, text: 'PACK',
    plan: { level: 'L3', act: 'question', thread: { id: 'th-9' }, decision: { degraded: true } } });
  const cfg = config('native');
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'et pour demain ?')], turn: 2, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  assert.deepEqual(out.messages[0].source, { kind: 'walter-intake', thread: 'th-9', act: 'question', level: 'L3', degraded: true });
  assert.equal(observations(cfg).find((r) => r.kind === 'intake').context_source, 'pack_degraded');
  assert.equal(turnPlans.get('dsh/vm/session-1').degraded, true);
});

// A session journal as the kernel exposes it (eventAt, seq), numbers and structure only.
function journal(events) {
  return { header: { id: 'session-1' }, seq: events.length, eventAt: (i) => events[i] };
}
const ev = (type, data = {}, extra = {}) => ({ type, data, time: 1_000, surfaceOp: null, ...extra });
const said = (kind, text, source = {}) => ev('user/message', { role: 'user', source: { kind, ...source }, content: [{ type: 'text', text }] },
  { surfaceOp: 'append' });
const answered = (text) => ev('assistant/message', { message: { role: 'assistant', content: [{ type: 'text', text }] } }, { surfaceOp: 'append' });

test('previous exchange: read from the journal of the last completed turn, with the thread its pack carried', () => {
  const session = journal([
    ev('turn/start', { turn: 1 }), said('user', 'premier sujet'), answered('réponse 1'), ev('turn/end', { turn: 1 }, { time: 2_000 }),
    ev('turn/start', { turn: 2 }), said('user', 'peux-tu vérifier le devis ?'), said('walter-intake', '<walter-context>…', { thread: 'th-2' }),
    answered('je regarde'), ev('tool/call', { name: 'x' }), answered('Le devis est conforme.'), ev('turn/end', { turn: 2 }, { time: 60_000 }),
    ev('turn/start', { turn: 3 }),
  ]);
  assert.deepEqual(lastExchange(session, 90_000), { message: 'peux-tu vérifier le devis ?', answer: 'Le devis est conforme.', age_s: 30, thread_id: 'th-2' });
  assert.equal(lastExchange(journal([ev('turn/start', { turn: 1 })])), null);     // nothing completed yet
});

test('native: the previous exchange, the door and the request id reach the preflight and the run', async () => {
  const { sessionMeta } = await import('../../interfaces/api/bindings.mjs');
  sessionMeta().set('session-1', { channel: 'owner', parent_run_id: null, model: null, interface: 'telegram', engine_session: 'telegram/test/42' });
  const cfg = config('native');
  const ctx = fakeCtx();
  intake.apply(ctx, cfg);
  const a = { session: journal([ev('turn/start', { turn: 1 }), said('user', 'bonjour'), answered('Bonjour.'), ev('turn/end', { turn: 1 }, { time: Date.now() - 5_000 }),
    ev('turn/start', { turn: 2 })]) };
  const owner = { ...msg('user', 'et ensuite ?'), source: { kind: 'user', rpcId: 'req-77' } };
  await ctx.handlers['agent/pre-step'][0]({ agent: a, messages: [owner], turn: 2, step: 0 }, async () => ({ kind: 'enter', messages: [] }));
  sessionMeta().delete('session-1');
  const start = calls.find((c) => c.path === '/v1/runs/start');
  assert.deepEqual(start.body.origin, { channel: 'owner', runtime: 'dsh', session_id: 'dsh/vm/session-1', interface: 'telegram',
    engine_session: 'telegram/test/42', request_id: 'req-77' });
  const pack = calls.find((c) => c.path === '/preflight?inject=1');
  assert.equal(pack.body.previous.message, 'bonjour');
  assert.equal(pack.body.previous.answer, 'Bonjour.');
  assert.ok(pack.body.previous.age_s >= 5 && pack.body.previous.age_s < 60);
});

test('native: Context decides the window before the message enters, with the thread the preflight found; a failure is measured, never fatal', async () => {
  behaviour['/preflight?inject=1'] = (data, reply) => reply(200, { text: 'PACK', plan: { level: 'L2', act: 'question', thread: { id: 'th-5' } } });
  const cfg = config('native');
  const order = [];
  const engine = { window: async (a, opts) => { order.push(['window', opts.plan]); return { applied: true, reason: 'cold_cache', warm: false,
    turns: { verbatim: 0, full: 1, brief: 2, omitted: 0, leaving: 3 }, tokens: { before: 45000, after: 600, gain: 44400, threshold: 1000 }, measured_tokens: 52000 }; } };
  const ctx = fakeCtx();
  globalThis[Symbol.for('walter.context.window')] = (a, opts, signal) => engine.window(a, opts, signal);
  intake.apply(ctx, cfg);
  const out = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'on reprend le devis')], turn: 3, step: 0 },
    async () => { order.push(['next']); return { kind: 'enter', messages: [] }; });
  assert.deepEqual(order, [['window', { thread: 'th-5' }], ['next']]);
  assert.equal(out.messages[0].source.thread, 'th-5');
  const row = observations(cfg).find((r) => r.kind === 'window');
  assert.deepEqual([row.applied, row.reason, row.tokens.gain], [true, 'cold_cache', 44400]);
  engine.window = async () => { throw new Error('bridge down'); };
  const again = await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'encore')], turn: 4, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  assert.equal(again.messages.length, 1);                        // the turn goes on
  assert.equal(observations(cfg).filter((r) => r.kind === 'window').at(-1).reason, 'error');
  delete globalThis[Symbol.for('walter.context.window')];
  await ctx.handlers['agent/pre-step'][0]({ agent: agent(), messages: [msg('user', 'sans contexte')], turn: 5, step: 0 },
    async () => ({ kind: 'enter', messages: [] }));
  assert.equal(observations(cfg).filter((r) => r.kind === 'window').at(-1).reason, 'no_entry');   // visible, never silent
});

test('native: the end of a turn says how it went (status, numbers, error) on the run', async () => {
  const cfg = config('native');
  const ctx = fakeCtx();
  events.apply(ctx, cfg);
  const session = journal([ev('turn/start', { turn: 1 }), ev('step/start'), ev('tool/call'), ev('tool/result', { message: { isError: true } }, { surfaceOp: 'append' }),
    ev('step/start'), ev('tool/call'), ev('tool/result', { message: { isError: false } }, { surfaceOp: 'append' }), ev('step/start')]);
  assert.deepEqual(turnStats(session), { steps: 3, tool_calls: 2, tool_errors: 1 });
  currentRuns.set('dsh/vm/session-1', { run_id: 'run-o', turn: 1 });
  await ctx.handlers['agent/turn-stopping'][0]({ agent: { session }, turn: 1 });
  let end = calls.find((c) => c.path === '/v1/runs/end');
  assert.deepEqual(end.body.outcome, { status: 'ok', steps: 3, tool_calls: 2, tool_errors: 1 });
  calls.length = 0;
  currentRuns.set('dsh/vm/session-1', { run_id: 'run-p', turn: 2 });
  const failure = Object.assign(new Error('upstream 529 overloaded'), { status: 529 });
  ctx.handlers['agent/error'][0]({ agent: { session }, error: failure });
  ctx.handlers['agent/status'][0]({ agent: { session }, status: 'idle' });
  await new Promise((r) => setTimeout(r, 30));
  end = calls.find((c) => c.path === '/v1/runs/end');
  assert.equal(end.body.status, 'failed');
  assert.deepEqual(end.body.outcome.error, { kind: 'Error', message: 'upstream 529 overloaded' });
  assert.equal(end.body.outcome.status, 'failed');
});

test('native: runs left open by an engine process that died are closed as interrupted at the next start, once', async () => {
  const cfg = config('native');
  const { settings } = await import('../plugins/shared.mjs');
  const real = settings(cfg);
  trackRun(real, 'dsh/vm/alive', { run_id: 'run-alive', turn: 1 });          // this process: still running
  const file = join(cfg.stateDir, 'open-runs.json');
  const rows = JSON.parse(readFileSync(file, 'utf8'));
  rows['dsh/vm/dead'] = { run_id: 'run-dead', turn: 7, pid: 2 ** 22 + 12345, at: 1 };   // no such process
  writeFileSync(file, JSON.stringify(rows));
  assert.deepEqual(await events.closeOrphans(real), ['run-dead']);
  const end = calls.find((c) => c.path === '/v1/runs/end');
  assert.deepEqual([end.body.run_id, end.body.status, end.body.outcome.status, end.body.outcome.error.kind],
    ['run-dead', 'cancelled', 'interrupted', 'engine_restart']);
  assert.deepEqual(await events.closeOrphans(real), []);                       // once
  assert.deepEqual(Object.keys(JSON.parse(readFileSync(file, 'utf8'))), ['dsh/vm/alive']);
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
  // the engine says how long it waits: the preflight answers inside it (13/11, three plans lost to a late answer)
  assert.equal(intake.planRequest({ runtime: 'dsh', preflightTimeoutMs: 7000 }, 's', 'm').answer_within_ms, 7000);
});
