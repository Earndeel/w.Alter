// Tests of the engine's persistent Python kernel plugin (plugins/python) against a stand-in tool registry and job
// registry: persistence, engine tool calls (policy refusal, parallel vs exclusive), background jobs, delegation,
// interruption, restart from snapshot, and — as root — the real systemd bubble (secrets, writes, local network).
//   node --test /walter/core/engine/tests/python.test.mjs
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { apply, searchTools, clip, bubbleArgv, DEFAULTS } from '../plugins/python/index.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function harness({ sandbox = 'none', stateDir = mkdtempSync(join(tmpdir(), 'wpy-')) } = {}) {
  const registered = [], executed = [], appended = [], started = [], settled = [];
  const schemas = [
    { name: 'echo', description: 'Echo the arguments back', parameters: {} },
    { name: 'slow', description: 'An exclusive tool taking 150 ms', parameters: {} },
    { name: 'deny', description: 'Always refused by policy', parameters: {} },
    { name: 'subagent', description: 'Delegate a task to a subagent', parameters: { type: 'object', properties: { prompt: {}, run_in_background: {} } } },
    { name: 'mcp__walter__memory_search', description: 'Search the owner memory', parameters: { type: 'object' } },
    { name: 'python', description: 'this tool', parameters: {} },
  ];
  const jobs = {
    limit: Infinity,
    start(spec) {
      if (started.length >= this.limit) throw new Error('background job limit reached for this owner (limit: 1)');
      const chunks = [];
      const hooks = spec.run({ id: `python-${started.length + 1}`, append: (t) => chunks.push(t), updateProgress() {} });
      started.push({ spec, hooks, chunks });
      hooks.done.then((o) => settled.push(o));
      return `python-${started.length}`;
    },
  };
  const ctx = {
    tools: {
      register: (d) => registered.push(d),
      schemas: () => schemas,
      executionMode: (input) => ({ kind: ['echo', 'subagent'].includes(input.name) ? 'parallel' : 'exclusive' }),
      execute: async (input) => {
        executed.push(input);
        if (input.name === 'deny') return { isError: true, error: { message: 'WALTER_POLICY_DENIED: refused' }, content: [] };
        if (input.name === 'slow') await sleep(150);
        if (input.name === 'subagent') return { isError: false, value: `report for ${input.arguments.prompt}`, content: [] };
        return { isError: false, value: { got: input.arguments }, content: [{ type: 'text', text: 'x' }] };
      },
    },
    get: (n) => (n === 'jobs' ? jobs : undefined),
    on() {}, effect() {}, logger: { info() {}, warn() {} },
  };
  const plugin = apply(ctx, { stateDir, sandbox, idleMs: 60_000, interruptGraceMs: 3000 });
  const tool = registered.find((d) => d.name === 'python');
  const agent = { id: `sess-${Math.random().toString(36).slice(2)}`, session: { header: { cwd: '/tmp' }, append: (t) => appended.push(t) }, ctx: { effect() {} } };
  let n = 0;
  const call = (code, extra = {}) => {
    const ac = extra.controller || new AbortController();
    return tool.execute({ code, ...extra.args }, { agent, callId: `call-${++n}`, rootCallId: `call-${n}`, token: { t: n }, signal: ac.signal });
  };
  const close = async () => { await Promise.allSettled([...plugin.kernels.values()].map((k) => k.stop('test'))); rmSync(stateDir, { recursive: true, force: true }); };
  return { plugin, tool, call, executed, appended, started, settled, close, agent, stateDir, jobs };
}

test('helpers: search ranks name hits, clip keeps head and tail, bubble denies private networks', () => {
  const s = searchTools([{ name: 'memory_search', description: 'x' }, { name: 'other', description: 'about memory' }, { name: 'python', description: 'memory' }], 'memory');
  assert.deepEqual(s.map((x) => x.name), ['memory_search', 'other']);
  const c = clip('a'.repeat(100) + 'b'.repeat(100), 50);
  assert.ok(c.startsWith('aaa') && c.endsWith('bbb') && c.includes('omitted'));
  const argv = bubbleArgv({ ...DEFAULTS }, { unit: 'u', dir: '/d', uid: 993, gid: 985 }).join(' ');
  for (const p of ['User=993', 'ProtectSystem=strict', 'ProtectHome=yes', 'NoNewPrivileges=yes', '127.0.0.0/8', '169.254.0.0/16', '100.64.0.0/10', 'BindPaths=/d:/kernel', 'CapabilityBoundingSet=', '--setenv=PATH=/services/python/engine-python/bin:'])
    assert.ok(argv.includes(p), p);
});

