"""Decision bench, web page (2026-11-13): the owner labels the cases with buttons in a browser, blind.

Temporary door, asked by the owner: one page, tailnet address only (never public), started as a transient systemd
unit and stopped once the labels are in. Same state as the Telegram buttons (decision_bench.record): either door
can be used, answers can be changed until the owner asks to see the models' answers to that case: they are shown
only for a case he has answered (or skipped), and his answers to it freeze from then (decision_bench.reveal).
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from walter_router.eval import decision_bench as bench


def cases_view() -> dict:
    cases = bench._read("cases.json", {}).get("cases") or []
    labels = bench._read("labels.json", {})
    out = []
    for no, c in enumerate(cases):
        crit_of = lambda k: (c["questions"].get(k) or {}).get("criteria") or {}  # noqa: E731
        lab = labels.get(c["id"], {})
        out.append({
            "no": no, "level": c["level"], "level_name": bench.LEVEL_NAMES[c["level"]],
            "source": "votre message" if c.get("source") != "fictif" else "fictif",
            "context": "\n".join(bench.context_lines(c)),
            "questions": [{"key": k, "text": text, "answer": lab.get(k, "__none__"),
                           "options": [{"value": v, "label": label,
                                        "help": crit_of(k).get(v) if isinstance(crit_of(k).get(v), str) else ""}
                                       for v, label in opts]}
                          for k, text, opts in bench.labelled_questions(c)],
            "done": bool(lab.get("_done")), "skipped": bool(lab.get("_skipped")),
            "revealed": bool(lab.get("_revealed"))})
    return {"cases": out}


def label(body: dict) -> dict:
    no = int(body["no"])
    if body.get("skip"):
        return bench.record(no, None, None, skip=True)
    oi = body.get("oi")
    qi = int(body["qi"])
    if "key" in body:          # the page names the question: a page loaded before a question list change is refused
        keys = [k for k, _, _ in bench.labelled_questions(bench._read("cases.json", {})["cases"][no])]
        if qi >= len(keys) or keys[qi] != body["key"]:
            raise ValueError("stale page")
    return bench.record(no, qi, None if oi is None else int(oi))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/cases":
            return self._send(200, json.dumps(cases_view(), ensure_ascii=False).encode(), "application/json")
        self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        if self.path not in ("/api/label", "/api/reveal"):
            return self._send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 4096:
            return self._send(413, b"too large", "text/plain")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            out = label(body) if self.path == "/api/label" else bench.reveal(int(body["no"]))
        except bench.RevealedError:
            return self._send(409, b'{"ok": false, "frozen": true}', "application/json")
        except (KeyError, ValueError, IndexError, TypeError):
            return self._send(400, b'{"ok": false}', "application/json")
        self._send(200, json.dumps({"ok": True, **out}, ensure_ascii=False).encode(), "application/json")

    def log_message(self, *a):  # the page carries the owner's own messages: no request log
        pass


def serve(host: str, port: int) -> None:
    ThreadingHTTPServer((host, port), Handler).serve_forever()


PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Banc de décision</title>
<style>
:root{--b:#01B7FF}
*{box-sizing:border-box}
body{margin:0;background:#000;color:#e8e8e8;font:16px/1.45 -apple-system,system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:16px}
header{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
h1{font-size:18px;margin:0;color:var(--b)}
.bar{height:6px;border:2px solid var(--b);border-radius:6px;margin:10px 0 16px}
.bar>div{height:100%;background:var(--b)}
.meta{color:#9aa;font-size:14px}
.ctx{white-space:pre-wrap;border:2px solid var(--b);border-radius:10px;padding:12px;margin:12px 0 18px;background:#050b10}
.q{margin:0 0 18px}
.q h2{font-size:16px;margin:0 0 8px}
.opts{display:flex;flex-wrap:wrap;gap:8px}
button{background:#000;color:#e8e8e8;border:2px solid #2a3a44;border-radius:10px;padding:9px 13px;font:inherit;cursor:pointer;text-align:left}
button:hover{border-color:var(--b)}
button.on{border-color:var(--b);background:#01B7FF22;color:#fff}
button small{display:block;color:#8a9aa4;font-size:12px;max-width:340px}
nav{display:flex;gap:8px;justify-content:space-between;margin-top:22px;flex-wrap:wrap}
nav button{min-width:120px;text-align:center}
.ok{color:var(--b)}
.dots{display:flex;flex-wrap:wrap;gap:4px;margin-top:20px}
.dots span{width:14px;height:14px;border:2px solid #2a3a44;border-radius:4px;cursor:pointer}
.dots span.d{background:var(--b);border-color:var(--b)}
.dots span.s{background:#444}
.dots span.c{outline:2px solid #fff}
.dots span.r{box-shadow:inset 0 0 0 3px #000}
button:disabled{opacity:.55;cursor:default}
#reveal{margin-top:14px;width:100%;text-align:center;border-color:var(--b)}
.models{margin-top:14px}
.m{border:2px solid #2a3a44;border-radius:10px;padding:10px 12px;margin:0 0 10px}
.m h3{margin:0 0 6px;font-size:15px;color:var(--b)}
.m div{font-size:14px}
.y{color:#3ddc84}.n{color:#ff5c5c}.u{color:#9aa}
</style></head><body><main>
<header><h1>Banc de décision</h1><span class="meta" id="count"></span></header>
<div class="bar"><div id="prog" style="width:0"></div></div>
<div id="case"></div>
<div id="rev"></div>
<nav><button id="prev">← Précédent</button><button id="skip">Passer ce cas</button><button id="next">Suivant →</button></nav>
<div class="dots" id="dots"></div>
<p class="meta">Répondez d'abord ; le bouton « Voir les réponses des modèles » apparaît ensuite (vos réponses à ce cas sont alors figées). « ? » = je ne sais pas. Chaque clic est enregistré.</p>
</main>
<script>
let cases=[],cur=0;
const $=id=>document.getElementById(id);
function el(tag,attrs,...kids){const e=document.createElement(tag);Object.assign(e,attrs||{});kids.forEach(k=>e.append(k));return e}
async function load(){cases=(await (await fetch('/api/cases')).json()).cases;const f=cases.findIndex(c=>!c.done);cur=f<0?0:f;draw()}
function draw(){
  const done=cases.filter(c=>c.done).length;$('count').textContent=done+' / '+cases.length+' cas';
  $('prog').style.width=(100*done/cases.length)+'%';
  const c=cases[cur],box=$('case');box.innerHTML='';
  box.append(el('div',{className:'meta',textContent:'Cas '+(cur+1)+' / '+cases.length+' · '+c.level_name+' · '+c.source+(c.skipped?' · passé':c.done?' · fait':'')}));
  box.append(el('div',{className:'ctx',textContent:c.context}));
  c.questions.forEach((q,qi)=>{
    const opts=el('div',{className:'opts'});
    q.options.forEach((o,oi)=>{const b=el('button',{className:q.answer===o.value?'on':''},o.label);
      if(o.help&&o.help!==o.label)b.append(el('small',{textContent:o.help}));b.onclick=()=>answer(qi,oi);opts.append(b)});
    const x=el('button',{className:q.answer===null?'on':''},'?');x.onclick=()=>answer(qi,null);opts.append(x);
    if(c.revealed)opts.querySelectorAll('button').forEach(b=>b.disabled=true);
    box.append(el('div',{className:'q'},el('h2',{textContent:(qi+1)+'. '+q.text}),opts))});
  const rev=$('rev');rev.innerHTML='';
  if(c.shown)showModels(c);
  else if(c.revealed){reveal()}
  else if(c.done){const b=el('button',{id:'reveal'},'Voir les réponses des modèles');
    b.append(el('small',{textContent:'Vos réponses à ce cas seront figées ensuite'}));b.onclick=reveal;rev.append(b)}
  const dots=$('dots');dots.innerHTML='';
  cases.forEach((k,i)=>{const d=el('span',{className:(k.skipped?'s':k.done?'d':'')+(k.revealed?' r':'')+(i===cur?' c':''),title:'Cas '+(i+1)});d.onclick=()=>{cur=i;draw()};dots.append(d)});
}
async function post(body){const r=await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(r.status===409){alert('Réponses des modèles déjà vues : la vôtre reste celle donnée avant');return null}if(!r.ok){alert('Non enregistré : rechargez la page');return null}return r.json()}
async function reveal(){const c=cases[cur],r=await fetch('/api/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({no:c.no})});
  if(!r.ok){alert('Répondez d\'abord au cas');return}c.shown=await r.json();c.revealed=true;draw()}
function showModels(c){
  const rev=$('rev'),d=c.shown,box=el('div',{className:'models'});
  const qs=c.questions;
  box.append(el('div',{className:'meta',textContent:'Réponses des modèles (majorité de leurs essais · accord · confiance). Vert = comme vous, rouge = différent, gris = vous avez répondu « ? ».'}));
  d.models.forEach(m=>{const card=el('div',{className:'m'},el('h3',{textContent:m.model+(m.ms?' · '+m.ms+' ms':'')+(m.failures?' · '+m.failures+' échec(s)':'')}));
    m.questions.forEach((q,i)=>{const cls=q.match===true?'y':q.match===false?'n':'u';
      card.append(el('div',{className:cls,textContent:(i+1)+'. '+(q.label??'pas de réponse')+(q.of?'  ('+q.agree+'/'+q.of+(q.confidence!=null?' · '+Math.round(q.confidence*100)+' %':'')+')':'')}))});
    box.append(card)});
  rev.append(box)}
async function answer(qi,oi){
  const c=cases[cur],r=await post({no:c.no,qi,oi,key:c.questions[qi].key});if(!r)return;
  c.questions.forEach(q=>{q.answer=(q.key in r.labels)?r.labels[q.key]:'__none__'});
  const was=c.done;c.done=r.done;c.skipped=false;
  draw()}
$('prev').onclick=()=>{if(cur>0){cur--;draw();window.scrollTo(0,0)}};
$('next').onclick=()=>{if(cur<cases.length-1){cur++;draw();window.scrollTo(0,0)}};
$('skip').onclick=async()=>{const c=cases[cur],r=await post({no:c.no,skip:true});if(!r)return;c.done=true;c.skipped=true;draw()};
load();
</script></body></html>
"""
