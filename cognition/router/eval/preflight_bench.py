"""Preflight bench (2026-11-14): 50 inputs, four decision models, the owner's blind reference, then his review.

Why: the decision model settles, for every input, what Walter prepares — which thread, what the input calls for, how
much context (C0-C4), which general tier (L1-L3), which modules' usage guide (D2), whether it is work to carry out
and follow. A wrong first decision costs a weak or needlessly expensive model, a missing or bloated context, a lost
thread. This bench measures it on the owner's own uses, on the target question set 3 (walter-context
`preflight-questions --set 3`: L/C/D, no task family, no delegation question), before the model is chosen.

Cases: 50, in the categories of the owner's brief (simple, short replies, thread switches, personal memory, module
documentation, complex work, ambiguity, other inputs). Authentic ones are drawn from the preflight journal (owner turns
in Walter Engine, cloud-safe, scrubbed: e-mails, numbers, links), rebuilt with the exchange before them and their
candidate subjects as of then; fictitious ones (@instance/config/router/preflight-bench-cases.json) cover the rest.
Each case carries the exact payload of its use, built by the preflight's own code.

Protocol: every model answers every case `SAMPLES` times through the same door (intent._decisions: same state, same
questions, same contract). Sample 1 = the single-call proposal shown to the owner; the mean of the samples (the
gateway's merge_answers, what production does with decision_samples = 3) is compared in the report. Answers are read
into plan fields by the preflight's own reader (`walter-context preflight-read`).

Blind: on the web page the owner first gives his own decision (reference), then sees four proposals labelled A-D in a
per-case random order, never the model names; he grades each field (correct / acceptable / incorrect), flags grave
errors, picks the proposal he prefers, comments, and may revise his reference (the blind one is kept). Model names
appear only in `report`. State in @instance/state/router/preflight-bench/ (0700); nothing goes to memory.
"""
from __future__ import annotations

import fcntl
import json
import random
import statistics
import subprocess
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance

MODELS = ("liquid/d1-ultra", "perplexity/pplx-decider-v1.3:free", "nace/drex-max-v1.1", "typesafe/jev-1.14")
# Perplexity Decider v1.3 (12/11) is on OpenRouter only as `:free` for its launch week (the paid id answers 404 on
# 14/11; Perplexity's own API needs a key the instance does not have). Same model, same contract.
SAMPLES = 3
CAP_USD = 1.0                       # well inside the 2 €/24 h test budget; measured cost ≈ 0.1 $ for the whole run
SEED = 20261114
WORKERS_PER_MODEL = 2
CATEGORIES = {"1_simple": "Demande simple, fait rapide, calcul", "2_court": "Échange court : accord, correction, merci",
              "3_fil": "Changement de sujet, reprise d'un fil", "4_memoire": "Mémoire personnelle, décisions anciennes",
              "5_docs": "Modules utiles (documentation)", "6_complexe": "Analyse complexe, travail long, tâche durable",
              "7_ambigu": "Intention ambiguë, contraintes contradictoires", "8_entrees": "Voix, bureau, connecteurs, API"}
WANT = {"1_simple": 8, "2_court": 8, "3_fil": 7, "4_memoire": 6, "5_docs": 6, "6_complexe": 5, "7_ambigu": 5,
        "8_entrees": 5}
