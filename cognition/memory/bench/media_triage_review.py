"""Blind human review for the media triage bench: Monsieur labels each image (utile / peut-être / inutile) without
seeing the rule/Jev verdicts; /stats compares afterwards.

Images are decrypted from the vault into RAM (/dev/shm) and served only on the Tailscale address behind a random
token path. `--wipe` deletes the decrypted copies. Labels: <out>/labels.json (0600).

    venv/bin/python bench/media_triage_review.py --out /root/.hermes/logs/media-triage-test [--prepare] [--serve]
"""
from __future__ import annotations

import argparse
import html
import io
import json
import random
import secrets
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps

SHM = Path("/dev/shm/media-triage-review")
LEVELS = {"high": "Utile", "medium": "Peut-être", "low": "Inutile"}


def load(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]


CLEF_MODELS = ("clef", "clef-flash")


def load_clef(out: Path) -> dict:
    p = out / "results_clef.jsonl"
    if not p.exists():
        return {}
    return {r["object_id"]: r for r in (json.loads(line) for line in p.read_text().splitlines())}


def prepare(out: Path) -> None:
    rows = load(out)
    orig, thumbs = SHM / "orig", SHM / "thumbs"
    orig.mkdir(parents=True, exist_ok=True, mode=0o700)
    thumbs.mkdir(exist_ok=True, mode=0o700)
    lst = SHM / "files.txt"
    lst.write_text("\n".join(r["storage_key"] for r in rows) + "\n")
    subprocess.run(["rclone", "copy", "walter-vault:secure", str(orig), "--files-from", str(lst),
                    "--transfers", "16", "--checkers", "16"], check=True)
    for r in rows:
        src = orig / r["storage_key"]
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((520, 520))
                im.convert("RGB").save(thumbs / f"{r['object_id']}.jpg", "JPEG", quality=82)
        except Exception as e:  # noqa: BLE001 — HEIC/ICO etc.: shown as missing
            print("thumb failed", r["object_id"], r["mime"], e)
    print("prepared", len(list(thumbs.iterdir())), "thumbnails")


def stats(out: Path) -> dict:
    rows = {r["object_id"]: r for r in load(out)}
    labels = json.loads((out / "labels.json").read_text()) if (out / "labels.json").exists() else {}
    lab = [(rows[k], v) for k, v in labels.items() if k in rows and "jev" in rows[k]]
    n = len(lab)

    def useful(v):
        return v == "high"

    res = {"labelled": n}
    if not n:
        return res
    # Jev "low" = would be discarded. False discard = Monsieur says Utile.
    for name, pred in {"jev_low": lambda r: r["jev"]["value"] == "low",
                       "rules_skip": lambda r: r["rule"] == "skip",
                       "rules_or_jev_low": lambda r: r["rule"] == "skip" or r["jev"]["value"] == "low"}.items():
        dropped = [(r, v) for r, v in lab if pred(r)]
        kept = [(r, v) for r, v in lab if not pred(r)]
        tot_useful = sum(useful(v) for _, v in lab)
        res[name] = {"dropped": len(dropped), "dropped_but_useful": sum(useful(v) for _, v in dropped),
                     "dropped_and_useless": sum(v == "low" for _, v in dropped),
                     "useful_kept_recall": round(sum(useful(v) for _, v in kept) / tot_useful, 2) if tot_useful else None,
                     "work_saved": round(len(dropped) / n, 2)}
    clef = load_clef(out)
    for m in CLEF_MODELS:
        sub = [(clef[r["object_id"]][m], v) for r, v in lab if m in clef.get(r["object_id"], {})]
        tot_useful = sum(useful(v) for _, v in sub)
        dropped = [(x, v) for x, v in sub if x["value"] == "low"]
        res[f"{m}_low"] = {"labelled": len(sub), "dropped": len(dropped),
                           "dropped_but_useful": sum(useful(v) for _, v in dropped),
                           "dropped_and_useless": sum(v == "low" for _, v in dropped),
                           "useful_kept_recall": round(sum(useful(v) for x, v in sub if x["value"] != "low") / tot_useful, 2)
                           if tot_useful else None,
                           "work_saved": round(len(dropped) / len(sub), 2) if sub else None,
                           "exact_agreement": round(sum(x["value"] == v for x, v in sub) / len(sub), 2) if sub else None}
        res[f"confusion_{m}_vs_monsieur"] = {p: {t: sum(1 for x, v in sub if x["value"] == p and v == t)
                                                 for t in LEVELS} for p in LEVELS}
    res["jev_exact_agreement"] = round(sum(r["jev"]["value"] == v for r, v in lab) / n, 2)
    res["confusion_jev_value_vs_monsieur"] = {p: {t: sum(1 for r, v in lab if r["jev"]["value"] == p and v == t)
                                                  for t in LEVELS} for p in LEVELS}
    res["monsieur"] = {t: sum(1 for _, v in lab if v == t) for t in LEVELS}
    return res


