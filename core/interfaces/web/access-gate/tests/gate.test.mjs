// Tests of the Access gate: token checks, automatic sign-in, loop guard, pass-through, WebSocket. No network.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request } from 'node:http';
import { connect } from 'node:net';
import { generateKeyPairSync, sign } from 'node:crypto';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createGate, verifyAccess } from '../gate.mjs';

const HOST = 'portal.example.test';
const AUD = 'aud-1'; const ISS = 'https://team.example.test'; const EMAIL = 'owner@example.test';
const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const other = generateKeyPairSync('rsa', { modulusLength: 2048 });
const enc = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
function jwt(claims = {}, key = privateKey, kid = 'k1') {
  const h = enc({ alg: 'RS256', kid }); const now = Math.floor(Date.now() / 1000);
  const p = enc({ aud: [AUD], iss: ISS, email: EMAIL, exp: now + 600, nbf: now - 5, ...claims });
  return `${h}.${p}.${sign('RSA-SHA256', Buffer.from(`${h}.${p}`), key).toString('base64url')}`;
}
const keyFor = async (kid) => (kid === 'k1' ? publicKey : undefined);
const opts = { keyFor, aud: AUD, issuer: ISS, emails: [EMAIL] };

test('verifyAccess accepts a good token and refuses every bad one', async () => {
  assert.equal(await verifyAccess(jwt(), opts), EMAIL);
  assert.equal(await verifyAccess(jwt({ aud: ['other'] }), opts), undefined);
  assert.equal(await verifyAccess(jwt({ iss: 'https://evil' }), opts), undefined);
  assert.equal(await verifyAccess(jwt({ email: 'someone@else' }), opts), undefined);
  assert.equal(await verifyAccess(jwt({ exp: 1 }), opts), undefined);
  assert.equal(await verifyAccess(jwt({}, other.privateKey), opts), undefined);
  assert.equal(await verifyAccess(jwt({}, privateKey, 'unknown'), opts), undefined);
  assert.equal(await verifyAccess('garbage', opts), undefined);
  assert.equal(await verifyAccess(undefined, opts), undefined);
});

// Fake interface: same contract as the engine's web auth (401 without cookie, ?token= on / → 303 + cookie).
const TOKEN = 'launch-token-1';
const upstream = createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname === '/' && u.searchParams.get('token') === TOKEN && req.headers.host === HOST) {
    res.writeHead(303, { location: './', 'set-cookie': 'dsh-auth-x=ok; Path=/; HttpOnly; SameSite=Strict' }); res.end(); return;
  }
  if (!(req.headers.cookie || '').includes('dsh-auth-x=ok')) { res.writeHead(401); res.end('dsh web authentication required'); return; }
  res.writeHead(200, { 'content-type': 'text/plain', 'x-up': '1' }); res.end(`page ${req.url}`);
});
upstream.on('upgrade', (req, socket) => {
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n');
  socket.on('data', (d) => socket.write(d));
});
await new Promise((r) => upstream.listen(0, '127.0.0.1', r));
const dir = mkdtempSync(join(tmpdir(), 'gate-'));
const tokenFile = join(dir, 'login-url');
writeFileSync(tokenFile, `http://127.0.0.1:3080/?token=${TOKEN}\n`);
const gate = createGate({ ...opts, publicHost: HOST, upstreamPort: upstream.address().port, tokenFile });
await new Promise((r) => gate.listen(0, '127.0.0.1', r));
const port = gate.address().port;
const sockets = new Set();
for (const s of [gate, upstream]) s.on('connection', (c) => { sockets.add(c); c.on('close', () => sockets.delete(c)); });
after(() => { for (const c of sockets) c.destroy(); gate.close(); upstream.close(); });

function get(path, headers = {}) {
  return new Promise((resolve, reject) => {
    const r = request({ host: '127.0.0.1', port, path, headers: { host: HOST, ...headers } }, (res) => {
      let body = ''; res.on('data', (d) => { body += d; }); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    r.on('error', reject); r.end();
  });
}
const nav = { 'sec-fetch-mode': 'navigate', 'sec-fetch-site': 'cross-site' };

test('no Access token, bad token or wrong host → 403, interface never reached', async () => {
  assert.equal((await get('/', nav)).status, 403);
  assert.equal((await get('/', { ...nav, 'cf-access-jwt-assertion': jwt({ email: 'x@y' }) })).status, 403);
  assert.equal((await get('/', { ...nav, host: 'evil.test', 'cf-access-jwt-assertion': jwt() })).status, 403);
});

test('a new browser after Access gets the interface cookie and a self-reload page', async () => {
  const r = await get('/devboard/', { ...nav, 'cf-access-jwt-assertion': jwt() });
  assert.equal(r.status, 200);
  assert.match(r.body, /http-equiv="refresh"/);
  const cookies = [].concat(r.headers['set-cookie']).join('\n');
  assert.match(cookies, /dsh-auth-x=ok/);
  assert.match(cookies, /walter-gate-try=1; Max-Age=30/);
  assert.doesNotMatch(JSON.stringify(r), new RegExp(TOKEN));
});

test('a signed-in browser passes through untouched', async () => {
  const r = await get('/devboard/', { ...nav, 'cf-access-jwt-assertion': jwt(), cookie: 'dsh-auth-x=ok' });
  assert.equal(r.status, 200); assert.equal(r.body, 'page /devboard/'); assert.equal(r.headers['x-up'], '1');
});

test('no loop: a second 401 navigation within the marker window is shown as is', async () => {
  const r = await get('/', { ...nav, 'cf-access-jwt-assertion': jwt(), cookie: 'walter-gate-try=1' });
  assert.equal(r.status, 401);
});

test('API calls (not navigations) keep their 401', async () => {
  const r = await get('/api/x', { 'sec-fetch-mode': 'cors', 'cf-access-jwt-assertion': jwt() });
  assert.equal(r.status, 401);
});

test('unreadable token file → 503, nothing leaked', async () => {
  writeFileSync(tokenFile, 'nothing here\n');
  const r = await get('/', { ...nav, 'cf-access-jwt-assertion': jwt() });
  assert.equal(r.status, 503);
  writeFileSync(tokenFile, `http://127.0.0.1:3080/?token=${TOKEN}\n`);
});

function upgrade(headers) {
  return new Promise((resolve) => {
    const s = connect(port, '127.0.0.1', () => {
      let raw = `GET /ws HTTP/1.1\r\nHost: ${HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n`;
      for (const [k, v] of Object.entries(headers)) raw += `${k}: ${v}\r\n`;
      s.write(`${raw}\r\n`);
    });
    let buf = '';
    s.on('data', (d) => {
      buf += d;
      if (buf.includes('101') && !buf.includes('ping')) { s.write('ping'); return; }
      s.end(); resolve(buf);
    });
    s.on('end', () => resolve(buf));
  });
}

test('WebSocket: refused without Access, relayed with it', async () => {
  assert.match(await upgrade({}), /403/);
  const out = await upgrade({ 'cf-access-jwt-assertion': jwt() });
  assert.match(out, /101/); assert.match(out, /ping/);
});