YES_NO = [("yes", "Oui"), ("no", "Non")]
# What the owner decides, per case: field → (question, options). Options None = built from the case (thread, docs).
FIELDS = [
    ("handling", "Qu'appelle cette entrée ?", [("answer", "Répondre ou agir"), ("record", "La garder en mémoire"),
                                               ("notify", "Me prévenir"), ("ignore", "Rien")]),
    ("act", "Que fait ce message ?", [("new", "Nouveau sujet"), ("continue", "Suite du sujet"),
                                      ("approve", "Accord, go"), ("correct", "Corrige"), ("inform", "Informe")]),
    ("thread", "À quel fil appartient-il ?", None),
    ("C", "Que doit voir le modèle en plus du message ? (contexte)", [
        ("C0", "C0 · rien"), ("C1", "C1 · dernier échange"), ("C2", "C2 · historique du fil"),
        ("C3", "C3 · fil + mémoire"), ("C4", "C4 · recherche étendue")]),
    ("L", "Quel niveau de modèle ? (intelligence)", [("L1", "L1 · simple"), ("L2", "L2 · exigeant"),
                                                     ("L3", "L3 · très exigeant")]),
    ("docs", "Quels modules le modèle devrait-il savoir utiliser d'emblée ? (D2)", None),
    ("work", "Travail à mener et suivre (pas seulement répondre) ?", YES_NO),
    ("resume", "Reprend-il une tâche ouverte ?", YES_NO),
    ("domain", "Quel savoir sur vous compte le plus ?", [
        ("projects", "Projets"), ("profile", "Vous-même"), ("activities", "Activités"), ("relations", "Personnes"),
        ("agenda", "Agenda"), ("decisions", "Décisions"), ("goals", "Objectifs"), ("none", "Aucun")]),
    ("horizon", "Sur quelle période ?", [("instant", "Ces heures-ci"), ("day", "Aujourd'hui / hier"),
                                         ("medium", "Ces semaines"), ("long", "Des mois, des années"),
                                         ("stable", "Durable"), ("none", "Aucune")]),
]
MEMORY_ONLY = ("domain", "horizon")          # asked of the owner only when his context level carries memory (C3, C4)
GRADES = ("correct", "acceptable", "incorrect")
ORDINAL = {"C": ["C0", "C1", "C2", "C3", "C4"], "L": ["L1", "L2", "L3"]}
MODULE_NAMES = {"memory": "Memory", "logs": "Logs agents", "raw-vault": "Raw Vault", "secrets": "Secrets",
                "browse": "Browse (web)", "computer": "Computer (Mac)", "router": "Router (modèles)",
                "skills": "Skills", "ops": "Ops", "lab": "Lab", "soul": "Profil (soul)", "core": "Harnais (core)"}
_lock = threading.Lock()


# ── files ────────────────────────────────────────────────────────────────────────────────────────────────────────
def home() -> Path:
    p = instance.state_file("preflight-bench")
    p.mkdir(parents=True, exist_ok=True)
    p.chmod(0o700)
    return p


def _read(name: str, default):
    p = home() / name
    return json.loads(p.read_text()) if p.is_file() else default


def _write(name: str, data) -> None:
    p = home() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.chmod(0o600)
    tmp.replace(p)


def answers() -> list[dict]:
    p = home() / "answers.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []


def cases() -> list[dict]:
    return _read("cases.json", {}).get("cases") or []


def _cmd(args: list[str], stdin: str | None = None, timeout: int = 120):
    r = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])}: exit {r.returncode}")
    return json.loads(r.stdout)


# ── build ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _fictitious() -> list[dict]:
    spec = json.loads(instance.config_path("preflight-bench-cases.json").read_text())
    threads = spec["threads"]
    out = []
    for c in spec["cases"]:
        cands = [{"id": t, **threads[t]} for t in c.get("candidates") or []]
        out.append({**c, "source": "fictif", "candidates": cands})
    return out


