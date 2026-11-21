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

test('budget: an understood owner request sets the turn\'s ceilings and one checkpoint; an unread one keeps the general ceilings', async () => {
  const { turnPlans } = await import('../plugins/shared.mjs');
  const cfg = { maxSteps: 80, graceSteps: 3, maxTurnMs: 2_700_000, graceMs: 300_000,
    levels: { L1: { checkpoint: 6, maxSteps: 16, maxTurnMs: 480_000 } } };
  const owner = { level: 'L1', channel: 'owner' };
  assert.equal(budget.verdict(cfg, { step: 5, startedAt: 0, now: 1, plan: owner }), 'go');
  assert.equal(budget.verdict(cfg, { step: 6, startedAt: 0, now: 1, plan: owner }), 'checkpoint');
  assert.equal(budget.verdict(cfg, { step: 16, startedAt: 0, now: 1, plan: owner }), 'conclude');
  assert.equal(budget.verdict(cfg, { step: 19, startedAt: 0, now: 1, plan: owner }), 'stop');
  assert.equal(budget.verdict(cfg, { step: 2, startedAt: 0, now: 481_000, plan: owner }), 'conclude');
  for (const plan of [null, { level: 'L1', channel: 'owner', degraded: true }, { level: 'L1', channel: 'machine' }, { level: 'L9', channel: 'owner' }])
    assert.equal(budget.verdict(cfg, { step: 40, startedAt: 0, now: 1, plan }), 'go');     // never cut short on a guess
  // the ceilings follow the EFFORT Context states, not the context level: a self-contained request (L0) that is work
  // to carry out is not cut at the light ceilings
  const levels = { L0: { checkpoint: 4, maxSteps: 12, maxTurnMs: 300_000 }, L4: { checkpoint: 36, maxSteps: 80, maxTurnMs: 2_700_000 } };
  const work = { level: 'L0', effort: 'L4', channel: 'owner' }, light = { level: 'L0', effort: 'L0', channel: 'owner' };
  assert.equal(budget.ceilings({ ...cfg, levels }, work).level, 'L4');
  assert.equal(budget.verdict({ ...cfg, levels }, { step: 14, startedAt: 0, now: 640_000, plan: work }), 'go');
  assert.equal(budget.verdict({ ...cfg, levels }, { step: 14, startedAt: 0, now: 640_000, plan: light }), 'stop');
  assert.equal(budget.ceilings({ ...cfg, levels }, { level: 'L0', channel: 'owner' }).level, 'L0');   // rule-made plan: its level
  const handlers = [];
  budget.apply({ on: (n, fn) => handlers.push(fn) }, cfg);
  const a = { session: { header: { id: 'b1' } } };
  const enter = async () => ({ kind: 'enter', messages: [] });
  turnPlans.set('dsh/vm/b1', { ...owner, turn: 1 });
  assert.equal((await handlers[0]({ agent: a, turn: 1, step: 5 }, enter)).messages.length, 0);
  const checked = await handlers[0]({ agent: a, turn: 1, step: 6 }, enter);
  assert.match(checked.messages.at(-1).content[0].text, /^Point d'étape/);
  assert.equal((await handlers[0]({ agent: a, turn: 1, step: 7 }, enter)).messages.length, 0);     // said once
  assert.match((await handlers[0]({ agent: a, turn: 1, step: 16 }, enter)).messages.at(-1).content[0].text, /^Budget de ce tour atteint/);
  assert.equal((await handlers[0]({ agent: a, turn: 1, step: 19 }, enter)).kind, 'reject');
  assert.equal(turnPlans.get('dsh/vm/b1').stopped, 'budget');
  assert.equal((await handlers[0]({ agent: a, turn: 2, step: 30 }, enter)).messages.length, 0);    // the plan of another turn does not apply
  turnPlans.delete('dsh/vm/b1');
});
