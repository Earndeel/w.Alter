"""Conversational capabilities: send a message to a web chat interface and return its reply.

A conversational recipe is an ordinary capability of the ProfileIndex registry whose
``implementation.kind`` is ``"conversation"`` (no second registry). It names, with
structural selectors (never coordinates):

    start_url   page that opens a new conversation
    engine      camoufox | chromium (same engine API, same exit rules)
    site        optional browser_sites name: owner login injected on (re)creation of the tab
    input       where the message goes          submit  {"key": "Enter"} or {"selector": css}
    user        the user's turns                reply   the service's turns
    busy        element visible while generating (null = end by quiescence)
    error       element whose appearance after submit means the service refused (default [role=alert])
    settle_ms / quiet_ms / timeout_s

Nominal path of a validated recipe = no LLM, no subprocess besides the clipboard, direct
HTTP to the engine:
    per-conversation lock → idempotency (request_id) → reuse the tab (2 ms check; recreated
    and pointed back at the conversation URL if the engine session expired) → real Ctrl+V
    paste under a clipboard lock (previous clipboard restored) → in-page MutationObserver
    armed BEFORE submit → submit → await the observer (event driven, no polling) → reply =
    the first service turn after the echo of this exact message.

Discovery (no recipe) and repair (recipe no longer matches) use deterministic DOM heuristics
recorded by the same observer, then ``register_capability`` / ``bump_capability_version``.
A message is never submitted twice for one request_id: a retry after a submit resumes
waiting on the page instead of sending again.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator, Mapping

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from profile_index import ProfileIndex
from walter_paths import state_home

ENGINES = {
    "camoufox": os.environ.get("WALTER_CAMOUFOX_URL", "http://127.0.0.1:9377"),
    "chromium": os.environ.get("WALTER_CHROMIUM_URL", "http://127.0.0.1:9378"),
}
DISPLAY = os.environ.get("WALTER_BROWSE_DISPLAY", ":101")  # X display of the engines (their units)
CHUNK_S = 45          # one awaited evaluate stays well under the engine's HTTP timeouts
KEEP_REQUESTS = 20    # idempotency log per conversation
DEFAULTS = {"engine": "camoufox", "submit": {"key": "Enter"}, "busy": None, "error": '[role="alert"]',
            "settle_ms": 150, "quiet_ms": 2000, "timeout_s": 180}


class ConversationError(RuntimeError):
    pass


class TabGone(ConversationError):
    pass


# --------------------------------------------------------------------------- engine (HTTP)

class Engine:
    """Direct HTTP to the engine (camoufox-max / cloakbrowser-max), no CLI process."""

    def __init__(self, name: str, user: str) -> None:
        if name not in ENGINES:
            raise ConversationError(f"unknown engine {name!r}")
        self.name, self.base, self.user = name, ENGINES[name], user

    def call(self, path: str, body: Mapping[str, Any] | None = None, *, timeout: float = 30) -> dict[str, Any]:
        data = json.dumps({"userId": self.user, **(body or {})}).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            if exc.code == 404:
                raise TabGone(detail) from None
            raise ConversationError(f"engine {path} HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConversationError(f"engine {path} unreachable: {exc}") from None

    def new_tab(self) -> str:
        return self.call("/tab/new", {})["tabId"]

    def navigate(self, tab: str, url: str) -> None:
        self.call("/tab/navigate", {"tabId": tab, "url": url}, timeout=60)

    def evaluate(self, tab: str, expression: str, *, timeout: float = 30) -> Any:
        return self.call("/tab/evaluate", {"tabId": tab, "expression": expression}, timeout=timeout).get("result")

    def press(self, tab: str, key: str) -> None:
        self.call("/tab/keyboard-press", {"tabId": tab, "key": key})

    def type_fast(self, tab: str, text: str) -> None:
        self.call("/tab/keyboard-type", {"tabId": tab, "text": text, "delay": 0}, timeout=60)


# --------------------------------------------------------------------------- in-page library

# Installed once per page (idempotent); every call is one evaluate. Promises are awaited by
# the engine, so waiting is a MutationObserver resolving a promise: no polling from Python.
_JS = r"""
(() => {
const V = 11;
if (window.__wc && window.__wc.v === V) return window.__wc;
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const vis = el => { if (!el || !el.isConnected) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const text = el => el ? (el.innerText ?? el.textContent ?? '') : '';
const qa = sel => { if (!sel) return []; try { return Array.from(document.querySelectorAll(sel)); } catch (e) { return []; } };
const follows = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
const stable = v => v && v.length <= 40 && !/\d|[:\s]|^_/.test(v);   // no index, id or framework key
const stableClass = c => /^[a-zA-Z][a-zA-Z_-]{1,30}$/.test(c) && !/^(css|sc|jsx|tw)-/.test(c);
function cands(el) {          // structural selectors for el, most specific first; never coordinates
  const out = [], tag = el.tagName.toLowerCase();
  if (el.id && stable(el.id)) out.push('#' + CSS.escape(el.id));
  const data = [...el.attributes].filter(a => a.name.startsWith('data-') && a.name !== 'data-ref');
  // attribute=value first (data-message-role="assistant"), bare attribute names after
  for (const a of data) if (stable(a.value)) out.push(`${tag}[${a.name}="${CSS.escape(a.value)}"]`);
  for (const a of data) out.push(`${tag}[${a.name}]`);
  const role = el.getAttribute('role');
  if (role) out.push(`${tag}[role="${role}"]` + (el.isContentEditable ? '[contenteditable="true"]' : ''));
  if (el.isContentEditable && !role) out.push(`${tag}[contenteditable="true"]`);
  for (const c of el.classList) if (stableClass(c)) out.push(`${tag}.${CSS.escape(c)}`);
  if (['textarea', 'main', 'article'].includes(tag)) out.push(tag);
  return out;
}
function findInput(sel) {
  let list = sel ? qa(sel) : qa('[contenteditable="true"][role="textbox"], textarea, [contenteditable="true"], input[type="text"], input:not([type])');
  list = list.filter(e => vis(e) && !e.disabled && !e.readOnly);
  if (!list.length) return null;
  if (sel) return list[list.length - 1];
  return list.sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0];
}
function inputValue(el) { return el ? ('value' in el && el.tagName !== 'DIV' ? el.value : text(el)) : ''; }
const R = {};                 // per-request state
const wc = { v: V, R };
wc.prepare = (cfg) => {       // find + focus + select the input so the paste replaces it
  const el = findInput(cfg.input);
  if (!el) return { ok: false, reason: 'input_not_found' };
  el.focus();
  if ('select' in el && el.tagName !== 'DIV') el.select();
  else { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
  let inputSel = cfg.input;
  if (!inputSel) inputSel = cands(el).find(s => findInput(s) === el) || null;
  return { ok: true, input: inputSel, href: location.href, users: qa(cfg.user).length, replies: qa(cfg.reply).length };
};
wc.inputText = (cfg) => norm(inputValue(findInput(cfg.input)));
wc.buttons = () => {          // attribute selectors of the visible buttons; the label too (a stop button often has only that)
  const s = new Set();
  for (const b of qa('button, [role="button"]')) if (vis(b)) {
    for (const c of cands(b)) if (c.includes('[')) s.add(c);
    const l = b.getAttribute('aria-label');
    if (l && l.length <= 40) s.add(`${b.tagName.toLowerCase()}[aria-label="${CSS.escape(l)}"]`);
  }
  return s; };
wc.arm = (id, cfg, msg, resume) => {    // install the observer BEFORE submit
  wc.forget(id);
  const st = R[id] = { id, cfg, msg: norm(msg), t0: performance.now(), submitAt: null, firstAt: null, doneAt: null,
    lastMut: performance.now(), added: [], echo: null, reply: null, mode: null, state: 'pending', resume: !!resume,
    oldUsers: new Set(qa(cfg.user)), before: wc.buttons(), during: null, input: findInput(cfg.input),
    errBefore: new Set(qa(cfg.error).filter(vis)), error: null };
  // the echo is a user element that did not exist at arm time, never found by counting: chat UIs unmount
  // old turns of long conversations (ChatGPT keeps ~7 mounted), so the count can stay the same after a send
  if (resume) { const u = qa(cfg.user); if (u.length) st.oldUsers.delete(u[u.length - 1]); }
  st.done = new Promise(res => { st.resolve = res; });
  const finish = (state) => { if (st.state !== 'pending') return; st.state = state; st.doneAt = performance.now(); st.obs.disconnect(); clearTimeout(st.timer); st.resolve(state); };
  st.finish = finish;
  const recipeEcho = () => {
    const users = qa(cfg.user);
    for (let i = users.length - 1; i >= 0; i--) { if (st.oldUsers.has(users[i])) continue; const t = norm(text(users[i])); if (t === st.msg || (st.msg.length > 60 && t.startsWith(st.msg.slice(0, 60)))) return users[i]; }
    return null;
  };
  const genericEcho = () => {
    let best = null;
    for (const root of st.added) {
      if (!root.isConnected || (st.input && (st.input.contains(root) || root.contains(st.input)))) continue;
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT); let n = root;
      while (n) { if (norm(text(n)) === st.msg) best = n; n = w.nextNode(); }
      if (best) return best;
    }
    return null;
  };
  const genericReply = (echo) => {
    // The reply sits between the echo and the composer: page chrome below the composer (disclaimers,
    // footers re-rendered on the conversation view) is never a reply.
    const inp = findInput(cfg.input) || (st.input && st.input.isConnected ? st.input : null);
    const below = inp && follows(echo, inp);
    let best = null, len = 0;
    for (const el of st.added) {
      if (!el.isConnected || el.contains(echo) || echo.contains(el) || !follows(echo, el)) continue;
      if (inp && (inp.contains(el) || el.contains(inp))) continue;
      if (below && follows(inp, el)) continue;
      const l = norm(text(el)).length; if (l > len) { best = el; len = l; }
    }
    return best;
  };
  const check = () => {
    if (st.state !== 'pending') return;
    let echo = null, reply = null, mode = 'recipe';
    if (cfg.user && cfg.reply) {
      echo = recipeEcho();
      if (echo) reply = qa(cfg.reply).find(r => follows(echo, r) && !r.contains(echo)) || null;
    }
    if (!echo || !reply) { mode = 'generic'; echo = genericEcho(); reply = echo ? genericReply(echo) : null; }
    st.echo = echo; st.reply = reply; st.mode = mode;
    const t = reply ? norm(text(reply)) : '';
    // first real content (a '…' placeholder is not a token)
    if (st.firstAt === null && /[\p{L}\p{N}]/u.test(t)) {
      st.firstAt = performance.now(); st.during = wc.buttons();
      st.earlyReply = wc.around(reply, echo); st.earlyUser = wc.around(echo, reply);   // selectors true DURING generation
    }
    if (st.cancel) return finish('cancelled');
    const err = qa(cfg.error).find(e => vis(e) && !st.errBefore.has(e) && norm(text(e)));
    if (err) { st.error = norm(text(err)).slice(0, 200); return finish('error'); }
    if (!t) return;
    if (cfg.busy && qa(cfg.busy).some(vis)) { st.busySeen = true; return; }   // still generating
    // short settle only once the recipe's busy element was really seen this exchange; a busy selector
    // the site no longer matches (update, other locale) falls back to quiescence instead of cutting the reply
    const wait = (mode === 'recipe' && cfg.busy && st.busySeen) ? cfg.settle_ms : cfg.quiet_ms;
    clearTimeout(st.timer);
    st.timer = setTimeout(() => { if (performance.now() - st.lastMut >= wait - 5) finish('done'); else check(); }, Math.max(0, wait - (performance.now() - st.lastMut)));
  };
  st.check = check;
  st.obs = new MutationObserver(muts => {
    let content = false;
    for (const m of muts) {
      if (m.type !== 'attributes') content = true;
      for (const n of m.addedNodes) if (n.nodeType === 1) { if (st.added.length < 3000) st.added.push(n); }
    }
    if (content) st.lastMut = performance.now();
    check();
  });
  st.obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden', 'disabled', 'aria-busy', 'data-state'] });
  if (resume) {               // resuming after a submit: the echo is already on the page
    const all = Array.from(document.body.querySelectorAll('*'));
    st.added = all.filter(e => e.children.length < 50).slice(-3000);
  }
  check();
  return { armed: true, oldUsers: st.oldUsers.size };
};
wc.submitted = (id) => { const st = R[id]; if (st) st.submitAt = performance.now(); return true; };
wc.wait = (id, ms) => {
  const st = R[id]; if (!st) return { state: 'unknown' };
  return Promise.race([st.done, new Promise(r => setTimeout(() => r('pending'), ms))]).then(() => wc.status(id));
};
wc.status = (id) => {
  const st = R[id]; if (!st) return { state: 'unknown' };
  const base = st.submitAt ?? st.t0;
  const busy = st.cfg.busy ? qa(st.cfg.busy).some(vis) : null;
  return { state: st.state, mode: st.mode, echo: !!st.echo, busy, busy_seen: !!st.busySeen, reply: st.reply ? text(st.reply).trim() : '', error: st.error,
           first_token_ms: st.firstAt === null ? null : Math.round(st.firstAt - base),
           generation_ms: Math.round((st.doneAt ?? performance.now()) - base), href: location.href };
};
// Elements carrying exactly the same text as `el` (the message itself, not page chrome), outermost first.
wc.same = (el, other) => {
  const T = norm(text(el)), up = [];
  for (let e = el; e && e !== document.body && !e.contains(other) && norm(text(e)) === T; e = e.parentElement) up.unshift(e);
  const down = Array.from(el.querySelectorAll('*')).filter(e => norm(text(e)) === T).slice(0, 200);
  return [...up, ...down];
};
wc.around = (el, other) => { const s = new Set(); if (el && other) for (const e of wc.same(el, other)) for (const c of cands(e)) s.add(c); return s; };
wc.learn = (id) => {          // post-hoc selectors from the observed exchange (discovery / repair)
  const st = R[id]; if (!st || !st.echo || !st.reply) return null;
  const pick = (start, other, early, isReply) => {
    const els = wc.same(start, other);
    for (const pass of [s => s.includes('="'), s => s.includes('['), s => true]) {   // attribute=value first
      for (const el of els) for (const s of cands(el)) {
        if (!pass(s) || (early && early.size && !early.has(s))) continue;
        const m = qa(s);
        if (!m.includes(el) || m.some(x => x.contains(other) || other.contains(x))) continue;
        if (isReply && m.find(r => follows(other, r)) !== el) continue;   // replay takes the first reply after the echo
        return s;
      }
    }
    return null;
  };
  const user = pick(st.echo, st.reply, st.earlyUser, false), reply = pick(st.reply, st.echo, st.earlyReply, true);
  let busy = null;
  if (st.during) {      // a button shown only while generating; one that says stop/cancel first
    const after = wc.buttons(), only = [...st.during].filter(s => !st.before.has(s) && !after.has(s));
    busy = only.find(s => /stop|cancel|abort|interrupt/i.test(s)) || only[0] || null;
  }
  return { user, reply, busy };
};
wc.cancel = () => {
  for (const st of Object.values(R)) if (st.state === 'pending') {
    st.cancel = true;
    const b = st.cfg.busy && qa(st.cfg.busy).find(vis); if (b) b.click();
    st.check();
  }
  return true;
};
wc.forget = (id) => { const st = R[id]; if (st) { try { st.obs.disconnect(); } catch (e) {} delete R[id]; } return true; };
window.__wc = wc;
return wc;
})()
"""


def _js(call: str) -> str:
    return "(() => { const wc = " + _JS.strip() + "; return " + call + "; })()"


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# --------------------------------------------------------------------------- state + locks

@contextlib.contextmanager
def _flock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _state_dir() -> Path:
    return state_home() / "conversations"


def _conv_key(host: str, capability: str, session: str, conversation: str) -> str:
    return hashlib.sha1(f"{host}\0{capability}\0{session}\0{conversation}".encode()).hexdigest()[:20]


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(tmp, path)


def _record(state: dict[str, Any], request_id: str, **fields: Any) -> dict[str, Any]:
    reqs = state.setdefault("requests", [])
    rec = next((r for r in reqs if r.get("id") == request_id), None)
    if rec is None:
        rec = {"id": request_id, "created_at": time.time()}
        reqs.append(rec)
    rec.update(fields, updated_at=time.time())
    reqs[:] = reqs[-KEEP_REQUESTS:]
    return rec


# --------------------------------------------------------------------------- clipboard paste

def _xclip(args: list[str], data: bytes | None = None) -> bytes | None:
    env = {**os.environ, "DISPLAY": DISPLAY}
    if data is None:
        out = subprocess.run(["xclip", "-selection", "clipboard", *args], env=env, capture_output=True, timeout=3)
        return out.stdout if out.returncode == 0 else None
    # -i forks a selection owner: its stdio must not be our pipes or run() would wait on it.
    subprocess.run(["xclip", "-selection", "clipboard", *args], env=env, input=data,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=True)
    return None


def _paste(engine: Engine, tab: str, cfg: Mapping[str, Any], message: str) -> str:
    """Real Ctrl+V under the clipboard lock; previous clipboard restored. Returns the method used."""
    want = _norm(message)
    with _flock(_state_dir() / "clipboard.lock"):
        previous = None
        try:
            previous = _xclip(["-o"])
            _xclip(["-i"], message.encode())
            engine.press(tab, "Control+V")
            if engine.evaluate(tab, _js(f"wc.inputText({_j(dict(cfg))})")) == want:
                return "paste"
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                _xclip(["-i"], previous or b"")
    # Fallback (no clipboard on this display): one fast keyboard insertion, never human-paced.
    prep = engine.evaluate(tab, _js(f"wc.prepare({_j(dict(cfg))})"))
    if prep and prep.get("ok"):
        engine.type_fast(tab, message)
        if engine.evaluate(tab, _js(f"wc.inputText({_j(dict(cfg))})")) == want:
            return "keyboard"
    raise ConversationError("input_not_filled")


# --------------------------------------------------------------------------- tab

def _login(site: str, session: str, engine: str) -> None:
    """Owner login through the declared core command (cookies injected server side)."""
    subprocess.run(["walter-browser", "-e", engine, "-s", session, "login", site],
                   capture_output=True, timeout=120, check=False)


def _drop_tab(engine: Engine, state: dict[str, Any]) -> None:
    tab = state.pop("tab", None)
    if tab:
        with contextlib.suppress(ConversationError):
            engine.call("/tab/close", {"tabId": tab}, timeout=10)


def _ensure_tab(engine: Engine, state: dict[str, Any], cfg: Mapping[str, Any], session: str) -> tuple[str, bool]:
    """Reuse the conversation's tab; recreate it (expired engine session) at the conversation URL."""
    tab = state.get("tab")
    target = state.get("url") or cfg["start_url"]
    if tab:
        try:
            href = engine.evaluate(tab, "location.href", timeout=10)
            if href == target or (not state.get("url") and href):
                return tab, False
            engine.navigate(tab, target)
            return tab, True
        except TabGone:
            pass
    if cfg.get("site"):
        _login(cfg["site"], session, engine.name)
    tab = engine.new_tab()
    engine.navigate(tab, cfg["start_url"])
    if target != cfg["start_url"]:
        engine.navigate(tab, target)
    state["tab"] = tab
    return tab, True