def build(draw: str | None = None) -> dict:
    """cases.json: the authentic draw (`draw`: a JSON list made by the drawing step, default real-draw.json in the
    state folder) + fictitious cases up to WANT per category, each with its set 3 payload, in a seeded order."""
    if (home() / "answers.jsonl").is_file() or _read("reviews.json", {}):
        raise RuntimeError("bench already run or reviewed: move preflight-bench/ aside before rebuilding")
    real = json.loads(Path(draw).read_text()) if draw else _read("real-draw.json", [])
    fict = _fictitious()
    chosen, have = [], Counter()
    for c in real + fict:                      # authentic first; fictitious ones fill each category up to WANT
        if have[c["category"]] < WANT[c["category"]]:
            chosen.append(c)
            have[c["category"]] += 1
    if sum(have.values()) != 50:
        raise RuntimeError(f"50 cases expected, got {dict(have)}")
    rng = random.Random(SEED)
    built = []
    for c in chosen:
        p = _cmd(["walter-context", "preflight-questions", "--set", "3"], json.dumps(c, ensure_ascii=False))
        order = list(MODELS)
        rng.shuffle(order)
        built.append({"id": c["id"], "category": c["category"], "source": c["source"], "case": c,
                      "state": p["state"], "questions": p["questions"], "modules": p["modules"],
                      "fast_path": p.get("fast_path"), "letters": dict(zip("ABCD", order))})
    rng.shuffle(built)
    _write("cases.json", {"built_at": datetime.now(timezone.utc).isoformat(), "seed": SEED, "models": list(MODELS),
                          "samples": SAMPLES, "cases": built})
    return {"cases": len(built), "by_category": dict(have),
            "authentic": sum(c["source"] != "fictif" for c in built), "fast_path": sum(bool(c["fast_path"]) for c in built)}


# ── run (blind: nothing printed but counts) ─────────────────────────────────────────────────────────────────────────
def _price(conn, model: str) -> float | None:
    row = conn.execute("""select min(o.price_in_1m) p from models.offers o join models.latest_snapshots s using (snapshot_id)
                          where o.interface = 'decisions' and o.offer_key = %s""", (model.split(":")[0],)).fetchone()
    return row["p"] if row else None


def _call(conn, model: str, case: dict, sample: int, price: float | None) -> dict:
    from walter_router.serve import intent
    row = {"case": case["id"], "model": model, "sample": sample, "at": datetime.now(timezone.utc).isoformat()}
    err = None
    for attempt in range(3):                     # a rate limit (free endpoint) is retried, an answer error is not
        t0 = time.monotonic()
        try:
            a, data, ms, _ = intent._decisions(conn, case["state"], case["questions"], 40, models=(model,))
            usage = data.get("usage") or {}
            tok = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            cost = usage.get("cost")
            if cost is None and price is not None:
                cost = tok * price / 1e6
            row.update(ok=True, answers=a, ms=ms, input_tokens=tok, cost_usd=cost, served_by=data.get("model"))
            return row
        except Exception as exc:  # noqa: BLE001 — recorded, the report counts it
            err = f"{type(exc).__name__}: {exc}"[:240]
            row["ms"] = int((time.monotonic() - t0) * 1000)
            if "429" not in err:
                break
            time.sleep(8 * (attempt + 1))
    row.update(ok=False, error=err)
    return row


def run(models: tuple = MODELS, samples: int = SAMPLES) -> dict:
    from walter_router.store import db
    todo_cases = cases()
    if not todo_cases:
        raise RuntimeError("no cases: run `preflight-bench build` first")
    done = Counter((r["case"], r["model"], r["sample"]) for r in answers() if r.get("ok"))
    spent = sum(r.get("cost_usd") or 0 for r in answers())
    jobs = [(m, c, s) for s in range(1, samples + 1) for c in todo_cases for m in models if not done[(c["id"], m, s)]]
    with db.connect() as conn:
        prices = {m: _price(conn, m) for m in models}
    state = {"spent": spent, "cap": False}
    out = home() / "answers.jsonl"
    out.touch(exist_ok=True)
    out.chmod(0o600)                             # readings of the owner's messages: owner-only, like the other files
    sem ={m: threading.Semaphore(WORKERS_PER_MODEL) for m in models}

    def one(job):
        model, case, sample = job
        with _lock:
            if state["spent"] >= CAP_USD:
                state["cap"] = True
                return None
        with sem[model], db.connect() as c:
            row = _call(c, model, case, sample, prices[model])
        with _lock:
            state["spent"] += row.get("cost_usd") or 0
            with out.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row["ok"]

    with ThreadPoolExecutor(WORKERS_PER_MODEL * len(models)) as ex:
        res = list(ex.map(one, jobs))
    readings()
    return {"calls": len(jobs), "ok": sum(r is True for r in res), "failed": sum(r is False for r in res),
            "not_run_cap": sum(r is None for r in res), "spent_usd": round(state["spent"], 4), "cap_reached": state["cap"]}


