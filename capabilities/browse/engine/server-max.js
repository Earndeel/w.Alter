require('dotenv').config();

// Global error handlers to prevent crashes from Playwright bugs
process.on('uncaughtException', (err) => {
  console.error('🦊 MAX uncaughtException (suppressed):', err.message);
});
process.on('unhandledRejection', (reason) => {
  console.error('🦊 MAX unhandledRejection (suppressed):', reason);
});

const { Camoufox, launchOptions } = require('camoufox-js');
const { firefox } = require('playwright-core');
const express = require('express');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { expandMacro } = require('./lib/macros');

const app = express();
app.use(express.json({ limit: '5mb' }));

const PORT = parseInt(process.env.CAMOFOX_MAX_PORT || '9378');
const HOST = process.env.CAMOFOX_MAX_HOST || '0.0.0.0';
// Engine (2026-10-26): camoufox (Firefox, default) or chromium (CloakBrowser: Chromium patched at the C++ level, for
// sites that need a Chromium browser). Same HTTP API, exit, identity rules and owner-cookie rule on both; one server
// process per engine (camoufox-max :9377, cloakbrowser-max :9378).
const ENGINE = process.env.CAMOFOX_ENGINE === 'chromium' ? 'chromium' : 'camoufox';
const CAMOUFOX_HEADLESS = process.env.CAMOUFOX_HEADLESS !== 'false';
const CONTEXT_DIR = process.env.CAMOFOX_DATA_DIR || 
  path.join(process.env.HOME || '/root', '.camoufox-max-data');

const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
const MAX_SNAPSHOT_NODES = 500;
const DEBUG_RESPONSES = true;
const MAX_CAPTURE_ITEMS = 80;
const MAX_CAPTURE_BODY_CHARS = 1200000;

let browser = null;
let browserStartPromise = null;
const sessions = new Map();
const tabLocks = new Map();

function logResponse(endpoint, data) {
  if (!DEBUG_RESPONSES) return;
  let logData = data;
  if (data && data.snapshot) {
    const snap = data.snapshot;
    logData = { ...data, snapshot: `[${snap.length} chars] ${snap.slice(0, 300)}...` };
  }
  console.log(`🦊 MAX ${endpoint} ->`, JSON.stringify(logData, null, 2));
}

async function withTabLock(tabId, operation) {
  const pending = tabLocks.get(tabId);
  if (pending) { try { await pending; } catch (e) {} }
  const promise = operation();
  tabLocks.set(tabId, promise);
  try { return await promise; } finally {
    if (tabLocks.get(tabId) === promise) tabLocks.delete(tabId);
  }
}

function getHostOS() {
  const platform = os.platform();
  if (platform === 'darwin') return 'macos';
  if (platform === 'win32') return 'windows';
  return 'linux';
}

async function ensureBrowser() {
  if (browser) return browser;
  // Serialize concurrent launches. A burst of requests must not create
  // several Camoufox processes while the first launch is still booting.
  if (browserStartPromise) return browserStartPromise;

  browserStartPromise = (async () => {
    const hostOS = IDENTITY.os;
    console.log(`🦊 MAX Launching ${ENGINE} (fingerprint OS: ${hostOS}, host: ${getHostOS()})...`);

    if (!fs.existsSync(CONTEXT_DIR)) {
      fs.mkdirSync(CONTEXT_DIR, { recursive: true });
      console.log(`🦊 MAX Created context dir: ${CONTEXT_DIR}`);
    }

    // With a default exit, the whole identity is derived from the exit IP (looked up through the exit); WebRTC
    // reports that IP. Exit unreachable: identity from this server's IP (plain geoip).
    let identity = null;
    if (DEFAULT_PROXY && await proxyReachable(DEFAULT_PROXY)) {
      try { identity = await exitIdentity(); } catch (e) { console.log(`🦊 MAX exit identity lookup failed: ${e.message}`); }
    }
    if (ENGINE === 'chromium') {
      browser = await launchChromium(identity);
      launchedExitIP = identity ? identity.ip : null;
      return browser;
    }
    const device = await deviceConfig();
    const options = await launchOptions({
      headless: CAMOUFOX_HEADLESS,
      os: hostOS,
      humanize: 2.0,
      enable_cache: true,
      persistent_context: true,
      geoip: !identity,
      config: { ...device, ...(identity ? identity.config : {}) },
      ...(identity ? { firefox_user_prefs: { 'network.dns.disableIPv6': true } } : {}),
      data_dir: CONTEXT_DIR,
    });
    delete options.proxy;   // the exit is applied per session, never browser-wide
    // Any device value Camoufox added on its own this time (e.g. screen.availTop) joins the fixed device for good.
    const added = Object.entries(camouConfigOf(options)).filter(([k]) => DEVICE_KEYS.test(k) && !(k in device));
    if (added.length) {
      fs.writeFileSync(DEVICE_FILE, JSON.stringify({ ...device, ...Object.fromEntries(added) }, null, 1), { mode: 0o600 });
      console.log(`🦊 MAX device fingerprint completed with ${added.map(([k]) => k).join(', ')}`);
    }
    launchedExitIP = identity ? identity.ip : null;
    console.log(identity
      ? `🦊 MAX identity from exit IP ${identity.ip}: ${identity.config.timezone}, ${identity.config['locale:all']}`
      : '🦊 MAX identity from this server\'s IP (no default exit reachable)');

    browser = await firefox.launch(options);
    console.log('🦊 MAX Camoufox browser launched');
    return browser;
  })();

  try {
    return await browserStartPromise;
  } finally {
    browserStartPromise = null;
  }
}