test('persistent namespace, results, errors', async () => {
  const h = harness();
  try {
    assert.equal(await h.call('x = 41\nx + 1'), '→ 42');
    assert.match(await h.call('print("hi")\nx'), /hi\n→ 41/);
    assert.match(await h.call('1/0'), /ZeroDivisionError/);
    assert.equal(await h.call('x'), '→ 41');
  } finally { await h.close(); }
});

test('engine tools from Python: through the registry, policy refusals, logged as ptc dispatches', async () => {
  const h = harness();
  try {
    assert.match(await h.call('await tools.echo(a=1)'), /\{'got': \{'a': 1\}\}/);
    const e = h.executed.at(-1);
    assert.equal(e.name, 'echo'); assert.equal(e.agent, h.agent); assert.ok(e.parent); assert.match(e.callId, /^call-1:py:/);
    assert.ok(h.appended.includes('tool/ptc-dispatch-start') && h.appended.includes('tool/ptc-dispatch'));
    assert.match(await h.call('try:\n    await tools.deny()\nexcept ToolError as e:\n    r = str(e)\nr'), /WALTER_POLICY_DENIED/);
    assert.match(await h.call('[t["name"] for t in await tools.search("memory")]'), /mcp__walter__memory_search/);
    assert.match(await h.call('(await tools.describe("mcp__walter__memory_search"))["parameters"]'), /object/);
    assert.match(await h.call('await tools.python(code="1")'), /cannot call itself/);
  } finally { await h.close(); }
});

test('parallel tools overlap, exclusive tools take turns', async () => {
  const h = harness();
  try {
    await h.call('import time');
    const par = await h.call('t=time.time()\nawait asyncio.gather(*(tools.echo(i=i) for i in range(4)))\nround(time.time()-t, 2)');
    const exc = await h.call('t=time.time()\nawait asyncio.gather(*(tools.slow(i=i) for i in range(3)))\nround(time.time()-t, 2)');
    assert.ok(Number(par.slice(2)) < 0.3, par);
    assert.ok(Number(exc.slice(2)) >= 0.44, exc);
  } finally { await h.close(); }
});

