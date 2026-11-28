// Access gate of the public W.Alter web address (2026-11-15, owner decision: « on garde Cloudflare Access, mais le
// message Telegram est chiant quand je me connecte avec un autre navigateur »).
//
// Sits between the Cloudflare tunnel and the web interface, for the public host only (the tailnet keeps reaching the
// interface directly). Two jobs:
//   1. Every request (HTTP and WebSocket) must carry a valid Cloudflare Access token (Cf-Access-Jwt-Assertion: RS256,
//      signed by the team's keys, right audience and issuer, not expired, allowed e-mail). Otherwise 403. This closes
//      the gap noted on 2026-11-14 (the interface trusted the tunnel without checking Access itself).
//   2. A page navigation the interface refuses with 401 (a browser without its sign-in cookie) is signed in here: the
//      gate exchanges the interface's launch token (root-only file, re-read each time: it changes at each restart) for
//      the interface's own cookie and returns it with a page that reloads itself. The reload is initiated by the site,
//      so the SameSite=Strict cookie is sent. A short marker cookie stops any loop: a second 401 within 30 s is shown.
// So Cloudflare Access (e-mail code) is the only sign-in. The gate holds no secret of its own; the launch token never
// leaves the VM (it only travels gate → interface on loopback) and is never logged.
import { createServer, request as httpRequest } from 'node:http';
import { connect } from 'node:net';
import { createPublicKey, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';

const MARKER = 'walter-gate-try';
const RELOAD = '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
  + '<meta http-equiv="refresh" content="0"><title>W.Alter</title><body style="background:#000"></body>';

const b64url = (s) => Buffer.from(s.replaceAll('-', '+').replaceAll('_', '/'), 'base64');

/** Cloudflare Access team keys, cached; refetched on an unknown key id (at most once a minute) and every hour. */
export function accessKeys(certsUrl, fetchImpl = fetch) {
  let keys = new Map(); let at = 0;
  const load = async () => {
    const r = await fetchImpl(certsUrl);
    if (!r.ok) throw new Error(`certs ${r.status}`);
    const body = await r.json();
    keys = new Map(body.keys.map((k) => [k.kid, createPublicKey({ key: k, format: 'jwk' })]));
    at = Date.now();
  };
  return async (kid) => {
    const age = Date.now() - at;
    if (age > 3600e3 || (!keys.has(kid) && age > 60e3)) await load();
    return keys.get(kid);
  };
}

/** Verify one Access token. Returns the e-mail on success, undefined otherwise (never throws). */
export async function verifyAccess(token, { keyFor, aud, issuer, emails, now = Date.now() }) {
  try {
    if (typeof token !== 'string') return undefined;
    const parts = token.split('.');
    if (parts.length !== 3) return undefined;
    const head = JSON.parse(b64url(parts[0]).toString('utf8'));
    if (head.alg !== 'RS256' || typeof head.kid !== 'string') return undefined;
    const key = await keyFor(head.kid);
    if (!key) return undefined;
    if (!verify('RSA-SHA256', Buffer.from(`${parts[0]}.${parts[1]}`), key, b64url(parts[2]))) return undefined;
    const claims = JSON.parse(b64url(parts[1]).toString('utf8'));
    const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    const sec = now / 1000;
    if (!auds.includes(aud) || claims.iss !== issuer) return undefined;
    if (typeof claims.exp !== 'number' || claims.exp <= sec) return undefined;
    if (typeof claims.nbf === 'number' && claims.nbf > sec + 60) return undefined;
    const email = String(claims.email || '').toLowerCase();
    return emails.includes(email) ? email : undefined;
  } catch {
    return undefined;
  }
}

function readToken(file) {
  const m = /[?&]token=([^&\s]+)/.exec(readFileSync(file, 'utf8'));
  if (!m) throw new Error('no token in the sign-in link file');
  return m[1];
}

function hasCookie(req, name) {
  return (req.headers.cookie || '').split(';').some((c) => c.trim().startsWith(`${name}=`));
}

/** Ask the interface for its sign-in cookie with the launch token (loopback only). Resolves to Set-Cookie or undefined. */
function exchange({ upstreamHost, upstreamPort, host, tokenFile }) {
  return new Promise((resolve) => {
    let token;
    try { token = readToken(tokenFile); } catch { resolve(undefined); return; }
    const r = httpRequest({ host: upstreamHost, port: upstreamPort, method: 'GET', path: `/?token=${token}`,
      headers: { host } }, (res) => {
      res.resume();
      const c = res.headers['set-cookie'];
      resolve(res.statusCode === 303 && c ? c : undefined);
    });
    r.on('error', () => resolve(undefined));
    r.end();
  });
}

export function createGate(cfg) {
  const { listenHost = '127.0.0.1', upstreamHost = '127.0.0.1', upstreamPort, publicHost } = cfg;
  const check = (req) => verifyAccess(req.headers['cf-access-jwt-assertion'], cfg);
  const forbid = (res) => { res.writeHead(403, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' }); res.end('forbidden\n'); };

  const server = createServer(async (req, res) => {
    if (req.headers.host !== publicHost || !(await check(req))) { forbid(res); return; }
    const navigation = req.method === 'GET' && (req.headers['sec-fetch-mode'] === 'navigate'
      || (!req.headers['sec-fetch-mode'] && (req.headers.accept || '').includes('text/html')));
    const up = httpRequest({ host: upstreamHost, port: upstreamPort, method: req.method, path: req.url,
      headers: req.headers }, async (ur) => {
      if (ur.statusCode === 401 && navigation && !hasCookie(req, MARKER)) {
        ur.resume();
        const cookie = await exchange({ upstreamHost, upstreamPort, host: publicHost, tokenFile: cfg.tokenFile });
        if (cookie) {
          res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store',
            'referrer-policy': 'no-referrer',
            'set-cookie': [...[].concat(cookie), `${MARKER}=1; Max-Age=30; Path=/; HttpOnly; Secure; SameSite=Lax`] });
          res.end(RELOAD);
          console.log('walter-web-gate: browser signed in after Cloudflare Access');
          return;
        }
        console.error('walter-web-gate: sign-in exchange failed (interface restarting?)');
        res.writeHead(503, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'retry-after': '5' });
        res.end('W.Alter redémarre, rechargez dans quelques secondes.\n');
        return;
      }
      res.writeHead(ur.statusCode, ur.rawHeaders);
      ur.pipe(res);
    });
    up.on('error', () => { if (!res.headersSent) { res.writeHead(502); } res.end(); });
    req.pipe(up);
  });

  server.on('upgrade', async (req, socket, head) => {
    if (req.headers.host !== publicHost || !(await check(req))) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return;
    }
    const up = connect(upstreamPort, upstreamHost, () => {
      let raw = `${req.method} ${req.url} HTTP/1.1\r\n`;
      for (let i = 0; i < req.rawHeaders.length; i += 2) raw += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
      up.write(`${raw}\r\n`);
      if (head?.length) up.write(head);
      up.pipe(socket); socket.pipe(up);
    });
    const close = () => { up.destroy(); socket.destroy(); };
    up.on('error', close); socket.on('error', close);
  });

  server.listenHost = listenHost;
  return server;
}

// CLI: node gate.mjs <config.json>
if (import.meta.url === `file://${process.argv[1]}`) {
  const file = process.argv[2];
  if (!file) { console.error('usage: gate.mjs <config.json>'); process.exit(2); }
  const c = JSON.parse(readFileSync(file, 'utf8'));
  const cfg = {
    publicHost: c.public_host, upstreamPort: c.upstream_port, upstreamHost: c.upstream_host || '127.0.0.1',
    listenHost: c.listen_host || '127.0.0.1', tokenFile: c.login_url_file,
    aud: c.access_aud, issuer: `https://${c.access_team_domain}`, emails: c.emails.map((e) => e.toLowerCase()),
    keyFor: accessKeys(`https://${c.access_team_domain}/cdn-cgi/access/certs`),
  };
  const server = createGate(cfg);
  server.listen(c.listen_port, cfg.listenHost, () =>
    console.log(`walter-web-gate: ${cfg.listenHost}:${c.listen_port} → ${cfg.upstreamHost}:${cfg.upstreamPort} for ${cfg.publicHost}`));
}