# --------------------------------------------------------------------------- main entry

def _host_of(url: str) -> str:
    from profile_index import _normalized_host  # same normalization as the registry
    return _normalized_host(url)


def send(
    host: str | None,
    capability: str,
    message: str,
    *,
    conversation: str = "default",
    request_id: str | None = None,
    session: str | None = None,
    start_url: str | None = None,
    site: str | None = None,
    index: ProfileIndex | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Send ``message`` in a conversation and return the normalized result (never raises)."""
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    mark = lambda name, since: timings.__setitem__(name, round((time.perf_counter() - since) * 1000, 1))  # noqa: E731
    index = index or ProfileIndex()
    host = host or (_host_of(start_url) if start_url else "")
    request_id = request_id or uuid.uuid4().hex
    session = session or "conv-" + re.sub(r"[^a-z0-9.-]+", "-", host.lower())
    result: dict[str, Any] = {"ok": False, "status": "failed", "reply": "", "host": host, "capability": capability,
                              "conversation": conversation, "request_id": request_id, "transport": "browser",
                              "session": session, "mode": None, "recipe_version": None, "error": None}
    cap = index.lookup_capability(host, capability) if host else None
    impl = (cap or {}).get("implementation") or {}
    if impl.get("kind") == "conversation":
        cfg = {**DEFAULTS, **impl}
        result["recipe_version"] = cap.get("version")
        mode = "replay"
    elif start_url:
        cfg = {**DEFAULTS, "kind": "conversation", "start_url": start_url, "site": site,
               "input": None, "user": None, "reply": None}
        mode = "discovery"
    else:
        result["error"] = "unknown_conversational_capability"
        return result
    if timeout_s:
        cfg["timeout_s"] = timeout_s
    result["engine"] = cfg["engine"]
    key = _conv_key(host, capability, session, conversation)
    state_path = _state_dir() / f"{key}.json"
    engine = Engine(cfg["engine"], session)
    t = time.perf_counter()
    with _flock(_state_dir() / f"{key}.lock"):
        mark("lock_ms", t)
        state = _load(state_path)
        state.update(host=host, capability=capability, session=session, conversation=conversation, engine=cfg["engine"])
        rec = next((r for r in state.get("requests", []) if r.get("id") == request_id), None)
        if rec and rec.get("status") == "done":   # idempotent: same request → same answer, nothing resent
            result.update(ok=True, status="done", reply=rec.get("reply", ""), duplicate=True, url=state.get("url"),
                          mode="log", timings={"total_ms": round((time.perf_counter() - t0) * 1000, 1)})
            return result
        if rec and rec.get("submitted") and rec.get("status") in ("error", "cancelled"):
            # Terminal after a submit: never resent under the same request_id (the caller decides).
            result.update(status=rec["status"], duplicate=True, error="already_" + rec["status"], mode="log")
            return result
        resume = bool(rec and rec.get("submitted"))
        try:
            t = time.perf_counter()
            tab, fresh_tab = _ensure_tab(engine, state, cfg, session)
            mark("tab_ms", t)
            result["tab_reused"] = not fresh_tab
            persist = lambda: _save(state_path, state)  # noqa: E731
            try:
                out = _exchange(engine, tab, cfg, message, request_id, state, resume, timings, persist)
            except ConversationError as exc:
                if fresh_tab or str(exc) != "input_not_found":
                    raise
                _drop_tab(engine, state)        # recovery: new tab, site login, back to the conversation
                t = time.perf_counter()
                tab, fresh_tab = _ensure_tab(engine, state, cfg, session)
                mark("recovery_ms", t)
                result["recovered"] = True
                out = _exchange(engine, tab, cfg, message, request_id, state, resume, timings, persist)
        except ConversationError as exc:
            result["error"] = str(exc)[:300]
            out = None
        if out is not None:
            status = out["status"]
            result.update(status=status["state"], reply=status["reply"], url=status.get("href"),
                          resumed=resume, input_method=out.get("input_method"), match=status.get("mode"),
                          busy_seen=status.get("busy_seen"))
            # On a resume the generation started in an earlier call: only its remaining part is measured.
            timings["first_token_ms"] = None if resume else status.get("first_token_ms")
            timings["generation_ms"] = status.get("generation_ms")
            result["ok"] = status["state"] == "done" and bool(status["reply"])
            if status["state"] == "error":
                result["error"] = "service_error: " + (status.get("error") or "")
                _drop_tab(engine, state)        # next request re-establishes the page (login, conversation URL)
            elif status["state"] == "done" and not status["reply"]:
                result["error"] = "empty_reply"
            elif status["state"] == "pending":
                result["status"] = "incomplete"
                result["error"] = "timeout"
            learned = out.get("learned")
            # Recipe bookkeeping: discovery registers, a recipe that missed is repaired (new version).
            if result["ok"] and (mode == "discovery" or status.get("mode") == "generic"):
                new_impl = {k: cfg[k] for k in ("kind", "engine", "start_url", "submit", "error", "settle_ms", "quiet_ms", "timeout_s") if k in cfg}
                new_impl.update(site=cfg.get("site"), input=out.get("input") or cfg.get("input"),
                                user=(learned or {}).get("user"), reply=(learned or {}).get("reply"),
                                busy=(learned or {}).get("busy") or None)
                if new_impl["input"] and new_impl["user"] and new_impl["reply"]:
                    if mode == "discovery":
                        if cap is None:
                            cap = index.register_capability(host, capability, inputs={"message": "text"},
                                                            outputs={"reply": "text"}, implementation=new_impl)
                        else:
                            cap = index.bump_capability_version(host, capability, implementation=new_impl, notes="conversation discovery")
                    else:
                        cap = index.bump_capability_version(host, capability, implementation=new_impl, notes="conversation repair")
                        mode = "repair"
                    result["recipe_version"] = (cap or {}).get("version")
                    result["learned"] = new_impl
            if cap is not None and status["state"] in ("done", "pending"):
                index.observe_capability(host, capability, success=result["ok"], latency_ms=timings.get("generation_ms") or 0)
            if result["url"] and result["ok"]:
                state["url"] = result["url"]
            reqfields = {"status": result["status"], "submitted": True}
            if result["ok"]:
                reqfields["reply"] = result["reply"]
            _record(state, request_id, **reqfields)
        elif cap is not None and impl.get("kind") == "conversation":
            index.observe_capability(host, capability, success=False, latency_ms=0)
        _save(state_path, state)
    result["mode"] = mode
    total = round((time.perf_counter() - t0) * 1000, 1)
    timings["total_ms"] = total
    if timings.get("generation_ms") is not None:
        # External time = from submit to the end condition minus our own settle window.
        settle = cfg["settle_ms"] if (result.get("busy_seen") and result.get("match") == "recipe") else cfg["quiet_ms"]
        timings["settle_ms"] = settle
        timings["external_ms"] = max(0.0, timings["generation_ms"] - settle)
        timings["walter_ms"] = round(total - timings["external_ms"], 1)
    result["timings"] = timings
    return result


def _exchange(engine: Engine, tab: str, cfg: dict[str, Any], message: str, request_id: str,
              state: dict[str, Any], resume: bool, timings: dict[str, float], persist: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if resume:
        engine.evaluate(tab, _js(f"wc.arm({_j(request_id)}, {_j(cfg)}, {_j(message)}, true)"))
        engine.evaluate(tab, _js(f"wc.submitted({_j(request_id)})"))
        first = engine.evaluate(tab, _js(f"wc.wait({_j(request_id)}, 1500)"), timeout=20) or {}
        if not first.get("echo"):
            # The submit never reached the page: safe to send now (no duplicate possible).
            engine.evaluate(tab, _js(f"wc.forget({_j(request_id)})"))
            resume = False
        else:
            out["status"] = first
    if not resume:
        t = time.perf_counter()
        prep = engine.evaluate(tab, _js(f"wc.prepare({_j(cfg)})"))
        if not (prep or {}).get("ok") and cfg.get("input"):
            # Recipe input selector broken: rediscover the input, the rest is repaired after the reply.
            cfg["input"] = None
            prep = engine.evaluate(tab, _js(f"wc.prepare({_j(cfg)})"))
        if not (prep or {}).get("ok"):
            raise ConversationError((prep or {}).get("reason") or "input_not_found")
        if not cfg.get("input"):
            cfg["input"] = prep.get("input")
            out["input"] = prep.get("input")
        out["input_method"] = _paste(engine, tab, cfg, message)
        mark_input = time.perf_counter()
        timings["input_ms"] = round((mark_input - t) * 1000, 1)
        _record(state, request_id, status="prepared", submitted=False)
        engine.evaluate(tab, _js(f"wc.arm({_j(request_id)}, {_j(cfg)}, {_j(message)}, false)"))
        # Recorded as submitted BEFORE the key press: a crash after it can only resume, never resend.
        _record(state, request_id, status="submitted", submitted=True)
        persist()
        engine.evaluate(tab, _js(f"wc.submitted({_j(request_id)})"))
        submit = cfg.get("submit") or {"key": "Enter"}
        if submit.get("selector"):
            engine.evaluate(tab, f"(() => {{ const b = document.querySelector({_j(submit['selector'])}); if (b) b.click(); return !!b; }})()")
        else:
            engine.press(tab, submit.get("key", "Enter"))
        timings["submit_ms"] = round((time.perf_counter() - mark_input) * 1000, 1)
    deadline = time.monotonic() + float(cfg["timeout_s"])
    status = out.get("status") or {"state": "pending"}
    while status.get("state") == "pending" and time.monotonic() < deadline:
        chunk_ms = int(min(CHUNK_S, max(0.5, deadline - time.monotonic())) * 1000)
        status = engine.evaluate(tab, _js(f"wc.wait({_j(request_id)}, {chunk_ms})"), timeout=chunk_ms / 1000 + 15) or {"state": "unknown"}
    t = time.perf_counter()
    if status.get("state") == "done" and (status.get("mode") == "generic" or not cfg.get("user")):
        out["learned"] = engine.evaluate(tab, _js(f"wc.learn({_j(request_id)})"))
    if status.get("state") != "pending":
        engine.evaluate(tab, _js(f"wc.forget({_j(request_id)})"))
    timings["extract_ms"] = round((time.perf_counter() - t) * 1000, 1)
    out["status"] = status
    return out


def cancel(host: str, capability: str, *, conversation: str = "default", session: str | None = None,
           engine_name: str = "camoufox") -> bool:
    """Stop the pending generation of a conversation (clicks the recipe's busy/stop element)."""
    session = session or "conv-" + re.sub(r"[^a-z0-9.-]+", "-", host.lower())
    state = _load(_state_dir() / f"{_conv_key(host, capability, session, conversation)}.json")
    if not state.get("tab"):
        return False
    try:
        return bool(Engine(state.get("engine", engine_name), session).evaluate(state["tab"], _js("wc.cancel()")))
    except ConversationError:
        return False


def close(host: str, capability: str, *, conversation: str = "default", session: str | None = None) -> bool:
    """Close the conversation's tab (the conversation URL is kept: it can be resumed later)."""
    session = session or "conv-" + re.sub(r"[^a-z0-9.-]+", "-", host.lower())
    path = _state_dir() / f"{_conv_key(host, capability, session, conversation)}.json"
    state = _load(path)
    tab = state.pop("tab", None)
    if tab:
        with contextlib.suppress(ConversationError):
            Engine(state.get("engine", "camoufox"), session).call("/tab/close", {"tabId": tab})
        _save(path, state)
    return bool(tab)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Walter Browse — conversational capability")
    ap.add_argument("message")
    ap.add_argument("--host")
    ap.add_argument("--capability", default="chat")
    ap.add_argument("--conversation", default="default")
    ap.add_argument("--session")
    ap.add_argument("--request-id")
    ap.add_argument("--start-url", help="discovery: page of a new conversation (no recipe yet)")
    ap.add_argument("--site", help="discovery: browser_sites name whose owner login the tab needs")
    ap.add_argument("--timeout", type=float)
    a = ap.parse_args(argv)
    out = send(a.host, a.capability, a.message, conversation=a.conversation, request_id=a.request_id,
               session=a.session, start_url=a.start_url, site=a.site, timeout_s=a.timeout)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