test('background work is an engine job owned by the session, settled with its result', async () => {
  const h = harness();
  try {
    const out = await h.call('j = bash("sleep 0.3; echo finished", background=True)\nj');
    assert.match(out, /<Job python-1 running/);                 // the engine's id, the one job_output takes
    assert.match(out, /\[background: python-1 /);
    assert.equal(h.started.length, 1);
    assert.equal(h.started[0].spec.owner, h.agent.id);
    assert.equal(h.started[0].spec.kind, 'python');
    for (let i = 0; i < 50 && !h.settled.length; i++) await sleep(50);
    assert.equal(h.settled[0]?.status, 'completed');
    assert.match(h.settled[0].result, /finished/);
    h.jobs.limit = 1;                                            // the engine refuses a job: it never runs unseen
    assert.match(await h.call('bash("sleep 5", background=True)'), /RuntimeError: background job refused by the engine: background job limit/);
  } finally { await h.close(); }
});

test('delegation: sub-agents on a Router poste, in parallel', async () => {
  const h = harness();
  try {
    const out = await h.call('await delegate_all(["one", {"prompt": "two", "poste": "code"}])');
    assert.match(out, /report for one/); assert.match(out, /report for two/);
    const sub = h.executed.filter((e) => e.name === 'subagent');
    assert.equal(sub.length, 2);
    assert.equal(sub[1].arguments.provider, 'walter'); assert.equal(sub[1].arguments.model, 'code');
    assert.equal(sub[0].arguments.run_in_background, false);                 // waits for the result by default
  } finally { await h.close(); }
});

test('the call signal interrupts a cell; the kernel keeps its state', async () => {
  const h = harness();
  try {
    await h.call('kept = "yes"');
    const ac = new AbortController();
    const p = h.call('await asyncio.sleep(60)', { controller: ac });
    await sleep(400); ac.abort('owner stopped');
    assert.match(await p, /\[interrupted\]/);
    const sync = h.call('import time\nwhile True: time.sleep(0.01)', { args: { timeout_s: 0.5 } });
    assert.match(await sync, /interrupted: the cell exceeded/);
    assert.equal(await h.call('kept'), "→ 'yes'");
  } finally { await h.close(); }
});

test('a killed kernel comes back from its last snapshot', async () => {
  const h = harness();
  try {
    await h.call('import json\nstate = {"step": 3}\ndef nxt():\n    state["step"] += 1\n    return state["step"]');
    await sleep(300);                                   // the snapshot after the cell
    const k = [...h.plugin.kernels.values()][0];
    await k.kill('test crash');
    for (let i = 0; i < 40 && h.plugin.kernels.size; i++) await sleep(50);
    const out = await h.call('(nxt(), json.dumps(state))');
    assert.match(out, /kernel restarted: \d+ variables restored/);
    assert.match(out, /→ \(4, '\{"step": 4\}'\)/);
  } finally { await h.close(); }
});

test('an engine restart stops running background jobs; the next cell says which ones', async () => {
  const h = harness();
  try {
    await h.call('j = bash("sleep 30", background=True)');
    const k = [...h.plugin.kernels.values()][0];
    await k.stop('engine unloading');                               // what the engine's dispose does on a restart
    for (let i = 0; i < 40 && h.plugin.kernels.size; i++) await sleep(50);
    const out = await h.call('1 + 1');
    assert.match(out, /background jobs stopped by an engine restart: python-1 bash: sleep 30/);
    assert.doesNotMatch(await h.call('2'), /stopped by an engine restart/);   // said once
    await h.call('j2 = bash("sleep 0.2", background=True)');                  // a job that ends normally leaves no trace
    for (let i = 0; i < 40 && h.settled.length < 2; i++) await sleep(50);
    const k2 = [...h.plugin.kernels.values()][0];
    await k2.stop('engine unloading');
    for (let i = 0; i < 40 && h.plugin.kernels.size; i++) await sleep(50);
    assert.doesNotMatch(await h.call('3'), /stopped by an engine restart/);
  } finally { await h.close(); }
});

const root = process.getuid?.() === 0;
test('the bubble: unprivileged, no secrets, read-only host, no local network, tools still reachable', { skip: !root && 'needs root (systemd-run)' }, async () => {
  const stateDir = mkdtempSync(join('/user/Lucas/state/core/engine', 'python-test-'));
  const h = harness({ sandbox: 'systemd', stateDir });
  try {
    const out = await h.call([
      'import os, socket',
      'def probe(p):',
      '    try:',
      '        open(p).read(1); return "READ"',
      '    except Exception as e: return type(e).__name__',
      'def conn(h, p):',
      '    s = socket.socket(); s.settimeout(1.5)',
      '    try: s.connect((h, p)); return "OPEN"',
      '    except Exception as e: return type(e).__name__',
      '    finally: s.close()',
      'open("ws.txt", "w").write("ok")',
      'r = {"uid": os.getuid(), "pgpass": probe("/root/.pgpass"), "instance": probe("/user/Lucas/instance.toml"),',
      '     "memory_env": probe("/walter/cognition/memory/.env"), "vision": probe("/walter/docs/VISION.md"),',
      '     "write_walter": probe_w if (probe_w := None) else None, "pg": conn("127.0.0.1", 5433), "metadata": conn("169.254.169.254", 80)}',
      'try:',
      '    open("/walter/x", "w"); r["write_walter"] = "WROTE"',
      'except Exception as e: r["write_walter"] = type(e).__name__',
      'r["tool"] = await tools.echo(z=1)',
      'r',
    ].join('\n'));
    assert.doesNotMatch(out, /'uid': 0\b/);
    for (const k of ['pgpass', 'instance', 'memory_env']) assert.match(out, new RegExp(`'${k}': 'PermissionError'`), out);
    assert.match(out, /'vision': 'READ'/);
    assert.match(out, /'write_walter': 'OSError'/);
    assert.doesNotMatch(out, /'OPEN'/);
    assert.match(out, /'tool': \{'got': \{'z': 1\}\}/);
  } finally { await h.close(); }
});
