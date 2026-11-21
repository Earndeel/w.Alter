"""Feature matrix of Liquid's own decision API vs OpenRouter (17/11/2026): one real call per feature and model, a
verdict against a truth we know. Output JSONL (no key, synthetic content only).
Run: walter-python bench/liquid_native_features.py OUT.jsonl"""
from __future__ import annotations

import json
import sys

import liquid_common as lc

OUT = sys.argv[1] if len(sys.argv) > 1 else "/dev/stdout"
MODELS = ("d1.2", "d1.2-ultra")
MSG = "Rappelle-moi d'appeler Paul Martin demain avant 18h pour le devis de 1 450 euros, mais ne lui envoie rien par mail."
PNG3, TRUTH3 = lc.squares_png(3)
PNG1, TRUTH1 = lc.squares_png(1)


def near(box, t, tol=0.06):
    return box and all(abs(box[k] - t[k]) <= tol for k in ("top", "bottom", "left", "right"))


def cases():
    """name → (body, check(answers) -> (ok, note), route)"""
    yield "noul", {"state": MSG, "questions": {"q": {"type": "noul", "instructions": "Le message demande-t-il d'envoyer un mail ?"}}}, \
        lambda a: (a["q"]["noul"] < 0.5, a["q"]["noul"]), "both"
    yield "choice", {"state": MSG, "questions": {"q": {"type": "choice", "instructions": "Quelle est l'intention ?",
        "criteria": {"rappel": "créer un rappel ou une tâche", "question": "poser une question", "salutation": "dire bonjour"}}}}, \
        lambda a: (a["q"]["choice"] == "rappel", a["q"]["probabilities"]), "both"
    yield "score", {"state": "URGENT !!! le serveur est tombé, appelez-moi tout de suite", "questions": {"q": {"type": "score",
        "instructions": "Quelle urgence ?", "criteria": ["aucune", "moyenne", "critique"]}}}, \
        lambda a: (a["q"]["score"] > 1.4, a["q"]["score"]), "both"
    yield "multiple", {"state": "Mon colis est arrivé en retard et j'ai été débité deux fois.", "questions": {"q": {"type": "choice",
        "multiple": True, "instructions": "Quels sujets ?", "criteria": {"facturation": "paiements", "livraison": "expédition",
        "produit": "qualité", "compte": "connexion"}}}}, \
        lambda a: (set(a["q"].get("choices", [])) == {"facturation", "livraison"} and
                   a["q"]["probabilities"]["facturation"] + a["q"]["probabilities"]["livraison"] > 1.2, a["q"].get("probabilities")), "both"
    yield "text", {"state": MSG, "questions": {"q": {"type": "text", "instructions": "Quelle personne faut-il appeler ?"}}}, \
        lambda a: ("Paul" in (a["q"].get("text") or ""), a["q"].get("text")), "ext"
    yield "number", {"state": MSG, "questions": {"q": {"type": "number", "instructions": "Quel montant ?", "unit": "EUR"}}}, \
        lambda a: (a["q"].get("number") == 1450, {k: a["q"].get(k) for k in ("number", "text", "found")}), "ext"
    yield "date", {"state": "Facture 2026-117. À payer avant le 03/04/2026 (jour/mois/année).", "questions": {"q": {"type": "date",
        "instructions": "Date limite de paiement ?"}}}, \
        lambda a: (a["q"].get("date") == "2026-04-03", {k: a["q"].get(k) for k in ("date", "text", "found")}), "ext"
    yield "date_words", {"state": "On se voit vendredi prochain.", "questions": {"q": {"type": "date", "instructions": "Quand ?"}}}, \
        lambda a: (a["q"].get("date") is not None, {k: a["q"].get(k) for k in ("date", "text", "found")}), "ext"
    yield "not_found", {"state": MSG, "questions": {"q": {"type": "number", "instructions": "Quel est le numéro de téléphone ?"}}}, \
        lambda a: (a["q"].get("number") is None and (a["q"].get("found") or 0) < 0.5, a["q"].get("found")), "ext"
    yield "spans", {"state": "Marie Curie (née le 1867-11-07) écrit à pierre@example.com ; appelez le 06 12 34 56 78.",
        "questions": {"q": {"type": "spans", "instructions": "Toutes les données personnelles."}}}, \
        lambda a: (a["q"].get("count", 0) >= 3, [s["text"] for s in a["q"].get("spans", [])]), "ext"
    yield "estimate", {"state": "Réunion du comité : on attend une trentaine de personnes, peut-être un peu plus.",
        "questions": {"q": {"type": "number", "instructions": "Combien de personnes ?", "range": [0, 100], "step": 1}}}, \
        lambda a: (20 <= a["q"].get("number", -1) <= 45 and a["q"].get("interval") is not None, {k: a["q"].get(k) for k in ("number", "interval")}), "ext"
    yield "image_count", {"state": "Image à analyser.", "images": [PNG3], "questions": {"q": {"type": "number",
        "instructions": "Combien de carrés rouges ?", "range": [0, 10], "step": 1}}}, \
        lambda a: (a["q"].get("number") == 3, {k: a["q"].get(k) for k in ("number", "interval")}), "img"
    yield "image_noul", {"state": "Image à analyser.", "images": [PNG3], "questions": {"q": {"type": "noul",
        "instructions": "Y a-t-il un cercle bleu ?"}, "r": {"type": "noul", "instructions": "Y a-t-il un triangle vert ?"}}}, \
        lambda a: (a["q"]["noul"] > 0.5 > a["r"]["noul"], (a["q"]["noul"], a["r"]["noul"])), "img"
    yield "box", {"state": "Image à analyser.", "images": [PNG1], "questions": {"q": {"type": "box", "instructions": "Le carré rouge."}}}, \
        lambda a: (bool(near(a["q"].get("box"), TRUTH1[0])), {"box": a["q"].get("box"), "truth": TRUTH1[0], "found": a["q"].get("found")}), "box"
    yield "boxes", {"state": "Image à analyser.", "images": [PNG3], "questions": {"q": {"type": "boxes", "instructions": "Chaque carré rouge.", "max": 6}}}, \
        lambda a: (a["q"].get("count") == 3 and all(near(b["box"], t) for b, t in zip(a["q"]["boxes"], sorted(TRUTH3, key=lambda x: (x["left"], x["top"])))),
                   {"count": a["q"].get("count"), "boxes": [b["box"] for b in a["q"].get("boxes", [])], "truth": TRUTH3}), "box"
    tone, silence = lc.wav_data("tone", 1.5), lc.wav_data("silence", 1.5)
    yield "audio_tone", {"state": None, "media": [{"type": "audio", "data": tone}], "questions": {"q": {"type": "noul",
        "instructions": "Y a-t-il un son audible (un bip) ?"}}}, lambda a: (a["q"]["noul"] > 0.5, a["q"]["noul"]), "audio"
    yield "audio_silence", {"state": None, "media": [{"type": "audio", "data": silence}], "questions": {"q": {"type": "noul",
        "instructions": "Y a-t-il un son audible (un bip) ?"}}}, lambda a: (a["q"]["noul"] < 0.5, a["q"]["noul"]), "audio"
    yield "mixed_one_call", {"state": MSG, "questions": {
        "mail": {"type": "noul", "instructions": "Faut-il envoyer un mail ?"},
        "intent": {"type": "choice", "instructions": "Intention ?", "criteria": {"rappel": "rappel", "question": "question"}},
        "who": {"type": "text", "instructions": "Qui appeler ?"}, "amount": {"type": "number", "instructions": "Montant ?"},
        "when": {"type": "date", "instructions": "Quand ?"}}}, \
        lambda a: (a["mail"]["noul"] < 0.5 and a["intent"]["choice"] == "rappel" and "Paul" in (a["who"].get("text") or "") and a["amount"].get("number") == 1450,
                   {k: (v.get("noul") or v.get("choice") or v.get("text") or v.get("number") or v.get("date")) for k, v in a.items()}), "mixed"
    yield "now_field", {"state": "On se voit vendredi prochain.", "now": "2026-11-17", "questions": {"q": {"type": "date", "instructions": "Quand ?"}}}, \
        lambda a: (a["q"].get("date") is not None, a["q"].get("date")), "param"
    yield "stream_param", {"state": "ok", "stream": True, "questions": {"q": {"type": "noul", "instructions": "Est-ce ok ?"}}}, \
        lambda a: (True, "accepted"), "param"
    yield "spoken_question", {"state": "Commande 4417 livrée le 14 novembre.", "questions": {"q": {"type": "noul",
        "instructions": {"type": "audio", "data": tone}}}}, lambda a: (True, a["q"]), "audio"
    yield "pdf_document", {"state": None, "media": [{"type": "document", "data": "data:application/pdf;base64,JVBERi0="}],
        "questions": {"q": {"type": "noul", "instructions": "ok ?"}}}, lambda a: (True, a), "pdf"


