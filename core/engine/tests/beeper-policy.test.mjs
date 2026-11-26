// Native Beeper is judged by the existing Engine policy plugin. Fake disclosure endpoint, no real send.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.env.WALTER_BEEPER_TEST_CORE || new URL('../..', import.meta.url).pathname;
const { judge } = await import(pathToFileURL(join(root, 'engine/plugins/policy/index.mjs')));
const { load } = await import(pathToFileURL(join(root, 'security/policy.mjs')));
const policy = load(process.env.WALTER_BEEPER_TEST_POLICY || undefined);
let action = 'allow', calls = 0;
const srv = createServer((req, res) => {
  let data = ''; req.on('data', (p) => { data += p; });
  req.on('end', () => {
    calls += 1;
    const body = JSON.parse(data);
    assert.equal(body.tool, 'mcp__walter__beeper_send_message');
    assert.equal(body.args.chat_id, '!fixture:test');
    if (action === 'down') { res.writeHead(503); return res.end('{}'); }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ action }));
  });
});
await new Promise((done) => srv.listen(0, '127.0.0.1', done));
after(() => srv.close());
const dir = mkdtempSync(join(tmpdir(), 'beeper-policy-test-'));
const tokenFile = join(dir, 'fake.env');
writeFileSync(tokenFile, 'WALTER_MEMORY_GATEWAY_TOKEN=fixture\n');
const cfg = { gateway: `http://127.0.0.1:${srv.address().port}`, tokenFile, interface: 'web', home: '/tmp' };
function agent(iface, depth = 0) {
  let a = { session: { header: { id: 'fixture', walter: { interface: iface } } } };
  for (let i = 0; i < depth; i++) a = { parentAgent: a, session: { header: { id: 'child' } } };
  return a;
}
function exec(iface = 'web', depth = 0, nested = false) {
  const args = { chat_id: '!fixture:test', text: 'fixture' };
  return { name: nested ? 'mcp__walter__walter_call' : 'mcp__walter__beeper_send_message',
    arguments: nested ? { tool: 'beeper_send_message', arguments: args } : args, agent: agent(iface, depth) };
}
test('Beeper send uses real disclosure checks: allow, ask, block, unavailable', async () => {
  for (const [a, decision] of [['allow', 'allow'], ['ask', 'ask'], ['block', 'deny'], ['down', 'ask']]) {
    action = a;
    assert.equal((await judge(cfg, policy, exec())).decision, decision);
    assert.equal((await judge(cfg, policy, exec('web', 0, true))).decision, decision);
  }
});
test('Beeper sends from API ask; command and child refuse, including generic walter_call', async () => {
  const before = calls;
  for (const [iface, depth, expected] of [['api', 0, 'ask'], ['command', 0, 'deny'], ['web', 1, 'deny']]) {
    for (const nested of [false, true]) assert.equal((await judge(cfg, policy, exec(iface, depth, nested))).decision, expected);
  }
  assert.equal(calls, before);
});
