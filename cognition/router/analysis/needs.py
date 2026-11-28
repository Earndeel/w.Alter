"""What each poste really uses (models.poste_needs) and whether a challenger can do it (owner 2026-11-22: D1.2 Ultra
was kept for several decisions per call and image reading, not for one AA point; « il faut prendre en compte des
choses plus larges »).

Observed: the walter-llm journal (counts the gateway writes per call: part types, tools, JSON, n, token sizes; never
content). Declared: the Walter Decision needs (question kinds). Checked against models.model_details, which comes
from free catalogues: nothing is run to know what a model can do."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from walter_router import instance, paths

WINDOW_DAYS = 14
TAIL_BYTES = 40_000_000
SCALARS = {"tools", "format", "n", "max_tokens", "max_completion_tokens", "logprobs", "kinds"}
PART_TO_MODALITY = {"image_url": "image", "input_image": "image", "image": "image", "input_audio": "audio",
                    "audio": "audio", "file": "file", "input_file": "file", "video_url": "video", "video": "video"}


def _journal_lines(tail_bytes: int = TAIL_BYTES) -> list[bytes]:
    path = instance.gateway_journal()
    with open(path, "rb") as fh:
        fh.seek(max(0, path.stat().st_size - tail_bytes))
        return fh.read().splitlines()[1:]


def _split(task: str) -> tuple[str, str]:
    t, _, lv = (task or "").partition("/")
    return t, lv if lv in ("L1", "L2", "L3") else ""


def observed(window_days: int = WINDOW_DAYS, lines: list[bytes] | None = None) -> dict[tuple[str, str], dict]:
    try:
        lines = _journal_lines() if lines is None else lines
    except (OSError, ValueError, KeyError):
        return {}
    horizon = time.time() - window_days * 86400
    acc: dict[tuple[str, str], dict] = {}
    for raw in lines:
        try:
            e = json.loads(raw)
            t = datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00")).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if t < horizon or e.get("event") or not e.get("provider") or not e.get("ok") or not e.get("task"):
            continue
        if str(e["task"]).startswith("exact:"):
            continue
        a = acc.setdefault(_split(e["task"]), {"calls": 0, "with_needs": 0, "inputs": {}, "tools": 0, "json": 0,
                                               "n": 1, "in": [], "out": 0})
        a["calls"] += 1
        n = e.get("needs")
        if isinstance(n, dict):                      # journaled since 2026-11-22
            a["with_needs"] += 1
        n = n if isinstance(n, dict) else {}
        for part in {PART_TO_MODALITY.get(k, k) for k in n if k not in SCALARS}:
            a["inputs"][part] = a["inputs"].get(part, 0) + 1
        a["tools"] += bool(n.get("tools"))
        a["json"] += n.get("format") in ("json_object", "json_schema")
        a["n"] = max(a["n"], int(n.get("n") or 1))
        for k in n.get("kinds") or {}:
            a.setdefault("kinds", set()).add(k)
        u = e.get("usage") or {}
        if isinstance(u.get("in"), (int, float)):
            a["in"].append(int(u["in"]) + int(u.get("cached") or 0))
        if isinstance(u.get("out"), (int, float)):
            a["out"] = max(a["out"], int(u["out"]))
    out = {}
    for key, a in acc.items():
        base = a["with_needs"] or None               # shares only from calls that carry the counts
        ins = sorted(a["in"])
        out[key] = {"calls": a["calls"],
                    "inputs": {k: round(v / base, 3) for k, v in a["inputs"].items()} if base else {},
                    "tools_share": round(a["tools"] / base, 3) if base else None,
                    "json_share": round(a["json"] / base, 3) if base else None,
                    "max_n": a["n"] if base else None,
                    "input_tokens_p95": ins[int(0.95 * (len(ins) - 1))] if ins else None,
                    "input_tokens_max": ins[-1] if ins else None,
                    "output_tokens_max": a["out"] or None, "kinds": sorted(a.get("kinds") or ())}
    return out


def declared_decision_kinds() -> list[str]:
    try:
        sys.path.insert(0, str(paths.ROOT / "llm"))
        import decision as wd
        return sorted({k for spec in wd.needs().values() for k in spec.get("types") or []})
    except Exception:  # noqa: BLE001 — no registry, no declared kinds
        return []


def refresh(conn, window_days: int = WINDOW_DAYS) -> int:
    rows = observed(window_days)
    if not rows:
        return 0
    kinds = declared_decision_kinds()
    conn.execute("delete from models.poste_needs")
    for (task, level), r in rows.items():
        conn.execute("""insert into models.poste_needs (task, level, calls, window_days, inputs, tools_share, json_share,
                        max_n, input_tokens_p95, input_tokens_max, output_tokens_max, decision_kinds)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (task, level, r["calls"], window_days, json.dumps(r["inputs"]), r["tools_share"], r["json_share"],
                      r["max_n"], r["input_tokens_p95"], r["input_tokens_max"], r["output_tokens_max"],
                      (r["kinds"] or kinds) if task.startswith("decision") else None))
    return len(rows)


