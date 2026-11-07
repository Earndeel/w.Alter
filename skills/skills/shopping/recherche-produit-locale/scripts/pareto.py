#!/usr/bin/env python3
"""Pareto front of sourced offers — deterministic, stdlib only (walter skill recherche-produit-locale).

Input (stdin or a file): a JSON list of offers, or `walter-memory observations run <run_id>` output. Each offer is
an Observation v1 ({subject, seller, source_url, values{price, currency, volume|volume_ml, sugar_g, …}}) or the same
fields flat. Units are normalised (ml, cl, l, oz, fl oz → ml; g, kg → g), price per 100 ml is derived when price and
volume are known. Unknown values stay unknown: an offer missing one of the chosen dimensions is listed apart as
"not comparable on …", never given a bad score.

  pareto.py --min price --min price_per_100ml --max volume_ml [--min sugar_g] [--weights price_per_100ml=2,…] [FILE]

Output JSON: {front: [...], dominated: [...], not_comparable: [...], ranking: [...] (only with --weights),
dimensions, currency_mixed}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

ML = {"ml": 1.0, "cl": 10.0, "l": 1000.0, "oz": 29.5735, "floz": 29.5735, "fl oz": 29.5735, "ออนซ์": 29.5735}
G = {"g": 1.0, "kg": 1000.0, "mg": 0.001}


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group().replace(",", ".")) if m else None


def volume_ml(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace("fl. oz", "floz").replace("fl oz", "floz")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(floz|oz|ออนซ์|ml|cl|l)\b", s) or re.search(r"(\d+(?:[.,]\d+)?)\s*(floz|oz|ออนซ์|ml|cl|l)", s)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) * ML[m.group(2)], 1)


def grams(v):
    if v is None or isinstance(v, (int, float)):
        return None if v is None else float(v)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|kg|g)\b", str(v).lower())
    return round(float(m.group(1).replace(",", ".")) * G[m.group(2)], 2) if m else _num(v)


def normalise(o: dict) -> dict:
    a = o.get("attributes") or o                     # a row of `walter-memory observations run`, or a bare offer
    vals = {**{k: a.get(k) for k in ("price", "prix", "currency", "volume", "volume_ml", "sugar_g", "caffeine_mg")
               if a.get(k) is not None}, **(a.get("values") or {})}
    price = _num(vals.get("price", vals.get("prix")))
    vol = volume_ml(vals.get("volume_ml")) if vals.get("volume_ml") is not None else volume_ml(vals.get("volume"))
    out = {"subject": a.get("subject") or a.get("produit"), "seller": a.get("seller"),
           "source_url": a.get("source_url") or a.get("url_source"), "currency": vals.get("currency"),
           "price": price, "volume_ml": vol,
           "price_per_100ml": round(price / vol * 100, 2) if price is not None and vol else None,
           "sugar_g": grams(vals.get("sugar_g")), "caffeine_mg": _num(vals.get("caffeine_mg"))}
    for k, v in vals.items():                        # any other numeric criterion passed through as is
        if k not in out and k not in ("prix", "volume"):
            out[k] = _num(v) if not isinstance(v, str) or re.search(r"\d", v) else v
    return out


def dominates(a: dict, b: dict, dims: list[tuple[str, str]]) -> bool:
    better = False
    for d, sense in dims:
        x, y = a[d], b[d]
        if (sense == "min" and x > y) or (sense == "max" and x < y):
            return False
        if x != y:
            better = True
    return better


def pareto(offers: list[dict], dims: list[tuple[str, str]], weights: dict[str, float] | None = None) -> dict:
    items = [normalise(o) for o in offers]
    names = [d for d, _ in dims]
    comparable = [i for i in items if all(i.get(d) is not None for d in names)]
    apart = [{**i, "missing": [d for d in names if i.get(d) is None]} for i in items if i not in comparable]
    front = [i for i in comparable if not any(dominates(j, i, dims) for j in comparable if j is not i)]
    dominated = [{**i, "dominated_by": [j["subject"] for j in comparable if j is not i and dominates(j, i, dims)]}
                 for i in comparable if i not in front]
    out = {"dimensions": [f"{s}:{d}" for d, s in dims], "front": front, "dominated": dominated,
           "not_comparable": apart, "currency_mixed": len({i["currency"] for i in comparable if i["currency"]}) > 1}
    if weights and comparable:
        def score(i):                                # min-max normalised, sense-aware, weighted; front first
            s = 0.0
            for d, sense in dims:
                w = weights.get(d, 0.0)
                vals = [c[d] for c in comparable]
                lo, hi = min(vals), max(vals)
                n = 0.5 if hi == lo else (i[d] - lo) / (hi - lo)
                s += w * (1 - n if sense == "min" else n)
            return round(s, 4)
        out["ranking"] = sorted(({"subject": i["subject"], "seller": i["seller"], "score": score(i),
                                  "on_front": i in front} for i in comparable), key=lambda r: (-r["on_front"], -r["score"]))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("file", nargs="?"); p.add_argument("--min", action="append", default=[])
    p.add_argument("--max", action="append", default=[]); p.add_argument("--weights", default="")
    a = p.parse_args()
    data = json.load(open(a.file) if a.file else sys.stdin)
    offers = data if isinstance(data, list) else data.get("observations") or data.get("offers") or []
    dims = [(d, "min") for d in a.min] + [(d, "max") for d in a.max]
    if not dims:
        p.error("at least one --min or --max dimension")
    weights = {k: float(v) for k, v in (x.split("=") for x in a.weights.split(",") if x)} if a.weights else None
    print(json.dumps(pareto(offers, dims, weights), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
