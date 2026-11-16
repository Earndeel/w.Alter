// Panels of the web interface: a page served by another Walter module, shown in the sidebar and the main area, behind
// the web interface's own sign-in. Upstream stand-in: a local HTTP server; sign-in stand-in: an admit() function.
import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { apply, checkLinks, checkPanels, proxyHandler } from '../index.mjs';

function listen(handler) {
  return new Promise((ok) => { const s = http.createServer(handler); s.listen(0, '127.0.0.1', () => ok(s)); });
}
const url = (s) => `http://127.0.0.1:${s.address().port}`;
async function withProxy(admit, upstreamHandler, fn, actions = []) {
  const up = await listen(upstreamHandler);
  const front = await listen(proxyHandler({ path: '/devboard', upstream: url(up), admit, actions }));
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
    value: [{ id: 'devboard', label: 'Développement', path: '/devboard' }] },
  { kind: 'global', name: '__WALTER_LINKS__', value: [] }]);
});

test('settings links are published as given (no route), and checked', () => {
  const routes = [], table = [];
  const web = { webServer: { register: (r) => { routes.push(r); return () => {}; } },
    connection: { requestRejection: () => undefined }, effect: (f) => f(), on: (ev, f) => f(table) };
  apply({ inject: (deps, f) => f(web) }, { links: [{ id: 'library', label: 'Bibliothèque', url: 'https://lib.example/fr/' }] });
  assert.deepEqual(routes, []);
  assert.deepEqual(table[1], { kind: 'global', name: '__WALTER_LINKS__',
    value: [{ id: 'library', label: 'Bibliothèque', description: '', url: 'https://lib.example/fr/' }] });
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'http://lib.example/' }]), /https/);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'javascript:alert(1)' }]), /https/);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'https://u:p@lib.example/' }]), /https/);
  assert.throws(() => checkLinks([{ id: 'x', url: 'https://lib.example/' }]), /label/);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'https://a.example/' }, { id: 'x', label: 'Y', url: 'https://b.example/' }]), /duplicate/);
});

test('a link may take a Settings page of its own (section), its nav label defaulting to the link label', () => {
  const table = [];
  const web = { webServer: { register: () => () => {} }, connection: { requestRejection: () => undefined },
    effect: (f) => f(), on: (ev, f) => f(table) };
  apply({ inject: (deps, f) => f(web) }, { links: [
    { id: 'library', label: 'Bibliothèque', url: 'https://lib.example/fr/', section: 'models', section_label: 'Modèles' },
    { id: 'other', label: 'Autre', url: 'https://o.example/', section: 'other' }] });
  assert.deepEqual(table[1].value, [
    { id: 'library', label: 'Bibliothèque', description: '', url: 'https://lib.example/fr/', section: 'models', section_label: 'Modèles' },
    { id: 'other', label: 'Autre', description: '', url: 'https://o.example/', section: 'other', section_label: 'Autre' }]);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'https://a.example/', section: 'general' }]), /section/);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'https://a.example/', section: 'Bad id' }]), /section/);
  assert.throws(() => checkLinks([{ id: 'x', label: 'X', url: 'https://a.example/', section: 'm' },
    { id: 'y', label: 'Y', url: 'https://b.example/', section: 'm' }]), /section/);
});

test('a POST under a declared action prefix is relayed with its body; elsewhere still 405', async () => {
  const seen = [];
  await withProxy(ok, (req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => { seen.push([req.method, req.url, body, req.headers['x-walter-action'], req.headers.cookie]); res.end('{"ok":true}'); });
  }, async (base) => {
    const r = await fetch(`${base}/devboard/api/actions/resume`, { method: 'POST', body: '{"ref":"W-1"}',
      headers: { 'content-type': 'application/json', 'x-walter-action': '1', cookie: 'dsh-auth-x=secret' } });
    assert.equal(r.status, 200);
    assert.equal((await fetch(`${base}/devboard/api/cards`, { method: 'POST', body: '{}' })).status, 405);
    assert.equal((await fetch(`${base}/devboard/api/actions/../cards`, { method: 'POST', body: '{}' })).status, 405);
  }, ['/api/actions/']);
  assert.deepEqual(seen, [['POST', '/api/actions/resume', '{"ref":"W-1"}', '1', undefined]]);
});

test('an action is refused without sign-in, and when too large', async () => {
  let hits = 0;
  await withProxy(() => 401, (req, res) => { hits++; res.end('x'); }, async (base) => {
    assert.equal((await fetch(`${base}/devboard/api/actions/abandon`, { method: 'POST', body: '{}' })).status, 401);
  }, ['/api/actions/']);
  await withProxy(ok, (req, res) => { hits++; res.end('x'); }, async (base) => {
    const r = await fetch(`${base}/devboard/api/actions/abandon`, { method: 'POST', body: 'x'.repeat(70000) });
    assert.equal(r.status, 413);
  }, ['/api/actions/']);
  assert.equal(hits, 0);
});

test('actions must be plain path prefixes', () => {
  const base = { id: 'devboard', label: 'D', path: '/devboard', upstream: 'http://127.0.0.1:9' };
  assert.throws(() => checkPanels([{ ...base, actions: ['api/actions'] }]), /actions/);
  assert.throws(() => checkPanels([{ ...base, actions: ['/api/../x/'] }]), /actions/);
  assert.doesNotThrow(() => checkPanels([{ ...base, actions: ['/api/actions/'] }]));
});
