// Panels of the W.Alter web interface — host half.
// A panel is a page served by another Walter module (its own loopback/tailnet HTTP server) that the web interface
// shows in its sidebar and main area. The host half mounts one route per panel on the web server and relays reads
// to the module, only for a browser that passed the web interface's own Host/Origin fence and sign-in cookie
// (`connection.requestRejection`). The browser half (client.js) adds the sidebar entry and the framed page.
// Neutral software: which panels exist (id, label, path, upstream) comes from the Loader config (instance patch).
import http from 'node:http';
import https from 'node:https';

export const name = 'walter-web-panels';
export const inject = ['webServer'];

const RESERVED = ['/api', '/hmr', '/plugins', '/assets', '/@'];
const ID = /^[a-z][a-z0-9-]{0,31}$/;
const PATH = /^\/[a-z0-9][a-z0-9-]{0,31}$/;
// Hop-by-hop headers, and what must not cross: the interface's sign-in cookie stays with the interface.
const DROP_REQUEST = new Set(['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'upgrade', 'te',
  'trailer', 'cookie', 'authorization', 'host']);
const DROP_RESPONSE = new Set(['connection', 'keep-alive', 'transfer-encoding', 'set-cookie']);

/** Validate the instance's panel list; returns it unchanged. */
export function checkPanels(panels) {
  if (!Array.isArray(panels)) throw new Error('walter-web-panels: panels must be a list');
  const ids = new Set();
  for (const p of panels) {
    if (!p || !ID.test(String(p.id)) || p.id === 'conversation' || ids.has(p.id)) {
      throw new Error(`walter-web-panels: invalid or duplicate id ${JSON.stringify(p?.id)}`);
    }
    ids.add(p.id);
    if (!p.label || typeof p.label !== 'string') throw new Error(`walter-web-panels: ${p.id}: label is required`);
    if (!PATH.test(String(p.path))) throw new Error(`walter-web-panels: ${p.id}: path must look like /name`);
    if (RESERVED.some((r) => p.path === r || p.path.startsWith(`${r}/`))) {
      throw new Error(`walter-web-panels: ${p.id}: path ${p.path} is reserved by the web interface`);
    }
    let u;
    try { u = new URL(p.upstream); } catch { u = undefined; }
    if (!u || !['http:', 'https:'].includes(u.protocol) || u.pathname !== '/' || u.search) {
      throw new Error(`walter-web-panels: ${p.id}: upstream must be an http(s) origin`);
    }
  }
  return panels;
}

/**
 * Request handler for one panel: `<path>` redirects to `<path>/`; `<path>/<rest>` is relayed to `<upstream>/<rest>`
 * (GET/HEAD only — a panel is a view) once `admit(req)` returns no rejection status.
 */
export function proxyHandler({ path, upstream, admit }) {
  const base = new URL(upstream);
  const client = base.protocol === 'https:' ? https : http;
  return (req, res) => {
    const target = new URL(req.url, 'http://x');
    if (target.pathname === path) {
      res.writeHead(308, { location: `${path}/${target.search}` });
      res.end();
      return;
    }
    const rejection = admit(req);
    if (rejection !== undefined) {
      res.writeHead(rejection, { 'content-type': 'text/plain' });
      res.end(rejection === 401 ? 'unauthorized' : 'forbidden');
      return;
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { allow: 'GET, HEAD', 'content-type': 'text/plain' });
      res.end('read only');
      return;
    }
    const headers = {};
    for (const [k, v] of Object.entries(req.headers)) if (!DROP_REQUEST.has(k)) headers[k] = v;
    headers['x-forwarded-prefix'] = path;
    const up = client.request({
      protocol: base.protocol, hostname: base.hostname, port: base.port, method: req.method, headers,
      path: target.pathname.slice(path.length) + target.search,
    }, (upRes) => {
      const out = {};
      for (const [k, v] of Object.entries(upRes.headers)) if (!DROP_RESPONSE.has(k)) out[k] = v;
      res.writeHead(upRes.statusCode || 502, out);
      if (typeof res.flushHeaders === 'function') res.flushHeaders();
      upRes.pipe(res);
    });
    up.on('error', () => {
      if (!res.headersSent) { res.writeHead(502, { 'content-type': 'text/plain' }); res.end('panel unavailable'); }
      else res.destroy();
    });
    res.on('close', () => up.destroy());
    req.pipe(up);
  };
}

export function apply(ctx, config = {}) {
  const panels = checkPanels(config.panels ?? []);
  ctx.inject(['webServer', 'connection'], (web) => {
    const admit = (req) => web.connection.requestRejection(req);
    for (const p of panels) {
      const handler = proxyHandler({ path: p.path, upstream: p.upstream, admit });
      // The web server's prefix rule covers `<path>` and `<path>/…` (not `<path>x`): one route per panel.
      web.effect(() => web.webServer.register({ kind: 'prefix', path: p.path, handler }), `walter-web-panels: ${p.path}`);
    }
    web.on('webserver/index-inject', (table) => {
      table.push({ kind: 'global', name: '__WALTER_PANELS__',
        value: panels.map(({ id, label, path }) => ({ id, label, path })) });
    });
  });
}