def readings() -> dict:
    """readings.json: each answer (and each model's mean of samples) read into plan fields by the preflight's reader."""
    from walter_router.llm.structured import merge_answers
    by_case = {c["id"]: c for c in cases()}
    rows = [r for r in answers() if r.get("ok") and r["case"] in by_case]
    items, keys = [], []
    for r in rows:
        c = by_case[r["case"]]
        items.append({"case": c["case"], "answers": r["answers"], "modules": c["modules"]})
        keys.append(f"{r['case']}|{r['model']}|{r['sample']}")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["case"], r["model"])].append(r)
    for (cid, m), rs in groups.items():
        if len(rs) > 1:
            c = by_case[cid]
            typed = [{k: {**v, **({"type": "noul"} if (c["questions"].get(k) or {}).get("type") == "noul" else {})}
                      for k, v in r["answers"].items()} for r in sorted(rs, key=lambda x: x["sample"])]
            items.append({"case": c["case"], "answers": merge_answers(typed), "modules": c["modules"]})
            keys.append(f"{cid}|{m}|mean")
    out = {}
    for i in range(0, len(items), 200):
        part = _cmd(["walter-context", "preflight-read"], json.dumps({"items": items[i:i + 200]}, ensure_ascii=False))
        out.update(zip(keys[i:i + 200], part))
    _write("readings.json", out)
    return {"readings": len(out)}


# ── what the owner sees ──────────────────────────────────────────────────────────────────────────────────────────
def options(case: dict, key: str) -> list[tuple[str, str]]:
    given = dict((k, o) for k, _, o in FIELDS)[key]
    if given is not None:
        return given
    if key == "thread":
        return [(t["id"], t.get("title") or t["id"]) for t in case["case"].get("candidates") or []] + [("new", "Nouveau fil")]
    if key == "docs":
        return [(m["module"], MODULE_NAMES.get(m["module"], m["module"])) for m in case["modules"]]
    return []


def fields_of(case: dict) -> list[str]:
    """The fields that apply to a case: its questions say whether there is a thread or an open task to resume."""
    q = case["questions"]
    out = []
    for k, _, _ in FIELDS:
        if (k == "thread" and "thread" not in q) or (k == "resume" and "resume" not in q):
            continue
        out.append(k)
    return out


def case_view(case: dict) -> dict:
    """A case as shown (never a model's answer): input, its origin, previous exchange, candidate threads."""
    c = case["case"]
    return {"message": c["message"], "origin": c.get("origin") or {}, "previous": c.get("previous"),
            "candidates": [{k: t.get(k) for k in ("id", "title", "objective", "state", "task", "last_message",
                                                  "hours_since_last") if t.get(k) is not None}
                           for t in c.get("candidates") or []],
            "category": CATEGORIES[case["category"]], "source": "votre message" if case["source"] != "fictif" else "fictif",
            "modules": [{"module": m["module"], "name": MODULE_NAMES.get(m["module"], m["module"]), "line": m["line"]}
                        for m in case["modules"]]}


def proposal(case: dict, model: str) -> dict | None:
    """A model's single-call proposal for a case (sample 1), as plan fields + confidence."""
    return _read("readings.json", {}).get(f"{case['id']}|{model}|1")


def _same(key: str, a, b) -> bool:
    if key == "docs":
        return sorted(a or []) == sorted(b or [])
    return a == b


# ── the owner's review (file lock: the page is threaded) ─────────────────────────────────────────────────────────
class Frozen(ValueError):
    """The proposals of this case were shown: the blind reference cannot change any more (revise instead)."""


