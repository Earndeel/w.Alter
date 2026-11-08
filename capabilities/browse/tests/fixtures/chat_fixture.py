"""Controlled conversational web UI for the conversation-capability tests (stdlib only).

Started by the tests on a free loopback port, never as a service. Behaviour of a real chat UI:
cookie login per user, conversations persisted server side at /c/<id> (only visible to their
owner), replies streamed token by token over a chunked HTTP response after a "thinking" pause,
a stop button visible while generating, Enter to send, error banner (role=alert) when the
login expired. Admin endpoints switch the DOM variant (site update), expire logins, change pace;
STATE["window"] keeps only the last N turns mounted (long conversations unmount old turns).
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

STATE = {"variant": "a", "token_ms": 20, "think_ms": 600, "window": 0, "sids": {}, "convs": {}}
LOCK = threading.Lock()

PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Fixture chat</title>
<style>body{font-family:sans-serif;max-width:720px;margin:auto} .bubble{padding:6px;margin:4px;border:1px solid #888}
#composer,textarea{min-height:40px;border:2px solid #01B7FF;padding:6px;display:block;width:100%}</style></head>
<body>__BODY__<script>
const VARIANT = "__VARIANT__", HISTORY = __HISTORY__, WINDOW = __WINDOW__;
let conv = __CONV__;
const A = VARIANT === "a";
const thread = document.querySelector(A ? '#thread' : 'section.log');
const input = document.querySelector(A ? '#composer' : 'textarea[name=prompt]');
const sendB = document.querySelector(A ? '[data-action=send]' : 'button.go');
const stopB = document.querySelector(A ? '[data-action=stop]' : '[data-testid=halt-generation]');
function turn(role, txt) {
  let el;
  if (A) { el = document.createElement('div'); el.className = 'turn'; el.dataset.author = role;
           const b = document.createElement('div'); b.className = 'bubble'; b.textContent = txt; el.appendChild(b); el._b = b; }
  else { el = document.createElement('article'); el.dataset.msgRole = role === 'user' ? 'human' : 'bot';
         const p = document.createElement('p'); p.textContent = txt; el.appendChild(p); el._b = p; }
  thread.appendChild(el);
  while (WINDOW && thread.children.length > WINDOW) thread.firstElementChild.remove();   // old turns unmounted
  return el;
}
for (const m of HISTORY) turn(m.role, m.text);
let ctrl = null;
function value() { return A ? input.innerText : input.value; }
function clear() { if (A) input.textContent = ''; else input.value = ''; }
async function send() {
  const text = value().trim(); if (!text || ctrl) return;
  clear(); turn('user', text);
  if (!conv) { conv = crypto.randomUUID().slice(0, 8); history.pushState({}, '', '/c/' + conv); }
  const bot = turn('assistant', ''); const dots = document.createElement('span'); dots.textContent = '…'; bot._b.appendChild(dots);
  const anim = setInterval(() => { dots.textContent = dots.textContent.length > 2 ? '.' : dots.textContent + '.'; }, 300);
  ctrl = new AbortController(); stopB.hidden = false; sendB.hidden = true;
  let first = true;
  try {
    const r = await fetch('/api/chat', {method: 'POST', body: JSON.stringify({conv, text}), signal: ctrl.signal,
                                        headers: {'Content-Type': 'application/json'}});
    if (r.status === 401) { clearInterval(anim); bot.remove(); const al = document.createElement('div');
      al.setAttribute('role', 'alert'); al.textContent = 'Session expirée, reconnectez-vous.'; document.body.appendChild(al); return; }
    const rd = r.body.getReader(), dec = new TextDecoder();
    for (;;) { const {value: chunk, done} = await rd.read(); if (done) break;
      if (first) { first = false; clearInterval(anim); dots.remove(); }
      bot._b.appendChild(document.createTextNode(dec.decode(chunk, {stream: true}))); }
  } catch (e) { /* aborted by the stop button */ }
  finally { clearInterval(anim); if (first) dots.remove(); ctrl = null; stopB.hidden = true; sendB.hidden = false; }
}
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
sendB.addEventListener('click', send);
stopB.addEventListener('click', () => ctrl && ctrl.abort());
</script></body></html>"""