def fit(conn, task: str, model_id: str, level: str | None = None) -> dict:
    """What the poste uses that `model_id` keeps, loses, or no free catalogue says. -> {"kept", "lost", "unknown"},
    each a list of short French phrases, and "basis" (what the poste uses, in words)."""
    rows = list(conn.execute("""select * from models.poste_needs where task = %s and (%s::text is null or level = %s)""",
                             (task, level, level)))
    d = conn.execute("select * from models.model_details where model_id = %s", (model_id,)).fetchone()
    kept, lost, unknown = [], [], []
    if not rows:
        return {"kept": kept, "lost": lost, "unknown": ["aucun appel réel observé sur ce poste"], "basis": None}
    ins = sorted({k for r in rows for k, v in (r["inputs"] or {}).items() if v})
    tools = max((r["tools_share"] or 0) for r in rows)
    js = max((r["json_share"] or 0) for r in rows)
    n = max((r["max_n"] or 1) for r in rows)
    need_ctx = max((r["input_tokens_max"] or 0) for r in rows)
    need_out = max((r["output_tokens_max"] or 0) for r in rows)
    params = set((d or {}).get("parameters") or [])
    modal = set((d or {}).get("input_modalities") or [])

    def judge(label, ok):
        (unknown if ok is None else kept if ok else lost).append(label)
    for m in ins:
        judge(f"lit {m}", (m in modal) if modal else None)
    if tools:
        judge(f"outils ({tools:.0%} des appels)", ("tools" in params) if params else None)
    if js:
        judge(f"réponse JSON ({js:.0%} des appels)",
              bool({"response_format", "structured_outputs"} & params) if params else None)
    if n > 1:
        judge(f"{n} réponses par appel", ("n" in params) if params else None)
    if need_ctx:
        judge(f"contexte ≥ {need_ctx:,} tokens".replace(",", " "),
              (d["context_length"] >= need_ctx) if d and d["context_length"] else None)
    if need_out:
        judge(f"réponse ≥ {need_out:,} tokens".replace(",", " "),
              (d["max_output_tokens"] >= need_out) if d and d["max_output_tokens"] else None)
    basis = {"appels": sum(r["calls"] for r in rows), "fenêtre_jours": rows[0]["window_days"]}
    if any(r["decision_kinds"] for r in rows):
        basis["décisions_demandées"] = sorted({k for r in rows for k in r["decision_kinds"] or []})
        unknown.append("types de décision : à vérifier dans `walter-router decision-needs` (le Router ne sait les "
                       "constater que pour les modèles de la chaîne)")
    return {"kept": kept, "lost": lost, "unknown": unknown, "basis": basis}


FEATURES = {"image": "lit les images", "audio": "entend l'audio", "video": "lit la vidéo", "file": "lit les fichiers",
            "tools": "outils", "structured_outputs": "JSON strict", "n": "plusieurs réponses par appel",
            "reasoning": "raisonnement réglable"}


def _features(d: dict | None) -> set[str]:
    if not d:
        return set()
    return ({m for m in d.get("input_modalities") or [] if m in FEATURES}
            | {p for p in d.get("parameters") or [] if p in FEATURES}
            | ({"reasoning"} if d.get("reasoning_efforts") else set()))


def compare(conn, task: str, challenger: str, current: str | None, level: str | None = None) -> dict:
    """The poste's real use checked on the challenger (`fit`), plus what the current model can do that the challenger
    cannot, and the reverse — from free catalogues only, `unknown` when none says."""
    out = fit(conn, task, challenger, level)
    if current:
        get = lambda m: conn.execute("select * from models.model_details where model_id = %s", (m,)).fetchone()
        a, b = get(challenger), get(current)
        if a and b:
            fa, fb = _features(a), _features(b)
            out["only_current"] = [FEATURES[f] for f in sorted(fb - fa)]
            out["only_challenger"] = [FEATURES[f] for f in sorted(fa - fb)]
        else:
            out["unknown"] = out["unknown"] + [f"fiche absente : {m}" for m, d in ((challenger, a), (current, b)) if not d]
    return out