function normalizeUserId(userId) { return String(userId); }

// Per-session proxy routes (session-specific network, never global).
const sessionProxies = new Map(); // userId -> {server, username?, password?}

// Default exit and identity (2026-10-20): a session without its own route leaves through the owner's machine
// (CAMOFOX_DEFAULT_PROXY, e.g. socks5://127.0.0.1:1082 = walter-exit-mac) and presents that machine's timezone and
// language, so the owner's cookies are always used from the owner's own IP. When the default exit is down, the
// session opens WITHOUT the owner's cookies (anonymous, from this server's IP) rather than exposing them elsewhere.
const DEFAULT_PROXY = process.env.CAMOFOX_DEFAULT_PROXY || '';
const IDENTITY = {
  timezoneId: process.env.CAMOFOX_TIMEZONE || 'America/Los_Angeles',
  locale: process.env.CAMOFOX_LOCALE || 'en-US',
  // Fingerprint OS and accepted languages of the owner's own browser (e.g. macos, "fr-FR,fr,en-US,en").
  os: process.env.CAMOFOX_OS || getHostOS(),
  languages: process.env.CAMOFOX_LANGUAGES || process.env.CAMOFOX_LOCALE || 'en-US',
};
const net = require('net');
const CAMOUFOX_DIST = path.dirname(require.resolve('camoufox-js'));
const { publicIP } = require(path.join(CAMOUFOX_DIST, 'ip.js'));
const { getGeolocation } = require(path.join(CAMOUFOX_DIST, 'locale.js'));
let launchedExitIP = null;   // exit IP the running browser's identity was derived from (null = this server's IP)

// Identity synchronised with the exit IP, as Camoufox's geoip does: timezone, locale, position and WebRTC IP come
// from where the exit IP is; the language list is the region's language, then English.
// Human typing: per-key delays drawn around a natural rhythm, longer after spaces and punctuation, occasional
// hesitations. Clearing a field uses the keyboard too (select all + delete), never a programmatic fill.
function humanDelay(ch) {
  const base = 55 + Math.random() * 90 + (Math.random() < 0.15 ? Math.random() * 160 : 0);
  return Math.round(/[\s.,;:!?]/.test(ch) ? base + 40 + Math.random() * 120 : base);
}
async function humanType(page, text, locator = null) {
  if (locator) {
    await locator.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Backspace');
  }
  for (const ch of String(text)) {
    await page.keyboard.type(ch);
    await page.waitForTimeout(humanDelay(ch));
    if (Math.random() < 0.03) await page.waitForTimeout(300 + Math.random() * 600);
  }
}

// One device for the instance: the fingerprint (hardware, screen, GPU, fonts, canvas seeds…) is generated once from
// the owner's machine profile and reused at every launch, so a relaunch never looks like a new device. Network
// identity (timezone, languages, position, WebRTC) stays per launch, from the exit IP.
const DEVICE_FILE = path.join(CONTEXT_DIR, 'device-fingerprint.json');
const DEVICE_KEYS = /^(navigator\.|screen\.|window\.|webGl|canvas:|fonts|headers\.|document\.)/;
function camouConfigOf(options) {
  const env = options.env || {};
  return JSON.parse(Object.keys(env).filter((k) => k.startsWith('CAMOU_CONFIG')).sort().map((k) => env[k]).join(''));
}
async function deviceConfig() {
  if (fs.existsSync(DEVICE_FILE)) return JSON.parse(fs.readFileSync(DEVICE_FILE, 'utf8'));
  const [w, h] = (process.env.CAMOFOX_DEVICE_SCREEN || '').split('x').map(Number);
  const webgl = (process.env.CAMOFOX_DEVICE_WEBGL || '').split('|');
  const cores = Number(process.env.CAMOFOX_DEVICE_CORES || 0);
  const generated = camouConfigOf(await launchOptions({
    headless: CAMOUFOX_HEADLESS, os: IDENTITY.os, geoip: false,
    ...(w && h ? { screen: { minWidth: w, maxWidth: w, minHeight: h, maxHeight: h } } : {}),
    ...(webgl.length === 2 ? { webgl_config: webgl } : {}),
    ...(cores ? { config: { 'navigator.hardwareConcurrency': cores } } : {}),
  }));
  const device = Object.fromEntries(Object.entries(generated).filter(([k]) => DEVICE_KEYS.test(k)));
  fs.writeFileSync(DEVICE_FILE, JSON.stringify(device, null, 1), { mode: 0o600 });
  console.log(`🦊 MAX device fingerprint generated once (${Object.keys(device).length} keys) -> ${DEVICE_FILE}`);
  return device;
}

// Chromium engine: the device is one fixed fingerprint seed (the binary derives GPU, screen, cores, canvas… from it as
// one coherent package), generated once and stored in the data dir; persona OS = the owner's. Network identity
// (timezone, languages, WebRTC IP) comes from the exit IP like Camoufox's, passed as binary flags (no CDP emulation).
async function launchChromium(identity) {
  const { launch } = require('cloakbrowser');
  let device = fs.existsSync(DEVICE_FILE) ? JSON.parse(fs.readFileSync(DEVICE_FILE, 'utf8')) : null;
  if (!device || !device.seed) {
    device = { engine: 'chromium', seed: crypto.randomInt(10000, 100000), platform: IDENTITY.os };
    fs.writeFileSync(DEVICE_FILE, JSON.stringify(device, null, 1), { mode: 0o600 });
    console.log(`🦊 MAX chromium device seed generated once -> ${DEVICE_FILE}`);
  }
  const langs = (identity ? identity.config['locale:all'] : IDENTITY.languages).split(',').map((l) => l.trim()).filter(Boolean);
  const args = [`--fingerprint=${device.seed}`, `--fingerprint-platform=${device.platform}`,
    `--lang=${langs[0]}`, `--fingerprint-locale=${langs.join(',')}`];
  if (identity) args.push(`--fingerprint-webrtc-ip=${identity.ip}`);
  const timezone = identity ? identity.config.timezone : IDENTITY.timezoneId;
  console.log(`🦊 MAX Launching Chromium (CloakBrowser, persona ${device.platform}, ${timezone}, ${langs.join(',')})...`);
  const b = await launch({ headless: CAMOUFOX_HEADLESS, humanize: true, timezone, args });
  console.log(identity
    ? `🦊 MAX chromium identity from exit IP ${identity.ip}`
    : '🦊 MAX chromium identity from instance defaults (no default exit reachable)');
  return b;
}

