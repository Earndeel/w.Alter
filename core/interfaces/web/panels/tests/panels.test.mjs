// Panels of the web interface: a page served by another Walter module, shown in the sidebar and the main area, behind
// the web interface's own sign-in. Upstream stand-in: a local HTTP server; sign-in stand-in: an admit() function.
import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { apply, checkPanels, proxyHandler } from '../index.mjs';

function listen(handler) {
  return new Promise((ok) => { const s = http.createServer(handler); s.listen(0, '127.0.0.1', () => ok(s)); });
}
const url = (s) => `http://127.0.0.1:${s.address().port}`;
async function withProxy(admit, upstreamHandler, fn) {
  const up = await listen(upstreamHandler);
  const front = await listen(proxyHandler({ path: '/devboard', upstream: url(up), admit }));
  try { await fn(url(front)); } finally { front.close(); up.close(); }
}
const ok = () => undefined;

test('a signed-in request reaches the module, prefix removed, query kept', async () => {
  const seen = [];
  await withProxy(ok, (req, res) => { seen.push(req.url); res.setHeader('content-type', 'application/json'); res.end('{"n":1}'); },
    async (base) => {
      const r = await fetch(`${base}/devboard/api/cards?group=status`);
      assert.equal(r.status, 200);
      assert.deepEqual(await r.json(), { n: 1 });
      assert.deepEqual(seen, ['/api/cards?group=status']);
    });
});

test('without the sign-in cookie nothing reaches the module', async () => {
  let hits = 0;
  await withProxy(() => 401, (req, res) => { hits++; res.end('x'); }, async (base) => {
    const r = await fetch(`${base}/devboard/api/cards`);
    assert.equal(r.status, 401);
    assert.equal(hits, 0);
  });
});

test('the bare prefix redirects to the folder so relative assets resolve', async () => {
  await withProxy(ok, (req, res) => res.end('x'), async (base) => {
    const r = await fetch(`${base}/devboard?x=1`, { redirect: 'manual' });
    assert.equal(r.status, 308);
    assert.equal(r.headers.get('location'), '/devboard/?x=1');
  });
});

test('only reads are relayed: the panel is a view', async () => {
  let hits = 0;
  await withProxy(ok, (req, res) => { hits++; res.end('x'); }, async (base) => {
    const r = await fetch(`${base}/devboard/api/cards`, { method: 'POST', body: '{}' });
    assert.equal(r.status, 405);
    assert.equal(hits, 0);
  });
});

test('the sign-in cookie of the web interface is never sent to the module', async () => {
  const cookies = [];
  await withProxy(ok, (req, res) => { cookies.push(req.headers.cookie); res.end('x'); }, async (base) => {
    await fetch(`${base}/devboard/`, { headers: { cookie: 'dsh-auth-x=secret' } });
    assert.deepEqual(cookies, [undefined]);
  });
});

test('a live stream is relayed as it comes', async () => {
  await withProxy(ok, (req, res) => {
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    res.write('event: hello\ndata: 1\n\n');
  }, async (base) => {
    const r = await fetch(`${base}/devboard/api/stream`);
    const reader = r.body.getReader();
    const { value } = await reader.read();
    assert.match(new TextDecoder().decode(value), /event: hello/);
    await reader.cancel();
  });
});

test('a stopped module answers 502, not a hang', async () => {
  const front = await listen(proxyHandler({ path: '/devboard', upstream: 'http://127.0.0.1:1', admit: ok }));
  try { assert.equal((await fetch(`${url(front)}/devboard/`)).status, 502); } finally { front.close(); }
});

test('panel settings are checked', () => {
  assert.throws(() => checkPanels([{ id: 'x', label: 'X', path: 'devboard', upstream: 'http://127.0.0.1:1' }]), /path/);
  assert.throws(() => checkPanels([{ id: 'x', label: 'X', path: '/api', upstream: 'http://127.0.0.1:1' }]), /reserved/);
  assert.throws(() => checkPanels([{ id: 'x', label: 'X', path: '/d', upstream: 'ftp://h' }]), /upstream/);
  assert.throws(() => checkPanels([{ id: 'conversation', label: 'X', path: '/d', upstream: 'http://h' }]), /id/);
  assert.deepEqual(checkPanels([]), []);
});

test('apply mounts one route per panel and publishes id, label and path only', () => {
  const routes = [], table = [];
  const web = { webServer: { register: (r) => { routes.push(r); return () => {}; } },
    connection: { requestRejection: () => undefined }, effect: (f) => f(),
    on: (ev, f) => { assert.equal(ev, 'webserver/index-inject'); f(table); } };
  const ctx = { inject: (deps, f) => { assert.deepEqual(deps, ['webServer', 'connection']); f(web); } };
  apply(ctx, { panels: [{ id: 'devboard', label: 'Développement', path: '/devboard', upstream: 'http://127.0.0.1:9' }] });
  // The web server's prefix rule matches `/devboard` and `/devboard/…` (never `/devboardx`): one route.
  assert.deepEqual(routes.map((r) => [r.kind, r.path]), [['prefix', '/devboard']]);
  assert.deepEqual(table, [{ kind: 'global', name: '__WALTER_PANELS__',
    value: [{ id: 'devboard', label: 'Développement', path: '/devboard' }] }]);
});
