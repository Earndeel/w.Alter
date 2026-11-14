// Edge worker in front of the public web interface. The interface's sign-in cookie is SameSite=Strict, so a page
// reached from another site (the Cloudflare Access login, a link in a chat) arrives without it and gets 401. The
// worker answers such a navigation with a same-origin reload, which carries the cookie; nothing else changes.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { handle } from '../worker.mjs';

const nav = (site, extra = {}) => new Request('https://w.example/', {
  headers: { 'sec-fetch-mode': 'navigate', 'sec-fetch-site': site, ...extra } });
const origin = (status, body = 'x') => async () => new Response(body, { status });

test('a cross-site navigation refused for lack of cookie is reloaded from the site itself', async () => {
  const r = await handle(nav('cross-site'), origin(401, 'dsh web authentication required'));
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('cache-control'), 'no-store');
  const html = await r.text();
  assert.match(html, /http-equiv="refresh" content="0"/);
  assert.doesNotMatch(html, /authentication required/);
});

test('a same-origin reload that is still refused shows the refusal (no loop)', async () => {
  const r = await handle(nav('same-origin'), origin(401, 'dsh web authentication required'));
  assert.equal(r.status, 401);
  assert.match(await r.text(), /authentication required/);
});

test('a typed address (no initiator) that is refused shows the refusal', async () => {
  assert.equal((await handle(nav('none'), origin(401))).status, 401);
});

test('API calls and other answers pass through untouched', async () => {
  const api = new Request('https://w.example/api/x', { headers: { 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'cross-site' } });
  assert.equal((await handle(api, origin(401))).status, 401);
  const ok = await handle(nav('cross-site'), origin(200, 'page'));
  assert.equal(ok.status, 200);
  assert.equal(await ok.text(), 'page');
  const post = new Request('https://w.example/', { method: 'POST', body: 'x',
    headers: { 'sec-fetch-mode': 'navigate', 'sec-fetch-site': 'cross-site' } });
  assert.equal((await handle(post, origin(401))).status, 401);
});

test('the request reaches the origin unchanged', async () => {
  let seen;
  await handle(new Request('https://w.example/?token=abc', { headers: { cookie: 'a=b' } }),
    async (req) => { seen = req; return new Response('x'); });
  assert.equal(seen.url, 'https://w.example/?token=abc');
  assert.equal(seen.headers.get('cookie'), 'a=b');
});