async function exitIdentity() {
  const ip = await publicIP(DEFAULT_PROXY);
  const geo = (await getGeolocation(ip)).asConfig();
  const region = geo['locale:region'];
  // Camoufox draws the language at random by speaker share; use the region's main language instead (CLDR likely subtags).
  const likely = region ? new Intl.Locale(`und-${region}`).maximize() : null;
  const lang = likely ? likely.language : geo['locale:language'];
  geo['locale:language'] = lang;
  if (likely && likely.script) geo['locale:script'] = likely.script;
  const all = [region ? `${lang}-${region}` : lang, lang, ...(lang === 'en' ? [] : ['en-US', 'en'])];
  return { ip, config: { ...geo, 'webrtc:ipv4': ip, 'locale:all': [...new Set(all)].join(', ') } };
}

function proxyReachable(server, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let u;
    try { u = new URL(server); } catch { return resolve(false); }
    const sock = net.connect({ host: u.hostname, port: Number(u.port) || 1080 });
    const done = (ok) => { sock.destroy(); resolve(ok); };
    sock.setTimeout(timeoutMs, () => done(false));
    sock.once('connect', () => done(true));
    sock.once('error', () => done(false));
  });
}

async function getSession(userId) {
  const key = normalizeUserId(userId);
  let session = sessions.get(key);
  if (!session) {
    const b = await ensureBrowser();
    const contextOptions = {
      viewport: { width: 1280, height: 720 },
      // Timezone and languages come from the fingerprint (exit IP); a context value would override them.
      ...(DEFAULT_PROXY ? {} : { locale: IDENTITY.locale, timezoneId: IDENTITY.timezoneId }),
      storageState: path.join(CONTEXT_DIR, 'storage-state.json'),
    };
    const proxy = sessionProxies.get(key);
    let route = 'direct';   // how this session reaches the web: session-proxy | default-exit | direct
    if (proxy && proxy.server) {
      route = 'session-proxy';
      contextOptions.proxy = { server: proxy.server };
      if (proxy.username) contextOptions.proxy.username = proxy.username;
      if (proxy.password) contextOptions.proxy.password = proxy.password;
      console.log(`🦊 MAX Session ${key} routed through proxy ${proxy.server} (session-scoped)`);
    } else if (DEFAULT_PROXY) {
      if (await proxyReachable(DEFAULT_PROXY)) {
        contextOptions.proxy = { server: DEFAULT_PROXY };
        route = 'default-exit';
        console.log(`🦊 MAX Session ${key} leaves through the default exit ${DEFAULT_PROXY}`);
      } else {
        delete contextOptions.storageState;
        console.log(`🦊 MAX Session ${key}: default exit ${DEFAULT_PROXY} down — anonymous session (no owner cookies)`);
      }
    }
    const context = await b.newContext(contextOptions);
    session = { context, tabGroups: new Map(), lastAccess: Date.now(), route };
    sessions.set(key, session);
    console.log(`🦊 MAX Session created for user ${key}`);
  }
  session.lastAccess = Date.now();
  return session;
}

function getTabGroup(session, listItemId) {
  let group = session.tabGroups.get(listItemId);
  if (!group) { group = new Map(); session.tabGroups.set(listItemId, group); }
  return group;
}

function findTab(session, tabId) {
  for (const [listItemId, group] of session.tabGroups) {
    if (group.has(tabId)) return { tabState: group.get(tabId), listItemId, group };
  }
  return null;
}

function createTabState(page) {
  return {
    page,
    refs: new Map(),
    visitedUrls: new Set(),
    toolCalls: 0,
    networkCaptures: [],
    networkCaptureErrors: [],
    removeNetworkCapture: null,
  };
}