def _locked(fn):
    def wrapper(*a, **kw):
        with (home() / ".reviews.lock").open("w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            reviews = _read("reviews.json", {})
            out = fn(reviews, *a, **kw)
            _write("reviews.json", reviews)
            return out
    return wrapper


def _case(no: int) -> dict:
    return cases()[no]


def _check_value(case: dict, key: str, value):
    if key not in fields_of(case):
        raise ValueError(f"no field {key} here")
    allowed = {k for k, _ in options(case, key)}
    if key == "docs":
        if not isinstance(value, list) or not set(value) <= allowed:
            raise ValueError("docs: a list of modules")
        return sorted(set(value))
    if value is not None and value not in allowed:
        raise ValueError(f"{key}: unknown option")
    return value


def required(case: dict, ref: dict) -> list[str]:
    """Fields the owner still has to give for his reference to be complete (domain/horizon only with memory)."""
    need = [k for k in fields_of(case) if k not in MEMORY_ONLY or ref.get("C") in ("C3", "C4")]
    return [k for k in need if k not in ref]


@_locked
def set_reference(reviews: dict, no: int, key: str, value) -> dict:
    case = _case(no)
    rv = reviews.setdefault(case["id"], {"reference": {}})
    if rv.get("revealed_at"):
        raise Frozen(case["id"])
    rv["reference"][key] = _check_value(case, key, value)
    if key == "C" and value not in ("C3", "C4"):
        for k in MEMORY_ONLY:
            rv["reference"].pop(k, None)
    rv["done"] = not required(case, rv["reference"])
    rv["at"] = datetime.now(timezone.utc).isoformat()
    return rv


@_locked
def reveal(reviews: dict, no: int) -> dict:
    """The four proposals of a case, once its reference is complete; the reference freezes from then."""
    case = _case(no)
    rv = reviews.get(case["id"]) or {}
    if not rv.get("done"):
        raise ValueError("give your own decision first")
    if not rv.get("revealed_at"):
        rv["revealed_at"] = datetime.now(timezone.utc).isoformat()
        reviews[case["id"]] = rv
    return _proposals(case, rv)


def _proposals(case: dict, rv: dict) -> dict:
    ref = rv.get("revised") or rv["reference"]
    out = []
    for letter, model in case["letters"].items():
        p = proposal(case, model)
        if p is None:
            out.append({"letter": letter, "missing": True})
            continue
        grades = (rv.get("grades") or {}).get(letter) or {}
        f = {}
        for k in fields_of(case):
            if k in MEMORY_ONLY and ref.get("C") not in ("C3", "C4"):
                continue
            auto = "correct" if _same(k, p.get(k), ref.get(k)) else None
            ck = {"C": "plan", "L": "model_level"}.get(k, k)
            conf = (p.get("confidence") or {}).get(ck)
            f[k] = {"value": p.get(k), "confidence": conf, "grade": grades.get(k) or auto}
        out.append({"letter": letter, "fields": f, "grave": bool((rv.get("grave") or {}).get(letter))})
    return {"case": case["id"], "reference": rv["reference"], "revised": rv.get("revised"),
            "preferred": rv.get("preferred"), "comment": rv.get("comment") or "", "proposals": out,
            "note": case["case"].get("note")}


@_locked
def review(reviews: dict, no: int, body: dict) -> dict:
    """After the reveal: grade a field of a proposal, flag a grave error, prefer one, comment, revise the reference."""
    case = _case(no)
    rv = reviews.get(case["id"]) or {}
    if not rv.get("revealed_at"):
        raise ValueError("reveal first")
    what = body.get("what")
    if what == "grade":
        if body["letter"] not in case["letters"] or body["grade"] not in GRADES + (None,) or body["key"] not in fields_of(case):
            raise ValueError("bad grade")
        rv.setdefault("grades", {}).setdefault(body["letter"], {})[body["key"]] = body["grade"]
    elif what == "grave":
        if body["letter"] not in case["letters"]:
            raise ValueError("bad letter")
        rv.setdefault("grave", {})[body["letter"]] = bool(body["value"])
    elif what == "preferred":
        if body["value"] not in (*case["letters"], "none", None):
            raise ValueError("bad letter")
        rv["preferred"] = body["value"]
    elif what == "comment":
        rv["comment"] = str(body.get("value") or "")[:2000]
    elif what == "revise":
        rev = dict(rv.get("revised") or rv["reference"])
        rev[body["key"]] = _check_value(case, body["key"], body["value"])
        rv["revised"] = rev
    else:
        raise ValueError("unknown review action")
    rv["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    reviews[case["id"]] = rv
    return _proposals(case, rv)


def status() -> dict:
    cs = cases()
    rv = _read("reviews.json", {})
    rows = answers()
    return {"cases": len(cs), "referenced": sum(bool(v.get("done")) for v in rv.values()),
            "revealed": sum(bool(v.get("revealed_at")) for v in rv.values()),
            "model_answers": sum(bool(r.get("ok")) for r in rows), "model_failures": sum(not r.get("ok") for r in rows),
            "spent_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4)}


# ── report (after the owner's review; the only place model names appear) ───────────────────────────────────────────
def _pct(a: int, n: int):
    return round(a / n, 3) if n else None


def _q(xs: list, q: float):
    xs = sorted(xs)
    return xs[min(int(len(xs) * q), len(xs) - 1)] if xs else None


def report(daily_inputs: int | None = None) -> dict:
    """Per model: agreement with the owner (strict = his blind reference, lenient = what he graded correct or
    acceptable), per field and overall; grave errors; under/over-sizing of C and L; docs precision/recall; thread;
    work/resume; stability across samples; calibration; latency; cost; single call vs mean of samples; preferences."""
    cs = {c["id"]: c for c in cases()}
    rv = _read("reviews.json", {})
    rd = _read("readings.json", {})
    rows = answers()
    if daily_inputs is None:            # the preflight's real volume (journal, last 7 days)
        daily_inputs = _daily_volume()
    out = {"cases_reviewed": 0, "daily_inputs": daily_inputs, "models": {}}
    reviewed = [cid for cid, v in rv.items() if v.get("done") and cid in cs]
    out["cases_reviewed"] = len(reviewed)
    for m in MODELS:
        mine = [r for r in rows if r["model"] == m]
        ok = [r for r in mine if r.get("ok")]
        ms = [r["ms"] for r in ok]
        cost = [r.get("cost_usd") or 0 for r in ok]
        per = {"calls": len(mine), "failures": len(mine) - len(ok), "p50_ms": _q(ms, .5), "p90_ms": _q(ms, .9),
               "usd_per_decision": round(statistics.mean(cost), 7) if cost else None}
        if cost:
            per["usd_per_month_1_call"] = round(statistics.mean(cost) * daily_inputs * 30, 3)
            per["usd_per_month_3_samples"] = round(statistics.mean(cost) * daily_inputs * 30 * 3, 3)
        for variant in ("1", "mean"):
            strict, lenient, n_f = Counter(), Counter(), Counter()
            under, over, grave, cal = Counter(), Counter(), 0, []
            docs_tp = docs_fp = docs_fn = 0
            for cid in reviewed:
                c, v = cs[cid], rv[cid]
                p = rd.get(f"{cid}|{m}|{variant}")
                if not p:
                    continue
                ref = v.get("revised") or v["reference"]
                blind = v["reference"]
                letter = next(k for k, x in c["letters"].items() if x == m)
                grades = (v.get("grades") or {}).get(letter) or {}
                grave += variant == "1" and bool((v.get("grave") or {}).get(letter))
                for k in fields_of(c):
                    if k not in blind:
                        continue
                    if blind[k] is None:            # « ? » : no gold
                        continue
                    n_f[k] += 1
                    hit = _same(k, p.get(k), blind[k])
                    strict[k] += hit
                    g = grades.get(k) if variant == "1" else None
                    lenient[k] += hit or g in ("correct", "acceptable") or _same(k, p.get(k), ref.get(k))
                    if k in ORDINAL and p.get(k) in ORDINAL[k] and blind[k] in ORDINAL[k]:
                        d = ORDINAL[k].index(p[k]) - ORDINAL[k].index(blind[k])
                        under[k] += d < 0
                        over[k] += d > 0
                    if k == "docs":
                        got, want = set(p.get("docs") or []), set(blind["docs"] or [])
                        docs_tp += len(got & want)
                        docs_fp += len(got - want)
                        docs_fn += len(want - got)
                    ck = {"C": "plan", "L": "model_level"}.get(k, k)
                    conf = (p.get("confidence") or {}).get(ck)
                    if conf is not None and k != "docs":
                        cal.append((conf, hit))
            fields = {k: {"strict": _pct(strict[k], n_f[k]), "lenient": _pct(lenient[k], n_f[k]), "n": n_f[k],
                          **({"under": under[k], "over": over[k]} if k in ORDINAL else {})} for k in n_f}
            tot = sum(n_f.values())
            res = {"overall_strict": _pct(sum(strict.values()), tot), "overall_lenient": _pct(sum(lenient.values()), tot),
                   "fields": fields,
                   "docs": {"precision": _pct(docs_tp, docs_tp + docs_fp), "recall": _pct(docs_tp, docs_tp + docs_fn)},
                   "calibration": _calibration(cal)}
            if variant == "1":
                res["grave_errors"] = grave
                res["preferred"] = sum(1 for cid in reviewed if rv[cid].get("preferred") ==
                                       next(k for k, x in cs[cid]["letters"].items() if x == m))
            per["single_call" if variant == "1" else "mean_of_samples"] = res
        per["stability"] = _stability(m, cs, rd)
        out["models"][m] = per
    _write("report.json", out)
    return out


def _calibration(pairs: list) -> dict:
    """Mean confidence when right / wrong, and the gap between confidence and accuracy per band (ECE)."""
    if not pairs:
        return {}
    bands = defaultdict(list)
    for conf, hit in pairs:
        bands[min(int(conf * 5), 4)].append((conf, hit))
    ece = sum(len(v) / len(pairs) * abs(statistics.mean(c for c, _ in v) - statistics.mean(h for _, h in v))
              for v in bands.values())
    right = [c for c, h in pairs if h]
    wrong = [c for c, h in pairs if not h]
    return {"ece": round(ece, 3), "confidence_right": round(statistics.mean(right), 3) if right else None,
            "confidence_wrong": round(statistics.mean(wrong), 3) if wrong else None, "n": len(pairs)}


def _stability(model: str, cs: dict, rd: dict) -> dict:
    """Share of (case, field) where all samples give the same reading."""
    same, n = Counter(), Counter()
    for cid, c in cs.items():
        reads = [rd.get(f"{cid}|{model}|{s}") for s in range(1, SAMPLES + 1)]
        reads = [r for r in reads if r]
        if len(reads) < 2:
            continue
        for k in fields_of(c):
            vals = [json.dumps(sorted(r.get(k) or []) if k == "docs" else r.get(k)) for r in reads]
            n[k] += 1
            same[k] += len(set(vals)) == 1
    tot = sum(n.values())
    return {"overall": _pct(sum(same.values()), tot), **{k: _pct(same[k], n[k]) for k in n}}


def _daily_volume() -> int:
    """Preflight decisions per day (journal, last 7 complete days; fast paths and local_only excluded)."""
    import glob
    base = instance.state_file("x").parent.parent / "context" / "shadow"
    days = sorted(glob.glob(str(base / "preflight-*.jsonl")))[-8:-1]
    counts = []
    for f in days:
        n = 0
        for line in Path(f).read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            n += bool(((d.get("plan") or {}).get("decision") or {}).get("model"))
        counts.append(n)
    return round(statistics.mean(counts)) if counts else 100