BODY_A = """<main id="thread" data-thread></main>
<div id="composer" contenteditable="true" role="textbox" aria-label="Message"></div>
<button type="button" data-action="send">Envoyer</button><button type="button" data-action="stop" hidden>Arrêter</button>"""
BODY_B = """<section class="log"></section>
<textarea name="prompt" placeholder="Écrire"></textarea>
<button type="button" class="go">Envoyer</button><button type="button" data-testid="halt-generation" hidden>Stop</button>"""
SIGNED_OUT = """<!doctype html><html><body><h1>Se connecter</h1><p>Session absente.</p></body></html>"""


def reply_text(conv: dict, text: str) -> str:
    users = [m["text"] for m in conv["messages"] if m["role"] == "user"]
    n = len(users)
    prev = users[-2] if n >= 2 else "aucun"
    words = 400 if "long" in text.lower() else 14
    filler = " ".join(f"mot{i}" for i in range(words))
    return f"[{conv['id']} tour {n}] Réponse à : {text} (précédent : {prev}) {filler} FIN"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # quiet
        pass

    def _user(self):
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid":
                return STATE["sids"].get(v)
        return None

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=()):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _page(self, conv):
        hist = conv["messages"] if conv else []
        v = STATE["variant"]
        html = (PAGE.replace("__BODY__", BODY_A if v == "a" else BODY_B).replace("__VARIANT__", v)
                .replace("__HISTORY__", json.dumps(hist)).replace("__WINDOW__", str(int(STATE["window"]))).replace("__CONV__", json.dumps(conv["id"] if conv else None)))
        return html

    def do_GET(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        headers = []
        user = self._user()
        if url.path == "/" and q.get("user"):
            sid = secrets.token_hex(8)
            with LOCK:
                STATE["sids"][sid] = q["user"][0]
            user = q["user"][0]
            headers.append(("Set-Cookie", f"sid={sid}; Path=/; HttpOnly"))
        if url.path == "/health":
            return self._send(200, "ok", "text/plain")
        if not user:
            return self._send(200, SIGNED_OUT)
        if url.path == "/":
            return self._send(200, self._page(None), headers=headers)
        if url.path.startswith("/c/"):
            conv = STATE["convs"].get(url.path[3:])
            if not conv or conv["user"] != user:
                return self._send(404, "<html><body><h1>Introuvable</h1></body></html>")
            return self._send(200, self._page(conv), headers=headers)
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        url = urlsplit(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if url.path.startswith("/admin/"):
            with LOCK:
                if url.path == "/admin/variant":
                    STATE["variant"] = body["v"]
                elif url.path == "/admin/expire":
                    STATE["sids"].clear()
                elif url.path == "/admin/pace":
                    STATE.update({k: body[k] for k in ("token_ms", "think_ms") if k in body})
            return self._send(200, "{}", "application/json")
        if url.path != "/api/chat":
            return self._send(404, "not found", "text/plain")
        user = self._user()
        if not user:
            return self._send(401, '{"error":"login"}', "application/json")
        with LOCK:
            conv = STATE["convs"].setdefault(body["conv"], {"id": body["conv"], "user": user, "messages": []})
            if conv["user"] != user:
                return self._send(403, "{}", "application/json")
            conv["messages"].append({"role": "user", "text": body["text"]})
            full = reply_text(conv, body["text"])
            conv["sent"] = conv.get("sent", 0) + 1
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        time.sleep(STATE["think_ms"] / 1000)
        out = []
        try:
            for i, tok in enumerate(full.split(" ")):
                piece = (tok if i == 0 else " " + tok).encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(piece), piece))
                self.wfile.flush()
                out.append(piece.decode())
                time.sleep(STATE["token_ms"] / 1000)
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        with LOCK:
            conv["messages"].append({"role": "assistant", "text": "".join(out)})


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def reset() -> None:
    with LOCK:
        STATE.update(variant="a", token_ms=20, think_ms=600, window=0, sids={}, convs={})


if __name__ == "__main__":
    srv, port = serve(int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 0)
    print(f"http://127.0.0.1:{port}/", flush=True)
    threading.Event().wait()