function attachNetworkCapture(tabState) {
  const onResponse = async (response) => {
    try {
      const request = response.request();
      const resourceType = request.resourceType();
      const headers = response.headers();
      const contentType = String(headers['content-type'] || '');
      const lowerContentType = contentType.toLowerCase();
      if (!['xhr', 'fetch', 'document'].includes(resourceType)) return;
      const body = await response.text();
      if (!body || body.length > MAX_CAPTURE_BODY_CHARS) return;
      if (!lowerContentType.includes('json') && !/^\s*[\[{]/.test(body)) return;
      let payload;
      try {
        payload = JSON.parse(body);
      } catch (_) {
        return;
      }
      tabState.networkCaptures.push({
        url: response.url(),
        method: request.method(),
        status: response.status(),
        contentType: contentType || 'application/json',
        responseBytes: Buffer.byteLength(body),
        requestBodyBytes: Buffer.byteLength(request.postData() || ''),
        payload,
      });
      if (tabState.networkCaptures.length > MAX_CAPTURE_ITEMS) {
        tabState.networkCaptures.splice(0, tabState.networkCaptures.length - MAX_CAPTURE_ITEMS);
      }
    } catch (error) {
      if (tabState.networkCaptureErrors.length < 10) {
        tabState.networkCaptureErrors.push(String(error.message || error));
      }
    }
  };
  tabState.page.on('response', onResponse);
  tabState.removeNetworkCapture = () => tabState.page.off('response', onResponse);
}

async function waitForPageReady(page, options = {}) {
  const { timeout = 10000, waitForNetwork = true } = options;
  try {
    await page.waitForLoadState('domcontentloaded', { timeout });
    if (waitForNetwork) {
      await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {
        console.log('waitForPageReady: networkidle timeout (continuing anyway)');
      });
    }
    await page.evaluate(async () => {
      for (let i = 0; i < 40; i++) {
        const entries = performance.getEntriesByType('resource');
        const recent = entries.slice(-5);
        const quiet = recent.every(e => (performance.now() - e.responseEnd) > 400);
        if (document.readyState === 'complete' && quiet) {
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
          return true;
        }
        await new Promise(r => setTimeout(r, 250));
      }
    }).catch(() => {});
  } catch (e) {
    if (e.message.includes('Timeout')) console.log('waitForPageReady: domcontentloaded timeout');
    else throw e;
  }
}

async function getDomSnapshot(page, options = {}) {
  const maxNodes = options.maxNodes || MAX_SNAPSHOT_NODES;
  const result = await page.evaluate(({ maxNodes }) => {
    const semanticTags = new Set([
      'A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'SUMMARY',
      'IMG', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'NAV', 'MAIN', 'FORM',
      'SECTION', 'ARTICLE', 'LABEL', 'LI', 'TABLE', 'TR', 'TH', 'TD'
    ]);
    const interactiveTags = new Set([
      'A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'SUMMARY'
    ]);
    const visible = (el) => {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        parseFloat(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
    };
    const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
    const roleFor = (el) => {
      const explicit = el.getAttribute('role');
      if (explicit) return explicit;
      const tag = el.tagName;
      if (tag === 'A' && el.getAttribute('href')) return 'link';
      if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button';
      if (tag === 'TEXTAREA') return 'textbox';
      if (tag === 'SELECT') return 'combobox';
      if (tag === 'INPUT') {
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        if (type === 'checkbox') return 'checkbox';
        if (type === 'radio') return 'radio';
        if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
        return 'textbox';
      }
      if (/^H[1-6]$/.test(tag)) return 'heading';
      if (tag === 'IMG') return 'image';
      if (tag === 'NAV') return 'navigation';
      if (tag === 'MAIN') return 'main';
      if (tag === 'FORM') return 'form';
      if (tag === 'LI') return 'listitem';
      if (tag === 'TR') return 'row';
      if (tag === 'TH' || tag === 'TD') return 'cell';
      return 'generic';
    };
    const nameFor = (el) => {
      const aria = el.getAttribute('aria-label');
      if (aria) return clean(aria);
      const labelledBy = el.getAttribute('aria-labelledby');
      if (labelledBy) {
        const labelled = labelledBy.split(/\\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ');
        if (clean(labelled)) return clean(labelled);
      }
      if (el.tagName === 'IMG') return clean(el.getAttribute('alt') || el.getAttribute('title'));
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
        return clean(el.getAttribute('placeholder') || el.getAttribute('title') || el.value || el.name);
      }
      return clean(el.innerText || el.textContent);
    };
    const semanticChild = (el) => Array.from(el.children).some(child => semanticTags.has(child.tagName));
    document.querySelectorAll('[data-ref]').forEach(el => el.removeAttribute('data-ref'));
    const items = [];
    let counter = 0;
    for (const el of document.querySelectorAll('body *')) {
      if (items.length >= maxNodes || !visible(el)) continue;
      const tag = el.tagName;
      const role = roleFor(el);
      const interactive = interactiveTags.has(tag) || el.hasAttribute('contenteditable') || el.hasAttribute('tabindex');
      const heading = /^H[1-6]$/.test(tag);
      const landmark = ['NAV', 'MAIN', 'FORM'].includes(tag);
      const text = nameFor(el);
      const leafText = text && !semanticChild(el) && !['SCRIPT', 'STYLE', 'SVG', 'PATH'].includes(tag);
      if (!interactive && !heading && !landmark && !leafText) continue;
      if (!text && !interactive && !landmark) continue;
      const ref = `e${counter++}`;
      el.setAttribute('data-ref', ref);
      items.push({
        ref,
        role,
        name: text.slice(0, 500),
        value: ('value' in el) ? String(el.value || '') : undefined,
        editable: interactive && ['INPUT', 'TEXTAREA'].includes(tag),
        checked: ('checked' in el) ? Boolean(el.checked) : undefined,
        level: heading ? Number(tag.slice(1)) : undefined
      });
    }
    return items;
  }, { maxNodes });

  let snapshot = '';
  const refs = {};
  for (const item of result || []) {
    const suffix = item.editable ? ' [editable]' :
      (item.value ? ` \"${item.value}\"` : '');
    const checked = item.checked !== undefined ? ` [checked=${item.checked}]` : '';
    const level = item.level ? ` [level=${item.level}]` : '';
    snapshot += `[${item.ref}] <${item.role}> ${item.name || ''}${suffix}${checked}${level}`.trimEnd() + '\\n';
    refs[item.ref] = {
      role: item.role,
      name: item.name || '',
      nth: 0,
    };
  }
  return { snapshot: snapshot || '[no visible DOM elements]', refs };
}

async function getSnapshot(page, options = {}) {
  const { elementRefs: includeRefs = true } = options;
  let snapshot;
  try {
    if (!page.accessibility || typeof page.accessibility.snapshot !== 'function') {
      throw new Error('accessibility snapshot unavailable');
    }
    snapshot = await page.accessibility.snapshot({ interestingOnly: true, root: page.mainFrame() });
  } catch (e) {
    console.log('getSnapshot: accessibility snapshot unavailable, using DOM fallback:', e.message);
    return getDomSnapshot(page, { maxNodes: MAX_SNAPSHOT_NODES });
  }
  let snapshotStr = '';
  const refs = new Map();
  let refCounter = 0;
  
  function walk(node, depth = 0) {
    if (!node) return;
    const role = node.role || 'text';
    const name = node.name || '';
    const nth = refCounter++;
    const refId = `e${nth}`;
    
    if (includeRefs && (role !== 'text' || name.trim().length > 5)) {
      refs.set(refId, { role, name: name.trim(), nth });
    }
    
    const indent = '  '.repeat(Math.min(depth, 10));
    if (name && name.trim()) {
      snapshotStr += `${indent}[${refId}] <${role}> ${name.trim()}`;
      if (node.checked !== undefined) snapshotStr += ` [checked=${node.checked}]`;
      if (node.level) snapshotStr += ` [level=${node.level}]`;
      snapshotStr += '\n';
    } else if (role !== 'text' && node.value !== undefined) {
      snapshotStr += `${indent}[${refId}] <${role}> "${node.value}"`;
      if (node.description) snapshotStr += ` - ${node.description}`;
      snapshotStr += ' [editable]\n';
    } else if (!name) {
      snapshotStr += `${indent}[${refId}] <${role}>`;
      snapshotStr += ' (empty)\n';
    }
    
    if (node.children) {
      for (const child of node.children) walk(child, depth + 1);
    }
  }
  walk(snapshot);
  
  if (snapshotStr.length > MAX_SNAPSHOT_NODES * 80) {
    snapshotStr = snapshotStr.slice(0, MAX_SNAPSHOT_NODES * 80) + '\n...[truncated]';
  }
  
  return { snapshot: snapshotStr, refs: includeRefs ? Object.fromEntries(refs) : {} };
}

app.post('/session/new', async (req, res) => {
  try {
    const { userId, proxy } = req.body;
    const key = normalizeUserId(userId || 'default');
    if (proxy && proxy.server) {
      sessionProxies.set(key, { server: proxy.server, username: proxy.username, password: proxy.password });
    }
    await getSession(key);
    res.json({ ok: true, userId: key, proxy: proxy && proxy.server ? proxy.server : null });
  } catch (e) {
    console.error('Error creating session:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/new', async (req, res) => {
  try {
    const { userId, listItemId } = req.body;
    const session = await getSession(userId || 'default');
    const group = getTabGroup(session, listItemId || crypto.randomUUID());
    const page = await session.context.newPage();
    // Keep browser diagnostics visible while debugging authenticated app failures.
    page.on('pageerror', (err) => console.error('🦊 MAX pageerror:', err?.stack || err?.message || err));
    page.on('console', (msg) => {
      if (msg.type() === 'error') console.error('🦊 MAX browser console.error:', msg.text());
    });
    const tabState = createTabState(page);
    attachNetworkCapture(tabState);
    const tabId = crypto.randomUUID();
    group.set(tabId, tabState);
    res.json({ ok: true, tabId, listItemId: listItemId || 'default' });
  } catch (e) {
    console.error('Error creating tab:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/navigate', async (req, res) => {
  try {
    const { userId, tabId, url } = req.body;
    
    // Ensure browser is healthy before proceeding
    await ensureBrowserHealthy();
    
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const { tabState } = found;
    const finalUrl = expandMacro(url);
    tabState.visitedUrls.add(finalUrl);
    tabState.toolCalls++;
    
    console.log(`🦊 MAX navigate: ${finalUrl}`);
    await tabState.page.goto(finalUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await waitForPageReady(tabState.page);
    const snap = await getSnapshot(tabState.page);
    tabState.refs = snap.refs || {};
    logResponse('navigate', { url: finalUrl, snapshot: snap.snapshot });
    res.json({ ok: true, url: finalUrl, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Error navigating:', e);
    res.status(500).json({ error: e.message });
  }
});

// Backward-compatible aliases for Hermes workers that still use the
// camofox-browser contract.  The active Hermes process can outlive a code
// update, so keeping these aliases avoids a 404 during the transition to /tab.
app.post('/tabs', async (req, res) => {
  try {
    const { userId, listItemId, url } = req.body;
    const session = await getSession(userId || 'default');
    const group = getTabGroup(session, listItemId || crypto.randomUUID());
    const page = await session.context.newPage();
    page.on('pageerror', (err) => console.error('🦊 MAX pageerror:', err?.stack || err?.message || err));
    page.on('console', (msg) => {
      if (msg.type() === 'error') console.error('🦊 MAX browser console.error:', msg.text());
    });
    const tabState = createTabState(page);
    attachNetworkCapture(tabState);
    const tabId = crypto.randomUUID();
    group.set(tabId, tabState);
    if (url) {
      const finalUrl = expandMacro(url);
      tabState.visitedUrls.add(finalUrl);
      await page.goto(finalUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await waitForPageReady(page);
      const snap = await getSnapshot(page);
      tabState.refs = snap.refs || {};
    }
    res.json({ ok: true, tabId, listItemId: listItemId || 'default' });
  } catch (e) {
    console.error('Legacy /tabs create failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tabs/:tabId/navigate', async (req, res) => {
  try {
    const { userId, url } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    const finalUrl = expandMacro(url);
    found.tabState.visitedUrls.add(finalUrl);
    found.tabState.toolCalls++;
    await found.tabState.page.goto(finalUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await waitForPageReady(found.tabState.page);
    const snap = await getSnapshot(found.tabState.page);
    found.tabState.refs = snap.refs || {};
    res.json({ ok: true, url: finalUrl, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Legacy /tabs navigate failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.get('/tabs/:tabId/snapshot', async (req, res) => {
  try {
    const session = await getSession(req.query.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    const snap = await getSnapshot(found.tabState.page);
    found.tabState.refs = snap.refs || {};
    res.json({ ok: true, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Legacy /tabs snapshot failed:', e);
    res.status(500).json({ error: e.message });
  }
});

// Remaining legacy interaction aliases. These keep already-loaded Hermes
// workers compatible until their Python module is reloaded.
app.post('/tabs/:tabId/click', async (req, res) => {
  try {
    const session = await getSession(req.body.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    const { tabState } = found;
    const ref = req.body.ref;
    if (!tabState.refs[ref]) return res.status(400).json({ error: `Ref not found: ${ref}` });
    await tabState.page.click(`xpath=//*[@data-ref='${ref}']`);
    await waitForPageReady(tabState.page, { timeout: 5000, waitForNetwork: false });
    const snap = await getSnapshot(tabState.page);
    tabState.refs = snap.refs || {};
    res.json({ ok: true, ref, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Legacy /tabs click failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tabs/:tabId/type', async (req, res) => {
  try {
    const session = await getSession(req.body.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    const ref = req.body.ref;
    const locator = found.tabState.page.locator(
      `xpath=//input[@data-ref='${ref}'] | //textarea[@data-ref='${ref}'] | //div[@contenteditable="true"][@data-ref='${ref}']`
    ).first();
    await humanType(found.tabState.page, req.body.text || '', locator);
    res.json({ ok: true, ref });
  } catch (e) {
    console.error('Legacy /tabs type failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tabs/:tabId/scroll', async (req, res) => {
  try {
    const session = await getSession(req.body.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.keyboard.press(req.body.direction === 'up' ? 'PageUp' : 'PageDown');
    await found.tabState.page.waitForTimeout(300);
    const snap = await getSnapshot(found.tabState.page);
    found.tabState.refs = snap.refs || {};
    res.json({ ok: true, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Legacy /tabs scroll failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tabs/:tabId/back', async (req, res) => {
  try {
    const session = await getSession(req.body.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.goBack({ waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
    const snap = await getSnapshot(found.tabState.page);
    found.tabState.refs = snap.refs || {};
    res.json({ ok: true, url: found.tabState.page.url(), snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Legacy /tabs back failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tabs/:tabId/press', async (req, res) => {
  try {
    const session = await getSession(req.body.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.keyboard.press(req.body.key);
    res.json({ ok: true, key: req.body.key });
  } catch (e) {
    console.error('Legacy /tabs press failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.get('/tabs/:tabId/screenshot', async (req, res) => {
  try {
    const session = await getSession(req.query.userId || 'default');
    const found = findTab(session, req.params.tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    const buffer = await found.tabState.page.screenshot({ fullPage: false });
    res.type('png').send(buffer);
  } catch (e) {
    console.error('Legacy /tabs screenshot failed:', e);
    res.status(500).json({ error: e.message });
  }
});

app.delete('/sessions/:userId', async (req, res) => {
  try {
    const key = normalizeUserId(req.params.userId);
    const session = sessions.get(key);
    if (session) {
      await session.context.close().catch(() => {});
      sessions.delete(key);
    }
    res.json({ ok: true });
  } catch (e) {
    console.error('Legacy session close failed:', e);
    res.status(500).json({ error: e.message });
  }
});

// Add init script that runs before any page script
app.post('/tab/add-init-script', async (req, res) => {
  try {
    const { userId, tabId, script } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    await found.tabState.page.addInitScript(script);
    res.json({ ok: true, message: 'Init script added. It will run on next navigation.' });
  } catch (e) {
    console.error('Error adding init script:', e);
    res.status(500).json({ error: e.message });
  }
});

// Intercept and modify network requests (e.g. inject code into JS bundles)
app.post('/tab/route', async (req, res) => {
  try {
    const { userId, tabId, urlPattern, bodyPrefix } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });

    const { tabState } = found;
    await tabState.page.route(urlPattern, async (route) => {
      const response = await route.fetch();
      let body = await response.text();
      body = bodyPrefix + body;
      await route.fulfill({
        response,
        body,
        headers: { ...response.headers() }
      });
    });
    res.json({ ok: true, message: `Route added for ${urlPattern}` });
  } catch (e) {
    console.error('Error adding route:', e);
    res.status(500).json({ error: e.message });
  }
});

// Remove all routes for a tab
app.post('/tab/unroute-all', async (req, res) => {
  try {
    const { userId, tabId } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.unrouteAll();
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/snapshot', async (req, res) => {
  try {
    const { userId, tabId } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const snap = await getSnapshot(found.tabState.page);
    found.tabState.refs = snap.refs || {};
    logResponse('snapshot', { snapshot: snap.snapshot });
    res.json({ ok: true, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Error getting snapshot:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/click', async (req, res) => {
  try {
    const { userId, tabId, ref } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const { tabState } = found;
    const el = tabState.refs[ref];
    if (!el) return res.status(400).json({ error: `Ref not found: ${ref}` });
    
    tabState.toolCalls++;
    try {
      await tabState.page.click(`xpath=//*[@data-ref='${ref}']`);
    } catch {
      const nth = el.nth;
      const locator = tabState.page.locator(`${el.role}`).nth(nth);
      await locator.click({ timeout: 5000 });
    }
    await waitForPageReady(tabState.page);
    const snap = await getSnapshot(tabState.page);
    tabState.refs = snap.refs || {};
    logResponse('click', { ref, snapshot: snap.snapshot });
    res.json({ ok: true, ref, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Error clicking:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/type', async (req, res) => {
  try {
    const { userId, tabId, ref, text } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const { tabState } = found;
    tabState.toolCalls++;
    const locator = tabState.page.locator(
      `xpath=//input[@data-ref='${ref}'] | //textarea[@data-ref='${ref}'] | //div[@contenteditable="true"][@data-ref='${ref}']`
    ).first();
    await humanType(tabState.page, text, locator);
    logResponse('type', { ref });
    res.json({ ok: true, ref });
  } catch (e) {
    console.error('Error typing:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/scroll', async (req, res) => {
  try {
    const { userId, tabId, direction = 'down' } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const key = direction === 'up' ? 'PageUp' : 'PageDown';
    await found.tabState.page.keyboard.press(key);
    await found.tabState.page.waitForTimeout(300);
    const snap = await getSnapshot(found.tabState.page);
    logResponse('scroll', { direction, snapshot: snap.snapshot });
    res.json({ ok: true, snapshot: snap.snapshot, refs: snap.refs });
  } catch (e) {
    console.error('Error scrolling:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/screenshot', async (req, res) => {
  try {
    const { userId, tabId } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const buffer = await found.tabState.page.screenshot({ fullPage: false });
    res.json({ ok: true, buffer: buffer.toString('base64') });
  } catch (e) {
    console.error('Error taking screenshot:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/tab/close', async (req, res) => {
  try {
    const { userId, tabId } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    if (found.tabState.removeNetworkCapture) found.tabState.removeNetworkCapture();
    await found.tabState.page.close();
    found.group.delete(tabId);
    res.json({ ok: true });
  } catch (e) {
    console.error('Error closing tab:', e);
    res.status(500).json({ error: e.message });
  }
});

// Return bounded JSON responses observed by Playwright's native response
// event. The route deliberately excludes cookies, headers, and request bodies.
app.post('/tab/network-captures', async (req, res) => {
  try {
    const { userId, tabId } = req.body;
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    res.json({
      ok: true,
      captures: found.tabState.networkCaptures,
      errors: found.tabState.networkCaptureErrors,
    });
  } catch (e) {
    console.error('Error reading network captures:', e);
    res.status(500).json({ error: e.message });
  }
});

// Evaluate JavaScript in a tab (with browser health check)
app.post('/tab/evaluate', async (req, res) => {
  try {
    const { userId, tabId, expression } = req.body;
    
    // Ensure browser is healthy before proceeding
    await ensureBrowserHealthy();
    
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    const result = await found.tabState.page.evaluate(expression);
    res.json({ ok: true, result });
  } catch (e) {
    console.error('Error evaluating:', e.message);
    
    // If browser is dead, try to restart and return helpful error
    if (e.message.includes('Target page, context or browser has been closed')) {
      browser = null;
      sessions.clear();
      return res.status(503).json({ 
        error: 'Browser crashed - restarting. Retry your request.',
        retry: true 
      });
    }
    
    res.status(500).json({ error: e.message });
  }
});

// Fetch a binary resource through the authenticated Playwright context.
// Browser-page fetches cannot read Flow media URLs because of CORS, while
// the context request API shares the logged-in browser cookies.  Keep this
// route host-restricted so it cannot become a generic SSRF proxy.
app.post('/tab/fetch-binary', async (req, res) => {
  try {
    const { userId, tabId, url } = req.body;
    const parsed = new URL(url);
    const allowedHost = parsed.hostname === 'labs.google' ||
      parsed.hostname.endsWith('.googleusercontent.com');
    if (parsed.protocol !== 'https:' || !allowedHost) {
      return res.status(400).json({ error: 'Only Google media URLs are allowed' });
    }

    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });

    const response = await found.tabState.page.context().request.get(url);
    const body = await response.body();
    res.status(response.status());
    const contentType = response.headers()['content-type'];
    const contentLength = response.headers()['content-length'];
    if (contentType) res.set('content-type', contentType);
    if (contentLength) res.set('content-length', contentLength);
    res.send(body);
  } catch (e) {
    console.error('Error fetching binary resource:', e.message);
    res.status(500).json({ error: e.message });
  }
});

// Add cookies to context
app.post('/session/cookies', async (req, res) => {
  try {
    const { userId, cookies } = req.body;
    const session = await getSession(userId || 'default');
    // The owner's cookies are only used from the owner's network: never in a session that left through this server
    // because the default exit was down.
    if (DEFAULT_PROXY && session.route === 'direct') {
      console.log(`🦊 MAX cookies refused for session ${userId}: default exit down, session leaves from this server's IP`);
      return res.status(409).json({ error: 'owner cookies refused: the default exit (owner network) is unreachable' });
    }
    await session.context.addCookies(cookies);
    res.json({ ok: true, count: cookies.length });
  } catch (e) {
    console.error('Error adding cookies:', e);
    res.status(500).json({ error: e.message });
  }
});

// Export full storage state (cookies + localStorage origins) in Playwright
// storageState format, for the Walter Session Manager save/load lifecycle.
app.get('/session/state', async (req, res) => {
  try {
    const userId = String(req.query.userId || req.query.user_id || 'default');
    const session = await getSession(userId);
    const cookies = await session.context.cookies();
    const origins = [];
    for (const page of session.context.pages()) {
      const url = page.url();
      if (!url || !url.startsWith('http')) continue;
      try {
        const origin = new URL(url).origin;
        const localStorageValues = await page.evaluate(() => {
          const items = {};
          for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
          }
          return items;
        });
        const entries = Object.entries(localStorageValues)
          .filter(([, value]) => value !== null)
          .map(([name, value]) => ({ name, value }));
        if (entries.length) origins.push({ origin, localStorage: entries });
      } catch (e) {
        // page closed or cross-origin restriction: skip that page
      }
    }
    // Never echo cookie values back to logs; counts only for observability.
    res.json({
      ok: true,
      userId,
      storageState: { cookies, origins },
      stats: { cookieCount: cookies.length, originCount: origins.length },
    });
  } catch (e) {
    console.error('Error reading session state:', e);
    res.status(500).json({ error: e.message });
  }
});

setInterval(() => {
  const now = Date.now();
  for (const [key, session] of sessions) {
    if (now - session.lastAccess > SESSION_TIMEOUT_MS) {
      session.context.close().catch(() => {});
      sessions.delete(key);
      console.log(`🦊 MAX Expired session: ${key}`);
    }
  }
}, 60000);

// Health check endpoint
app.get('/health', async (req, res) => {
  const alive = await isBrowserAlive();
  res.json({ 
    ok: alive, 
    running: !!browser,
    engine: ENGINE,
    flavor: 'max',
    humanize: 2,
    geoip: true,
    persistent_context: true,
    sessions: sessions.size,
    browserConnected: alive
  });
});

// Restart browser endpoint
app.post('/restart', async (req, res) => {
  try {
    if (browser) {
      await browser.close().catch(() => {});
    }
    browser = null;
    sessions.clear();
    await ensureBrowser();
    res.json({ ok: true, message: 'Browser restarted' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

const httpServer = app.listen(PORT, HOST, () => {
  console.log(`🦊 MAX server (${ENGINE}) running on ${HOST}:${PORT}`);
  console.log(`   humanize: 2.0, geoip: true, persistent_context: true`);
  console.log(`   health: http://localhost:${PORT}/health`);
});

// Boot the browser under systemd supervision, rather than waiting for the
// first request. A failed launch makes the service fail and lets systemd
// restart it; a listening Node process with no browser is not "healthy".
ensureBrowser().catch((error) => {
  console.error('🦊 MAX startup failed:', error?.stack || error);
  httpServer.close(() => process.exit(1));
});

// Browser health check and auto-restart
// When the exit IP changes (owner's VPN on/off, exit back after an outage), relaunch the browser with the matching
// identity — only while no session is open; otherwise retry at the next check.
async function resyncExitIdentity() {
  if (!DEFAULT_PROXY || !browser || browserStartPromise) return;
  try {
    const up = await proxyReachable(DEFAULT_PROXY);
    const ip = up ? await publicIP(DEFAULT_PROXY) : null;
    if (ip === launchedExitIP) return;
    if (sessions.size > 0) {
      console.log(`🦊 MAX exit IP now ${ip || 'unreachable'} (identity built for ${launchedExitIP || 'server IP'}); relaunch deferred: ${sessions.size} session(s) open`);
      return;
    }
    console.log(`🦊 MAX exit IP changed ${launchedExitIP || 'server IP'} -> ${ip || 'unreachable'}: relaunching with matching identity`);
    await browser.close().catch(() => {});
    browser = null;
    await ensureBrowser();
  } catch (e) {
    console.log(`🦊 MAX exit identity check failed: ${e.message}`);
  }
}
if (DEFAULT_PROXY) setInterval(resyncExitIdentity, 5 * 60 * 1000).unref();

async function isBrowserAlive() {
  if (!browser) return false;
  try {
    // Try to get browser contexts - this will fail if browser is dead
    await browser.contexts();
    return true;
  } catch (e) {
    return false;
  }
}

async function ensureBrowserHealthy() {
  if (!(await isBrowserAlive())) {
    console.log('🦊 MAX Browser dead or missing, restarting...');
    browser = null;
    sessions.clear(); // Clear dead sessions
    return await ensureBrowser();
  }
  return browser;
}

// Health check every 30 seconds
setInterval(async () => {
  try {
    await ensureBrowserHealthy();
  } catch (e) {
    console.error('🦊 MAX Health check failed:', e.message);
  }
}, 30000);

// Keyboard type endpoint - types text character by character
app.post('/tab/keyboard-type', async (req, res) => {
  try {
    const { userId, tabId, text, delay = 50 } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    if (req.body.delay !== undefined) await found.tabState.page.keyboard.type(text, { delay });
    else await humanType(found.tabState.page, text);
    res.json({ ok: true, typed: text.length + ' chars' });
  } catch (e) {
    console.error('Error typing:', e);
    res.status(500).json({ error: e.message });
  }
});

// Keyboard press endpoint
app.post('/tab/keyboard-press', async (req, res) => {
  try {
    const { userId, tabId, key } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    await found.tabState.page.keyboard.press(key);
    res.json({ ok: true, key });
  } catch (e) {
    console.error('Error pressing:', e);
    res.status(500).json({ error: e.message });
  }
});

// Mouse click at coordinates
app.post('/tab/click-at', async (req, res) => {
  try {
    const { userId, tabId, x, y } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    
    await found.tabState.page.mouse.click(x, y);
    res.json({ ok: true, clicked: { x, y } });
  } catch (e) {
    console.error('Error clicking:', e);
    res.status(500).json({ error: e.message });
  }
});
