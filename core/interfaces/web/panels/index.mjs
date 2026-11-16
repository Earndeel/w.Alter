// Panels of the W.Alter web interface — host half.
// A panel is a page served by another Walter module (its own loopback/tailnet HTTP server) that the web interface
// shows in its sidebar and main area. The host half mounts one route per panel on the web server and relays reads
// to the module, only for a browser that passed the web interface's own Host/Origin fence and sign-in cookie
// (`connection.requestRejection`). A panel may declare `actions` (path prefixes, e.g. `/api/actions/`): POSTs there
// are relayed too (small JSON bodies), behind the same fence; everything else stays read-only.
// The browser half (client.js) adds the sidebar entry and the framed page, and one Settings › General row per link
// (`links`: a page opened in a new tab, nothing relayed — e.g. a module page behind its own sign-in).
// Neutral software: which panels exist (id, label, path, upstream) comes from the Loader config (instance patch).
import http from 'node:http';
import https from 'node:https';

export const name = 'walter-web-panels';
export const inject = ['webServer'];

const RESERVED = ['/api', '/hmr', '/plugins', '/assets', '/@'];
const ID = /^[a-z][a-z0-9-]{0,31}$/;
const PATH = /^\/[a-z0-9][a-z0-9-]{0,31}$/;
const ACTION = /^\/[a-z0-9][a-z0-9/_-]{0,63}\/$/;
const MAX_ACTION_BODY = 65536;
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
    if (p.actions !== undefined && (!Array.isArray(p.actions) || p.actions.some((a) => !ACTION.test(String(a)) || String(a).includes('..')))) {
      throw new Error(`walter-web-panels: ${p.id}: actions must be path prefixes like /api/actions/`);
    }
  }
  return panels;
}

/** Validate the instance's settings links (id, label, optional description, https url); returns them unchanged. */
export function checkLinks(links) {
  if (!Array.isArray(links)) throw new Error('walter-web-panels: links must be a list');
  const ids = new Set();
  for (const l of links) {
    if (!l || !ID.test(String(l.id)) || ids.has(l.id)) {
      throw new Error(`walter-web-panels: invalid or duplicate link id ${JSON.stringify(l?.id)}`);
    }
    ids.add(l.id);
    if (!l.label || typeof l.label !== 'string') throw new Error(`walter-web-panels: link ${l.id}: label is required`);
    if (l.description !== undefined && typeof l.description !== 'string') {
      throw new Error(`walter-web-panels: link ${l.id}: description must be text`);
    }
    let u;
    try { u = new URL(l.url); } catch { u = undefined; }
    if (!u || u.protocol !== 'https:' || u.username || u.password) {
      throw new Error(`walter-web-panels: link ${l.id}: url must be an https address`);
    }
  }
  return links;
}

/**
 * Request handler for one panel: `<path>` redirects to `<path>/`; `<path>/<rest>` is relayed to `<upstream>/<rest>`
 * (GET/HEAD — a panel is a view — plus POST under its declared `actions` prefixes) once `admit(req)` returns no
 * rejection status.
 */
export function proxyHandler({ path, upstream, admit, actions = [] }) {
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
    const rest = target.pathname.slice(path.length);
    const action = req.method === 'POST' && actions.some((a) => rest.startsWith(a)) && !rest.includes('..');
    if (req.method !== 'GET' && req.method !== 'HEAD' && !action) {
      res.writeHead(405, { allow: 'GET, HEAD', 'content-type': 'text/plain' });
      res.end('read only');
      return;
    }
    if (action && !(Number(req.headers['content-length']) <= MAX_ACTION_BODY)) {
      res.writeHead(413, { 'content-type': 'text/plain' });
      res.end('action body too large or without length');
      return;
    }
    const headers = {};
    for (const [k, v] of Object.entries(req.headers)) if (!DROP_REQUEST.has(k)) headers[k] = v;
    headers['x-forwarded-prefix'] = path;
    const up = client.request({
      protocol: base.protocol, hostname: base.hostname, port: base.port, method: req.method, headers,
      path: rest + target.search,
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
  const links = checkLinks(config.links ?? []);
  ctx.inject(['webServer', 'connection'], (web) => {
    const admit = (req) => web.connection.requestRejection(req);
    for (const p of panels) {
      const handler = proxyHandler({ path: p.path, upstream: p.upstream, admit, actions: p.actions ?? [] });
      // The web server's prefix rule covers `<path>` and `<path>/…` (not `<path>x`): one route per panel.
      web.effect(() => web.webServer.register({ kind: 'prefix', path: p.path, handler }), `walter-web-panels: ${p.path}`);
    }
    web.on('webserver/index-inject', (table) => {
      table.push({ kind: 'global', name: '__WALTER_PANELS__',
        value: panels.map(({ id, label, path }) => ({ id, label, path })) });
      table.push({ kind: 'global', name: '__WALTER_LINKS__',
        value: links.map(({ id, label, description, url }) => ({ id, label, description: description ?? '', url })) });
    });
  });
}
