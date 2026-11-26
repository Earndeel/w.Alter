#!/usr/bin/env walter-python
"""Turn the owner's ChatGPT bench (`@instance/state/lab/chatgpt-bench/cases.jsonl`, built 2026-11-23 from his real
requests) into payload-bench scenarios (lot 3a reduced plan, 2026-11-24): a subset of the principal set only — the
reserve is never read — chosen on metadata alone (type, hard/representative, turns to replay, attachments present),
never on content, so the choice cannot be tuned to a Soul.

    chatgpt_scenarios.py [--size 30] [--out @instance/state/core/engine/bench/payload/scenarios/chatgpt-30.json]

The output and the image fixtures stay in the instance (0600 / 0700): they hold the owner's words. Each scenario:
his messages up to `tours_a_rejouer`, played on the web door; images he attached are copied with their real extension
and named to the engine the way a door names an attachment; the judge gets his expectations (`juger`: attendu,
critères from his reactions, recadrages, pièges, si_date) — ChatGPT's own answer is never given as the truth.
The output prints aggregates only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

# share of each request type in the subset, proportional to the principal set (100 cases) rounded to 30
QUOTAS = {"recherche_comparaison": 7, "conseil_decision": 5, "explication": 4, "plan_organisation": 4,
          "creation_visuelle": 3, "redaction": 2, "traduction": 1, "brainstorming": 1, "analyse_image": 1,
          "calcul": 1, "question_rapide": 1}
MAX_TURNS = 5                 # longer replays drift from what he answered ChatGPT, and cost the most
SHORT = {"recherche_comparaison": "cmp", "conseil_decision": "dec", "explication": "exp", "plan_organisation": "plan",
         "creation_visuelle": "vis", "redaction": "red", "traduction": "trad", "brainstorming": "idee",
         "analyse_image": "img", "calcul": "calc", "question_rapide": "rapide"}


def instance_root() -> Path:
    out = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=20).stdout.strip()
    if not out:
        sys.exit("no active Walter instance")
    return Path(out)


def resolve(root: Path, value: str) -> Path:
    return root / value[len("@instance/"):] if value.startswith("@instance/") else Path(value)


def mine(case: dict) -> list[dict]:
    return [t for t in case["turns"] if t.get("role") == "monsieur"][: int(case["juger"].get("tours_a_rejouer") or 1)]


BENCH: Path = Path()          # the ChatGPT bench folder: attachment paths are relative to it


def image_file(a: dict) -> Path | None:
    return (BENCH / a["path"]) if a.get("path") else None


ARTEFACTS: set[str] = set()    # 25/11: requests whose intent needed a context the replay lacks (artifacts.json)


def eligible(case: dict) -> bool:
    if case.get("jeu") != "principal" or case.get("rejouable") not in ("oui", "date"):
        return False
    if case["id"] in ARTEFACTS:
        return False
    turns = mine(case)
    if not turns or len(turns) > MAX_TURNS:
        return False
    atts = [a for t in turns for a in t.get("attachments") or []]
    return all(a.get("kind") == "image" and image_file(a) and image_file(a).is_file() for a in atts)


def order_key(case: dict) -> str:
    return hashlib.sha256(case["id"].encode()).hexdigest()      # stable, content-blind order


def pick(cases: list[dict], size: int) -> list[dict]:
    """Per type: hard cases (`dur:`) first, then representative ones, spreading categories; a type short of
    candidates leaves its places to the largest types."""
    chosen: list[dict] = []
    quotas = dict(QUOTAS)
    if size != sum(quotas.values()):
        scale = size / sum(quotas.values())
        quotas = {k: max(1, round(v * scale)) for k, v in quotas.items()}
    spare = 0
    for typ, n in quotas.items():
        pool = sorted((c for c in cases if c["type"] == typ), key=order_key)
        hard = [c for c in pool if c["case"].startswith("dur:")]
        rep = [c for c in pool if not c["case"].startswith("dur:")]
        got: list[dict] = []
        cats: Counter = Counter()
        for group in (hard[: max(1, n // 2)], rep, hard):
            for c in sorted(group, key=lambda c: (cats[c["cat"]], order_key(c))):
                if len(got) >= n:
                    break
                if c not in got:
                    got.append(c)
                    cats[c["cat"]] += 1
        spare += n - len(got)
        chosen += got
    if spare:
        rest = sorted((c for c in cases if c not in chosen), key=lambda c: (-QUOTAS.get(c["type"], 0), order_key(c)))
        chosen += rest[:spare]
    return chosen[:size]


def criteria(case: dict) -> str:
    j = case["juger"]
    lines = ["Demande réelle de Monsieur (rejouée). Ce qu'il attendait, d'après ses réactions réelles — la réponse "
             "qu'il avait reçue à l'époque n'est pas une vérité de référence :",
             f"- Attendu : {j.get('attendu')}"]
    lines += [f"- Critère : {x}" for x in j.get("criteres") or []]
    lines += [f"- Recadrage qu'il avait dû faire (à ne pas rendre nécessaire) : {x}" for x in j.get("recadrages") or []]
    lines += [f"- Piège : {x}" for x in j.get("pieges") or []]
    if j.get("si_date"):
        lines.append(f"- Dépend du moment : {j['si_date']} Juger la méthode et la fraîcheur des sources, pas le chiffre "
                     "de l'époque.")
    if len(mine(case)) > 1:
        lines.append("- Ses messages après le premier répondaient à l'époque à une autre réponse : juger la cohérence "
                     "de W.Alter avec ce qui lui a été réellement dit.")
    if case["type"] == "creation_visuelle":
        lines.append("- Le juge ne voit pas l'image : juger sur ce que la réponse livre (fichier créé, description, "
                     "choix) ; une image réellement produite vaut mieux qu'un simple prompt.")
    return "\n".join(lines)


def turn_text(t: dict, fixtures: Path) -> str:
    notes = []
    for a in t.get("attachments") or []:
        ext = mimetypes.guess_extension(a.get("mime_type") or "") or ".png"
        dest = fixtures / f"{a['file_id']}{ext}"
        if not dest.exists():
            shutil.copyfile(image_file(a), dest)
            os.chmod(dest, 0o600)
        notes.append(f"[image reçue de Monsieur sur le Portal, enregistrée ici : {dest}]")
    return "\n".join(notes + [t.get("text") or ""]).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=30)
    ap.add_argument("--cases", default="@instance/state/lab/chatgpt-bench/cases.jsonl")
    ap.add_argument("--out", default="@instance/state/core/engine/bench/payload/scenarios/chatgpt-30.json")
    a = ap.parse_args()
    root = instance_root()
    global BENCH
    src = resolve(root, a.cases)
    BENCH = src.parent
    art = resolve(root, "@instance/state/core/engine/bench/payload/scenarios/artifacts.json")
    if art.is_file():
        ARTEFACTS.update(o["id"] for o in json.loads(art.read_text()) if o.get("intent_artifact"))
    cases = [json.loads(x) for x in src.read_text().splitlines() if x.strip()]
    pool = [c for c in cases if eligible(c)]
    chosen = pick(pool, a.size)
    out = resolve(root, a.out)
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fixtures = out.parent / "fixtures"
    fixtures.mkdir(exist_ok=True, mode=0o700)
    scenarios = []
    for c in chosen:
        scenarios.append({
            "id": f"cg_{SHORT.get(c['type'], c['type'])}_{c['id'][:8]}", "family": f"chatgpt/{c['type']}",
            "interface": "web", "case": c["id"], "hard": c["case"].startswith("dur:"), "needs": c.get("needs") or [],
            "turns": [turn_text(t, fixtures) for t in mine(c)], "criteria": criteria(c),
            "tool_expected": "web_live" in (c.get("needs") or []), "judge_chars": 8000,
            "checks": [{"no_approval": True}]})
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"source": a.cases, "built": "lot 3a reduced plan (2026-11-24)", "scenarios": scenarios}, fh,
                  ensure_ascii=False, indent=1)
    print(json.dumps({"out": str(out), "eligible": len(pool), "chosen": len(scenarios),
                      "types": Counter(c["type"] for c in chosen), "hard": sum(s["hard"] for s in scenarios),
                      "turns": Counter(len(s["turns"]) for s in scenarios),
                      "needs": Counter(n for s in scenarios for n in s["needs"]),
                      "with_images": sum("[image reçue" in t for s in scenarios for t in s["turns"]),
                      "sphere": Counter(c["sphere"] for c in chosen)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
