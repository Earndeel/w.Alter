// Lot E3: the engine's policy plugin — guard (never), pre-execute (preset, child, disclosure), kernel still decides.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, writeFileSync, readdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import * as policy from '../plugins/policy/index.mjs';

let disclosure = { action: 'allow', reason: '' };
const seen = [];
const server = createServer((req, res) => {
  let body = ''; req.on('data', (c) => { body += c; });
  req.on('end', () => {
    seen.push({ path: req.url, body: JSON.parse(body || '{}') });
    if (disclosure === 'down') { res.writeHead(503); return res.end('{}'); }
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(disclosure));
  });
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
after(() => server.close());
const dir = mkdtempSync(join(tmpdir(), 'walter-policy-'));
const tokenFile = join(dir, '.env'); writeFileSync(tokenFile, 'WALTER_MEMORY_GATEWAY_TOKEN=t\n');

function mount(extra = {}) {
  const guards = [], pre = [];
  const ctx = { tools: { guard: (g) => guards.push(g) }, on: (n, fn) => { if (n === 'tools/pre-execute') pre.push(fn); }, logger: { warn() {} } };
  const stateDir = join(dir, `s-${Math.random()}`);
  policy.apply(ctx, { interface: 'web', gateway: `http://127.0.0.1:${server.address().port}`, tokenFile, stateDir, ...extra });
  const run = async (exec, kernel = { kind: 'allow' }) => {
    const reason = guards.map((g) => g(exec)).find(Boolean);
    const decided = await pre[0](exec, async () => kernel);
    return { guard: reason, decided };
  };
  return { run, stateDir };
}
const agent = (iface, depth = 0) => {
  let a = { session: { header: { id: 'root', walter: iface ? { interface: iface } : undefined } } };
  for (let i = 0; i < depth; i += 1) a = { parentAgent: a, session: { header: { id: `c${i}` } } };
  return a;
};

test('a secret file: the guard refuses, so no listener can grant it back; the refusal is journaled without the arguments', async () => {
  const { run, stateDir } = mount();
  const out = await run({ name: 'bash', arguments: { command: 'cat /root/.pgpass' }, agent: agent() });
  assert.match(out.guard, /secrets/);
  assert.equal(out.decided.kind, 'deny');
  const rows = readdirSync(stateDir).flatMap((f) => readFileSync(join(stateDir, f), 'utf8').trim().split('\n').map((l) => JSON.parse(l)));
  assert.ok(rows.every((r) => !JSON.stringify(r).includes('pgpass') || r.rule.includes('pgpass')));
  assert.ok(!JSON.stringify(rows).includes('cat /root'));
});

test('web: ordinary work passes untouched and the kernel keeps its say', async () => {
  const { run } = mount();
  assert.deepEqual((await run({ name: 'bash', arguments: { command: 'ls /walter' }, agent: agent() })).decided, { kind: 'allow' });
  assert.deepEqual((await run({ name: 'bash', arguments: { command: 'rm -rf /etc' }, agent: agent() }, { kind: 'ask', reason: 'sandbox' })).decided,
    { kind: 'ask', reason: 'sandbox' });
});

test('a door asks where its preset says so (Telegram acting as Monsieur), a child under a web root too', async () => {
  const { run } = mount();
  const tg = await run({ name: 'mcp__walter__browser_session', arguments: { site: 'linkedin' }, agent: agent('telegram') });
  assert.equal(tg.decided.kind, 'ask');
  const child = await run({ name: 'mcp__walter__computer_use', arguments: {}, agent: agent('web', 1) });
  assert.equal(child.decided.kind, 'ask');
  const grandchild = await run({ name: 'subagent', arguments: {}, agent: agent('web', 3) });
  assert.equal(grandchild.decided.kind, 'deny');
});

test('outgoing messages: disclosure block ⇒ deny, ask ⇒ ask, check unavailable ⇒ ask (never sent blind)', async () => {
  const { run } = mount();
  const exec = { name: 'mcp__beeper__send_message', arguments: { to: 'x', text: 'bonjour' }, agent: agent('web') };
  disclosure = { action: 'block', reason: 'Walter Memory bloque cet envoi' };
  assert.equal((await run(exec)).decided.kind, 'deny');
  disclosure = { action: 'ask', reason: 'Accord de Monsieur requis' };
  assert.equal((await run(exec)).decided.kind, 'ask');
  disclosure = 'down';
  assert.equal((await run(exec)).decided.kind, 'ask');
  disclosure = { action: 'allow', reason: '' };
  assert.equal((await run(exec)).decided.kind, 'allow');
  assert.equal(seen.at(-1).body.tool, 'mcp__beeper__send_message');
});

test('an unreadable policy: every call asks (fail closed without an answerer)', async () => {
  const { run } = mount({ policyPath: join(dir, 'missing.json') });
  assert.equal((await run({ name: 'read', arguments: { path: '/tmp/x' }, agent: agent() })).decided.kind, 'ask');
});

import * as budget from '../plugins/budget/index.mjs';

test('budget: go, then conclude once at the ceiling, then stop after the grace', async () => {
  const cfg = { maxSteps: 3, graceSteps: 2, maxTurnMs: 60_000, graceMs: 10_000 };
  assert.equal(budget.verdict(cfg, { step: 2, startedAt: 0, now: 1 }), 'go');
  assert.equal(budget.verdict(cfg, { step: 3, startedAt: 0, now: 1 }), 'conclude');
  assert.equal(budget.verdict(cfg, { step: 5, startedAt: 0, now: 1 }), 'stop');
  assert.equal(budget.verdict(cfg, { step: 0, startedAt: 0, now: 61_000 }), 'conclude');
  assert.equal(budget.verdict(cfg, { step: 0, startedAt: 0, now: 71_000 }), 'stop');
  const handlers = [];
  budget.apply({ on: (n, fn) => handlers.push(fn) }, { maxSteps: 1, graceSteps: 1 });
  const a = {};
  const enter = async () => ({ kind: 'enter', messages: [] });
  assert.equal((await handlers[0]({ agent: a, turn: 1, step: 0 }, enter)).messages.length, 0);
  const told = await handlers[0]({ agent: a, turn: 1, step: 1 }, enter);
  assert.equal(told.messages.at(-1).source.kind, 'walter-budget');
  assert.equal((await handlers[0]({ agent: a, turn: 1, step: 2 }, enter)).kind, 'reject');
  assert.equal((await handlers[0]({ agent: a, turn: 2, step: 0 }, enter)).messages.length, 0);   // a new turn starts afresh
});
