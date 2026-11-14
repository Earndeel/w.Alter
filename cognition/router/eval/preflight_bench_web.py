"""Preflight bench, web page (2026-11-14): the owner's blind reference, then his review of four anonymous proposals.

Temporary door, asked by the owner: one page, tailnet address only (never public), run as a transient systemd unit
and stopped once the review is done. Per case: the input and everything the preflight would see (origin, previous
exchange, candidate threads, modules), his own decision first; the proposals A-D (random order per case, never a
model name) only once his decision is complete, which freezes it (a revision is kept apart). No request log: the
page carries the owner's messages.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from walter_router.eval import preflight_bench as bench

QUESTIONS = {k: q for k, q, _ in bench.FIELDS}


def cases_view() -> dict:
    reviews = bench._read("reviews.json", {})
    out = []
    for no, c in enumerate(bench.cases()):
        rv = reviews.get(c["id"]) or {}
        out.append({"no": no, **bench.case_view(c), "done": bool(rv.get("done")),
                    "revealed": bool(rv.get("revealed_at")), "reference": rv.get("reference") or {},
                    "fields": [{"key": k, "text": QUESTIONS[k], "memory_only": k in bench.MEMORY_ONLY,
                                "multi": k == "docs", "options": [{"value": v, "label": lab}
                                                                  for v, lab in bench.options(c, k)]}
                               for k in bench.fields_of(c)],
                    **({"shown": bench._proposals(c, rv)} if rv.get("revealed_at") else {})})
    return {"cases": out, "status": bench.status()}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
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
            return self._send(200, json.dumps(cases_view(), ensure_ascii=False).encode())
        self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        if self.path not in ("/api/ref", "/api/reveal", "/api/review"):
            return self._send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 8192:
            return self._send(413, b"too large", "text/plain")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            no = int(body["no"])
            if self.path == "/api/ref":
                out = bench.set_reference(no, body["key"], body.get("value"))
            elif self.path == "/api/reveal":
                out = bench.reveal(no)
            else:
                out = bench.review(no, body)
        except bench.Frozen:
            return self._send(409, b'{"ok": false, "frozen": true}')
        except (KeyError, ValueError, IndexError, TypeError):
            return self._send(400, b'{"ok": false}')
        self._send(200, json.dumps({"ok": True, **out}, ensure_ascii=False).encode())

    def log_message(self, *a):
        pass


def serve(host: str, port: int) -> None:
    ThreadingHTTPServer((host, port), Handler).serve_forever()


PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Banc Preflight</title>
<style>
:root{--b:#01B7FF}
*{box-sizing:border-box}
body{margin:0;background:#000;color:#e8e8e8;font:16px/1.45 -apple-system,system-ui,sans-serif}
main{max-width:900px;margin:0 auto;padding:16px}
header{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
h1{font-size:18px;margin:0;color:var(--b)}
h2{font-size:16px;margin:18px 0 8px;color:var(--b)}
.bar{height:6px;border:2px solid var(--b);border-radius:6px;margin:10px 0 16px}
.bar>div{height:100%;background:var(--b)}
.meta{color:#9aa;font-size:14px}
.box{border:2px solid var(--b);border-radius:10px;padding:12px;margin:10px 0;background:#050b10}
.msg{white-space:pre-wrap;font-size:17px}
.prev{white-space:pre-wrap;font-size:14px;color:#c8d0d4;border-left:3px solid #2a3a44;padding-left:10px;margin:6px 0}
.th{border:2px solid #2a3a44;border-radius:8px;padding:8px 10px;margin:6px 0;font-size:14px}
.th b{color:#fff}
details{margin:8px 0}summary{cursor:pointer;color:var(--b)}
.mod{font-size:13px;margin:4px 0;color:#c8d0d4}
.q{margin:0 0 16px}
.q h3{font-size:15px;margin:0 0 6px}
.opts{display:flex;flex-wrap:wrap;gap:6px}
button{background:#000;color:#e8e8e8;border:2px solid #2a3a44;border-radius:10px;padding:8px 12px;font:inherit;font-size:15px;cursor:pointer}
button:hover{border-color:var(--b)}
button.on{border-color:var(--b);background:#01B7FF22;color:#fff}
button:disabled{opacity:.5;cursor:default}
nav{display:flex;gap:8px;justify-content:space-between;margin-top:22px;flex-wrap:wrap}
#reveal{width:100%;border-color:var(--b);margin-top:8px}
.p{border:2px solid #2a3a44;border-radius:10px;padding:10px 12px;margin:0 0 12px}
.p.pref{border-color:var(--b)}
.p h3{margin:0 0 8px;font-size:16px;color:var(--b);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.row{display:grid;grid-template-columns:150px 1fr auto;gap:8px;align-items:center;padding:4px 0;border-top:1px solid #111}
.row .k{color:#9aa;font-size:13px}
.row .v{font-size:14px}.row .v small{color:#8a9aa4}
.g button{padding:3px 9px;font-size:13px}
.g .correct.on{background:#3ddc8433;border-color:#3ddc84}
.g .acceptable.on{background:#f5b84133;border-color:#f5b841}
.g .incorrect.on{background:#ff5c5c33;border-color:#ff5c5c}
.grave.on{background:#ff5c5c44;border-color:#ff5c5c}
textarea{width:100%;min-height:70px;background:#000;color:#e8e8e8;border:2px solid #2a3a44;border-radius:10px;padding:8px;font:inherit}
.dots{display:flex;flex-wrap:wrap;gap:4px;margin-top:20px}
.dots span{width:14px;height:14px;border:2px solid #2a3a44;border-radius:4px;cursor:pointer}
.dots span.d{background:#01B7FF66;border-color:var(--b)}
.dots span.r{background:var(--b);border-color:var(--b)}
.dots span.c{outline:2px solid #fff}
.note{font-size:14px;color:#c8d0d4;border:2px dashed #2a3a44;border-radius:10px;padding:8px 10px;margin:8px 0}
</style></head><body><main>
<header><h1>Banc Preflight · décision à l'aveugle</h1><span class="meta" id="count"></span></header>
<div class="bar"><div id="prog" style="width:0"></div></div>
<div id="case"></div>
<nav><button id="prev">← Précédent</button><button id="next">Suivant →</button></nav>
<div class="dots" id="dots"></div>
<p class="meta">1. Donnez votre propre décision (« ? » = je ne sais pas). 2. « Voir les propositions » affiche les quatre propositions anonymes A–D, dans un ordre différent à chaque cas ; votre décision d'avant est alors gardée telle quelle. 3. Notez chaque champ (✓ juste, ≈ acceptable, ✗ faux), signalez une erreur grave, choisissez la proposition préférée. Vous pouvez encore corriger votre décision : la correction est gardée à part. Chaque clic est enregistré.</p>
</main>
<script>
let cases=[],cur=0;
const $=id=>document.getElementById(id);
function el(t,a,...k){const e=document.createElement(t);Object.assign(e,a||{});k.forEach(x=>e.append(x));return e}
async function api(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.status===409){alert('Propositions déjà vues : votre décision d\'avant reste celle-là (corrigez plus bas)');return null}
  if(!r.ok){alert('Non enregistré : rechargez la page');return null}return r.json()}
async function load(){const d=await (await fetch('/api/cases')).json();cases=d.cases;const f=cases.findIndex(c=>!c.revealed);cur=f<0?0:f;draw()}
const MEM=['C3','C4'];
function label(c,key,v){if(v===undefined)return '—';if(v===null)return '?';const f=c.fields.find(x=>x.key===key);
  if(key==='docs'){return v.length?v.map(m=>(f.options.find(o=>o.value===m)||{label:m}).label).join(', '):'Aucun'}
  return (f.options.find(o=>o.value===v)||{label:v}).label}
function ctx(c){const b=el('div');
  const o=c.origin||{};b.append(el('div',{className:'meta',textContent:'Cas '+(cur+1)+' / '+cases.length+' · '+c.category+' · '+c.source+(o.channel?' · entrée : '+[o.channel,o.kind,o.source].filter(Boolean).join(' / '):'')}));
  const box=el('div',{className:'box'});
  if(c.previous){box.append(el('div',{className:'meta',textContent:'Échange précédent'+(c.previous.age_s!=null?' (il y a '+Math.round(c.previous.age_s/60)+' min)':'')}));
    box.append(el('div',{className:'prev',textContent:'Vous : '+(c.previous.message||'')+'\nWalter : '+(c.previous.answer||'')}))}
  box.append(el('div',{className:'meta',textContent:'Nouveau message'}));box.append(el('div',{className:'msg',textContent:c.message}));b.append(box);
  if(c.candidates.length){b.append(el('div',{className:'meta',textContent:'Fils candidats'}));
    c.candidates.forEach(t=>{const d=el('div',{className:'th'},el('b',{textContent:t.title||t.id}));
      [['objective','Objectif'],['state','État'],['task','Tâche'],['last_message','Dernier message']].forEach(([k,n])=>{if(t[k])d.append(el('div',{textContent:n+' : '+(typeof t[k]==='string'?t[k]:JSON.stringify(t[k]))}))});
      if(t.hours_since_last!=null)d.append(el('div',{className:'meta',textContent:'il y a '+t.hours_since_last+' h'}));b.append(d)})}
  const det=el('details',{},el('summary',{textContent:'Modules présentés au modèle (une ligne chacun, D1)'}));
  c.modules.forEach(m=>det.append(el('div',{className:'mod'},el('b',{textContent:m.name+' : '}),m.line)));b.append(det);return b}
function refForm(c){const b=el('div');const ref=c.revealed?(c.shown.revised||c.reference):c.reference;
  b.append(el('h2',{textContent:c.revealed?'Votre décision (corrigez si besoin : gardée à part)':'Votre décision'}));
  c.fields.forEach(f=>{if(f.memory_only&&!MEM.includes(ref.C))return;
    const opts=el('div',{className:'opts'}),val=ref[f.key];
    f.options.forEach(o=>{const on=f.multi?(Array.isArray(val)&&val.includes(o.value)):val===o.value;
      const x=el('button',{className:on?'on':''},o.label);x.onclick=()=>{let v=o.value;
        if(f.multi){const s=new Set(Array.isArray(val)?val:[]);s.has(o.value)?s.delete(o.value):s.add(o.value);v=[...s]}set(f.key,v)};opts.append(x)});
    if(f.multi){const x=el('button',{className:Array.isArray(val)&&!val.length?'on':''},'Aucun');x.onclick=()=>set(f.key,[]);opts.append(x)}
    else{const x=el('button',{className:val===null?'on':''},'?');x.onclick=()=>set(f.key,null);opts.append(x)}
    b.append(el('div',{className:'q'},el('h3',{textContent:f.text}),opts))});
  return b}
async function set(key,value){const c=cases[cur];
  if(c.revealed){const r=await api('/api/review',{no:c.no,what:'revise',key,value});if(r){c.shown=r;draw()}return}
  const r=await api('/api/ref',{no:c.no,key,value});if(!r)return;c.reference=r.reference;c.done=r.done;draw()}
function proposals(c){const b=el('div'),s=c.shown;b.append(el('h2',{textContent:'Propositions anonymes'}));
  if(s.note)b.append(el('div',{className:'note',textContent:'Note du cas : '+s.note}));
  s.proposals.forEach(p=>{const card=el('div',{className:'p'+(s.preferred===p.letter?' pref':'')});
    if(p.missing){card.append(el('h3',{textContent:p.letter+' · pas de réponse'}));b.append(card);return}
    const pref=el('button',{className:s.preferred===p.letter?'on':''},'Préférée');pref.onclick=()=>rev({what:'preferred',value:s.preferred===p.letter?null:p.letter});
    const gr=el('button',{className:'grave'+(p.grave?' on':'')},'Erreur grave');gr.onclick=()=>rev({what:'grave',letter:p.letter,value:!p.grave});
    card.append(el('h3',{},el('span',{textContent:'Proposition '+p.letter}),el('span',{},pref,' ',gr)));
    Object.entries(p.fields).forEach(([k,f])=>{const g=el('div',{className:'g'});
      [['correct','✓'],['acceptable','≈'],['incorrect','✗']].forEach(([v,t])=>{const x=el('button',{className:v+(f.grade===v?' on':'')},t);x.onclick=()=>rev({what:'grade',letter:p.letter,key:k,grade:v});g.append(x)});
      const fl=c.fields.find(x=>x.key===k);
      card.append(el('div',{className:'row'},el('div',{className:'k',textContent:fl?fl.text.replace(/ \(.*\)/,'').replace(/\?$/,''):k}),
        el('div',{className:'v'},label(c,k,f.value),el('small',{textContent:f.confidence!=null?'  '+Math.round(f.confidence*100)+' %':''})),g))});
    b.append(card)});
  const none=el('button',{className:s.preferred==='none'?'on':''},'Aucune ne me convient');none.onclick=()=>rev({what:'preferred',value:s.preferred==='none'?null:'none'});b.append(none);
  const ta=el('textarea',{value:s.comment||'',placeholder:'Commentaire (facultatif)'});ta.onblur=()=>{if(ta.value!==(s.comment||''))rev({what:'comment',value:ta.value})};
  b.append(el('h2',{textContent:'Commentaire'}),ta);return b}
async function rev(body){const c=cases[cur],r=await api('/api/review',{no:c.no,...body});if(r){c.shown=r;draw()}}
async function reveal(){const c=cases[cur],r=await api('/api/reveal',{no:c.no});if(!r)return;c.shown=r;c.revealed=true;draw()}
function draw(){const rv=cases.filter(c=>c.revealed).length;$('count').textContent=rv+' / '+cases.length+' cas validés';
  $('prog').style.width=(100*rv/cases.length)+'%';const c=cases[cur],box=$('case');box.innerHTML='';
  box.append(ctx(c),refForm(c));
  if(c.revealed)box.append(proposals(c));
  else if(c.done){const b=el('button',{id:'reveal'},'Voir les propositions');b.onclick=reveal;box.append(b)}
  else box.append(el('div',{className:'meta',textContent:'Répondez à chaque question pour voir les propositions.'}));
  const dots=$('dots');dots.innerHTML='';
  cases.forEach((k,i)=>{const d=el('span',{className:(k.revealed?'r':k.done?'d':'')+(i===cur?' c':''),title:'Cas '+(i+1)});d.onclick=()=>{cur=i;draw();scrollTo(0,0)};dots.append(d)})}
$('prev').onclick=()=>{if(cur>0){cur--;draw();scrollTo(0,0)}};
$('next').onclick=()=>{if(cur<cases.length-1){cur++;draw();scrollTo(0,0)}};
load();
</script></body></html>
"""
