"""Minimal recall check, g0+g1 (today) vs g1 alone (after a switch), on questions whose answers Monsieur's memory holds
(2026-11-03). The answer must appear in the context Walter would inject (rerank off for both: free). Read-only;
nothing is switched. The bar for a switch is the owner's: g1 must be at least as good as today on these.

  walter-python bench/g1_recall.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

QUESTIONS = [
    ("Dans quel pays Monsieur vit-il en ce moment ?", ["thaïlande", "thailand", "bangkok"]),
    ("Pour les images, Walter Router doit-il prendre le meilleur rapport qualité-prix ou le meilleur modèle disponible ?",
     ["meilleur disponible", "best available", "meilleur modèle disponible", "toujours le meilleur"]),
    ("Quel modèle de décision rapide utilise le preflight de walter-context ?", ["d1-ultra", "d1 ultra"]),
    ("Quel est le skill d'entrée pour une recherche de produit local avec Pareto ?", ["recherche-produit-locale"]),
    ("Sur quel port local écoute la sortie réseau walter-exit-local ?", ["1084"]),
    ("Par quelle connexion sort le navigateur Chromium de Walter ?", ["freebox"]),
    ("Quel outil sert à la sauvegarde hors site dédupliquée de Walter ?", ["restic"]),
    ("Où doivent être stockées les clés API de Walter ?", ["bitwarden"]),
    ("Quel est le plafond de dépense des bancs de test sur les fournisseurs payants ?", ["2 €", "2 euros", "2€"]),
    ("Où vit le logiciel Walter et où sont les données personnelles de Monsieur ?", ["/walter", "/user/lucas"]),
    ("Quand Hindsight a-t-il été retiré ?", ["19 octobre", "2026-10-19", "19/10"]),
    ("Sur quel dépôt GitHub le logiciel Walter est-il publié ?", ["earndeel/walter"]),
    ("Quelle est la règle pour les sous-titres des vidéos publicitaires ?", ["ponctuation", "tiers inférieur", "lower third"]),
    ("Que vend le projet EDGEWISE ?", ["perruque", "wig"]),
    ("Peut-on basculer la mémoire globalement de g0 vers g1 maintenant ?", ["rappel", "pas de bascule", "aucune bascule"]),
    ("Monsieur veut-il encore de longues périodes en mode fantôme pour la Memory V1 ?", ["fantôme", "shadow"]),
    ("Quel fournisseur a été ajouté à Walter Router le 30 octobre ?", ["venice"]),
    ("Comment le Mac de Monsieur résout-il les noms du tailnet ?", ["100.", "ip", "dns"]),
    ("Faut-il demander à Monsieur quels skills garder ?", ["réserve", "jamais", "ne pas demander", "never ask"]),
    ("Quelle est la cible de remplacement du runtime Hermes ?", ["dsh", "runtime"]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--rerank", action="store_true", help="as in production (cloud rerank: a few cents)")
    a = ap.parse_args()
    from walter_memory import context, generations, search
    rows, t0 = [], time.time()
    for q, expected in QUESTIONS:
        real = search._rerank
        if not a.rerank:
            search._rerank = lambda qq, rr, limit, timeout=8: rr[:limit]
        try:
            today_r = context.get_context(q, include_profile=False)
            saved = generations._cache
            generations._cache = (time.monotonic(), ["g1"])
            try:
                after_r = context.get_context(q, include_profile=False)
            finally:
                generations._cache = saved
        finally:
            search._rerank = real
        today, after = today_r["text"].lower(), after_r["text"].lower()
        p = {"today": {"tokens": len(today) // 4}, "after_switch": {"tokens": len(after) // 4}}
        hit = lambda text: any(e.lower() in text for e in expected)  # noqa: E731
        rows.append({"q": q, "today": hit(today), "g1_only": hit(after), "tokens_today": p["today"]["tokens"],
                     "tokens_g1": p["after_switch"]["tokens"]})
    n = len(rows)
    out = {"questions": n, "today": sum(r["today"] for r in rows), "g1_only": sum(r["g1_only"] for r in rows),
           "median_tokens_today": sorted(r["tokens_today"] for r in rows)[n // 2],
           "median_tokens_g1": sorted(r["tokens_g1"] for r in rows)[n // 2], "seconds": round(time.time() - t0),
           "lost_after_switch": [r["q"] for r in rows if r["today"] and not r["g1_only"]],
           "gained_after_switch": [r["q"] for r in rows if r["g1_only"] and not r["today"]], "rows": rows}
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