def run_one(prov: str, model: str, name: str, body: dict, check, route: str) -> dict:
    row = {"provider": prov, "model": model, "feature": name}
    if prov == "liquid":
        res = lc.liquid(model, body)
    else:
        # OpenRouter: decision route for base kinds; extraction route for typed ones; images as image_url parts
        b = dict(body)
        b.pop("now", None); b.pop("stream", None)
        if route in ("ext",) and body["questions"]:
            fields = {}
            for k, q in b["questions"].items():
                t = q["type"]
                f = {"instructions": q["instructions"]}
                if t == "number" and "range" in q:
                    f.update(type="estimate", min=q["range"][0], max=q["range"][1], step=q.get("step"))
                elif t == "spans":
                    f.update(type="list", items="text")
                else:
                    f.update(type=t, null_threshold=0.5)
                fields[k] = f
            res = lc.or_extract(model, {"state": b["state"], "fields": fields})
        else:
            if b.get("images"):
                b["state"] = [b["state"], *({"type": "image_url", "image_url": {"url": u}} for u in b.pop("images"))]
            res = lc.or_decide(model, b)
    row.update(status=res["status"], ms=res["ms"], rl=res.get("rl") or None)
    data = res["data"] or {}
    if res["status"] == 200 and isinstance(data.get("answers"), dict):
        a = data["answers"]
        row["usage"] = data.get("usage")
        try:
            ok, note = check(a)
            row.update(ok=bool(ok), note=note)
        except Exception as e:  # noqa: BLE001
            row.update(ok=False, note=f"check failed: {type(e).__name__} {e}", answers=a)
        row["answers"] = a if name in ("box", "boxes", "mixed_one_call", "spoken_question", "now_field") else None
    else:
        row.update(ok=False, error=json.dumps(data)[:300] if data else res.get("error"))
    return row


def main():
    rows = []
    with open(OUT, "w") as f:
        for name, body, check, route in cases():
            for model in MODELS:
                provs = ["liquid"] + (["openrouter"] if route in ("both", "ext", "img", "mixed", "box", "audio", "param") else [])
                for prov in provs:
                    row = run_one(prov, model, name, body, check, route)
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"{prov:10} {model:11} {name:16} {row['status']} {row['ms']:7.0f} ms ok={row.get('ok')} {str(row.get('note') or row.get('error'))[:110]}")


if __name__ == "__main__":
    main()