def clef_line(model: str, x: dict | None) -> str:
    if not x:
        return f'<div class="m">{model} : pas de résultat</div>'
    flags = " · ".join(f"{label} {x[k]:.2f}" for k, label in
                       (("nudity", "nudité"), ("people", "personnes"), ("text", "texte"), ("sticker_like", "sticker")))
    return (f'<div class="m"><span class="t {x["value"]}">{model} : {LEVELS[x["value"]]}</span> '
            f'conf. {x["value_confidence"]:.2f} · {html.escape(x["content"])} · {html.escape(x["processing"])}'
            f'<br><small>{flags}</small></div>')


def serve(out: Path, host: str, port: int) -> None:
    url_file = out / "review_url.txt"
    old = url_file.read_text().strip().rstrip("/").rsplit("/", 1)[-1] if url_file.exists() else ""
    token = old or secrets.token_urlsafe(18)
    rows = load(out)
    order = [r["object_id"] for r in rows]
    random.Random(7).shuffle(order)
    meta = {r["object_id"]: r for r in rows}
    clef = load_clef(out)
    labels_path = out / "labels.json"

    def labels() -> dict:
        return json.loads(labels_path.read_text()) if labels_path.exists() else {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if not p.startswith(f"/{token}"):
                return self._send(404, b"", "text/plain")
            p = p[len(token) + 1:]
            if p.startswith("/img/"):
                f = SHM / "thumbs" / (p[5:].replace("/", "") + ".jpg")
                return self._send(200, f.read_bytes(), "image/jpeg") if f.exists() else self._send(404, b"", "text/plain")
            if p == "/count":
                return self._send(200, str(len(labels())).encode(), "text/plain")
            if p == "/stats":
                return self._send(200, json.dumps(stats(out), indent=1, ensure_ascii=False).encode(), "application/json")
            lab = labels()
            cards = []
            for i, oid in enumerate(order, 1):
                r = meta[oid]
                st = r.get("state") or {}
                cur = lab.get(oid, "")
                btns = "".join(f'<button class="b {k}{" on" if cur == k else ""}" onclick="L(\'{oid}\',\'{k}\',this)">{v}</button>'
                               for k, v in LEVELS.items())
                j = r.get("jev") or {}
                rule = "écartée par règle (" + r["rule_reason"] + ")" if r["rule"] == "skip" else "règles : gardée"
                ctxt = [f"Légende : {st['caption']}"] if st.get("caption") else []
                ctxt += [f"{m['minutes_from_image']:+d} min · {m['from']} : {m['text']}"
                         for m in st.get("neighbouring_messages") or []]
                tm = st.get("thread_messages") or {}
                ctxt.append(f"Envoyée par : {st.get('sent_by')} · fil : {tm.get('by_monsieur')} msg de Monsieur / "
                            f"{tm.get('by_others')} des autres · réactions : {st.get('reactions_on_image')}")
                verdict = (f'<div class="v"><span class="t {j.get("value")}">Jev : {LEVELS.get(j.get("value"), "?")}</span> '
                           f'conf. {j.get("value_confidence")} · {html.escape(str(j.get("content")))} · '
                           f'{html.escape(str(j.get("processing")))}<br><small>{html.escape(rule)} · probas '
                           f'{html.escape(json.dumps(j.get("value_probs")))}</small>'
                           + "".join(clef_line(m, clef.get(oid, {}).get(m)) for m in CLEF_MODELS) +
                           f'<details><summary>Contexte vu par Jev</summary><small>'
                           + "<br>".join(html.escape(x) for x in ctxt) + '</small></details></div>')
                info = html.escape(f"{st.get('network') or ''} · {st.get('chat_type') or ''} · {(r.get('captured_at') or '')[:10]}")
                cards.append(f'<div class="c" id="c{oid}"><div class="n">#{i}</div><img loading="lazy" src="/{token}/img/{oid}">'
                             f'<div class="i">{info}</div>{verdict}<div class="bs">{btns}</div></div>')
            page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Tri médias Beeper — vérification</title><style>
body{{font:14px -apple-system,sans-serif;margin:16px;background:#111;color:#eee}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}}
.c{{background:#1c1c1e;border-radius:10px;padding:8px}} .c img{{width:100%;height:240px;object-fit:contain;background:#000;border-radius:6px}}
.n{{color:#888;font-size:12px}} .i{{color:#aaa;font-size:12px;margin:4px 0}}
.bs{{display:flex;gap:4px}} .b{{flex:1;padding:8px 0;border:0;border-radius:6px;background:#333;color:#eee;cursor:pointer}}
.b.high.on{{background:#2e7d32}} .b.medium.on{{background:#b28704}} .b.low.on{{background:#b71c1c}}
.v{{display:none;font-size:12px;color:#ccc;margin:4px 0}} body.show .v{{display:block}}
.t{{font-weight:600;padding:1px 6px;border-radius:4px}} .t.high{{background:#2e7d32}} .t.medium{{background:#b28704}} .t.low{{background:#b71c1c}}
.m{{margin-top:6px;padding-top:4px;border-top:1px solid #333}}
details{{margin-top:4px}} summary{{cursor:pointer;color:#8ab4f8}}
#p{{position:sticky;top:0;background:#111;padding:8px 0;z-index:2}}</style>
<div id=p><b>Tri des médias Beeper — test à l'aveugle</b> · une image est <i>utile</i> si son contenu mérite d'entrer
dans la mémoire de W.Alter. Noté : <span id=k>{len(lab)}</span>/{len(order)} (50 suffisent pour une première mesure)
<button onclick="document.body.classList.toggle('show');localStorage.v=document.body.classList.contains('show')?1:''"
style="margin-left:12px;padding:6px 10px">Afficher / masquer les verdicts (Jev, Clef, Clef-flash)</button>
<a href="/{token}/stats" style="margin-left:12px;color:#8ab4f8">stats</a></div>
<div class=g>{''.join(cards)}</div><script>if(localStorage.v)document.body.classList.add('show');
async function L(o,v,b){{await fetch('/{token}/label',{{method:'POST',body:JSON.stringify({{o,v}})}});
b.parentNode.querySelectorAll('.b').forEach(x=>x.classList.remove('on'));b.classList.add('on');
let r=await fetch('/{token}/count');document.getElementById('k').textContent=await r.text();}}</script>"""
            return self._send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            p = self.path
            if p == f"/{token}/label":
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0))
                if d.get("o") in meta and d.get("v") in LEVELS:
                    lab = labels()
                    lab[d["o"]] = d["v"]
                    labels_path.write_text(json.dumps(lab))
                    labels_path.chmod(0o600)
                    return self._send(200, b"ok", "text/plain")
            return self._send(400, b"", "text/plain")

    (out / "review_url.txt").write_text(f"http://{host}:{port}/{token}/\n")
    (out / "review_url.txt").chmod(0o600)
    print(f"serving on http://{host}:{port}/<token>/ (url in {out}/review_url.txt)", flush=True)
    ThreadingHTTPServer((host, port), H).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/.hermes/logs/media-triage-test")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--host", default="100.91.35.121")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    out = Path(a.out)
    if a.prepare:
        prepare(out)
    if a.stats:
        print(json.dumps(stats(out), indent=1, ensure_ascii=False))
    if a.wipe:
        shutil.rmtree(SHM, ignore_errors=True)
        print("wiped", SHM)
    if a.serve:
        serve(out, a.host, a.port)


if __name__ == "__main__":
    main()
