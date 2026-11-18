"""Préflight natif bench (2026-11-18): the live preflight, as configured, on the instance's reference set — real owner
messages taken from walter_logs plus synthetic cases (implicit location, appointment, project, last conversation,
image, voice note, ambiguity) — scored against expected answers written by hand before any measure.

    PYTHONPATH=/walter/cognition/context:/walter/cognition/memory walter-python bench/preflight_native.py run --label old
    … bench/preflight_native.py report --labels old,new

The reference set lives in the instance (`@instance/state/context/bench/preflight-gold-*.json`), never in /walter:
it holds real messages. Results and reports go there too; a report prints aggregates only, never a message.

`run` drives the real path in this process — walter_context.preflight.__main__.handle(want_pack=True): the decision
through walter-llm (live models; each case's calls are journalled in system.model_calls under the purpose
« bench pfn <label> <case> », which gives the calls and the cost per case), then the pack read from Walter Memory.
Nothing else is written (preflight record and bus signal are switched off; no thread candidates: the owner's current
threads are not those of the time the message was sent)."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/walter/core")
from walter_platform import instance  # noqa: E402

BENCH = Path(instance.state("context", "bench"))
MEMORY_BLOCKS = {"memory", "records", "subject", "experience", "people", "board"}


def _gold_file(name: str = "gold") -> Path:
    """`gold` = the cases the corrections were made against; `indep` = cases written before any correction, never
    used to make one (validation of the generalisation, 18/11)."""
    return sorted(BENCH.glob(f"preflight-{name}-*.json"))[-1]


def _pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def _request(case: dict, label: str) -> dict:
    msg = case["message"].replace("@bench/", str(BENCH) + "/")
    d = {"turn_id": f"bench-pfn-{label}-{case['id']}", "message": msg, "privacy_class": "cloud_allowed",
         "runtime": "walter", "candidates": []}
    if case.get("previous"):
        p = case["previous"]
        d["previous"] = {"message": p["message"], "answer": p["answer"], "age_s": p["minutes_ago"] * 60}
    if case.get("media"):
        d["attachments"] = [{"type": m["type"], "path": str(BENCH / m["path"])} for m in case["media"]]
    return d


def _calls(purpose_prefix: str, since: datetime) -> dict:
    """{case: {calls, cost_usd, models, failed, hedged}} from the gateway journal, for this run only. A question the
    gateway did not send to a model (`unsupported`) is no call; a hedge cancelled in flight is one (`hedged`)."""
    import psycopg
    out: dict = {}
    with psycopg.connect(host="127.0.0.1", port=5433, dbname="hindsight", user="hindsight") as c:
        for purpose, model, status, err, n, cost in c.execute(
                "select purpose, model, status, error, count(*), coalesce(sum(cost_usd), 0) from system.model_calls "
                "where purpose like %s and at >= %s group by 1, 2, 3, 4", (purpose_prefix + "%", since)):
            if status == "dropped" and err != "hedged":
                continue
            case = purpose.rsplit(" ", 1)[-1]
            o = out.setdefault(case, {"calls": 0, "cost_usd": 0.0, "models": {}, "failed": 0, "hedged": 0})
            o["calls"] += n
            o["cost_usd"] += float(cost)
            o["models"][model] = o["models"].get(model, 0) + n
            o["hedged"] += n if status == "dropped" else 0
            o["failed"] += n if status not in ("ok", "success", "dropped", None) else 0
    return out


def run(label: str, limit: int | None, only: list[str] | None, need: str | None = None,
        apart: bool | None = None, without: list[str] | None = None, set_name: str = "gold") -> Path:
    from walter_context.preflight import __main__ as pm
    from walter_memory import llm
    if apart is not None:                               # the candidate's readings setting ([preflight] readings_apart)
        from walter_context import preflight as pf
        pf.READINGS_APART = apart
    pm._record = lambda row: None                       # noqa: E731 — no preflight journal line for a bench turn
    pm._signal_degraded = lambda d, plan: None          # noqa: E731 — no bus signal
    pm.subjects = lambda d: ([], None, None)            # noqa: E731 — no thread candidates (see module doc)
    real = llm.decide
    cur: dict = {"box": {}}

    def decide(*a, **kw):
        box = cur["box"]
        kw["purpose"] = f"bench pfn {label} {box['case']}"
        if need:                                         # a candidate policy of the gateway (decision-needs.json)
            kw["processor"] = need
        if without and kw.get("models"):                 # a route taken out of the chain (an outage, simulated)
            kw["models"] = [m for m in kw["models"] if m not in without]
        reading = kw.get("layers") == ["observation"]
        key = "readings" if reading else "decision"
        t = time.perf_counter()
        try:
            res = real(*a, **kw)
        except Exception as exc:
            box[f"{key}_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            box[f"{key}_ms"] = round((time.perf_counter() - t) * 1000)
            raise
        box[f"{key}_ms"] = round((time.perf_counter() - t) * 1000)
        box["readings_res" if reading else "res"] = res
        return res
    llm.decide = decide

    started = datetime.now(timezone.utc)
    gold = json.loads(_gold_file(set_name).read_text())
    cases = [c for c in gold["cases"] if not only or c["id"] in only][:limit]
    from walter_context.preflight import owner_today
    tag = "" if set_name == "gold" else f"{set_name}-"
    out = BENCH / f"pfn-{tag}{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')}.jsonl"
    with out.open("a") as f:
        for i, case in enumerate([{"id": "warm", "message": "Fais le point sur la journée"}] * 2 + cases):
            cur["box"] = box = {"case": case["id"]}
            t = time.perf_counter()
            try:
                plan, row = pm.handle(_request(case, label), shadow=False, want_pack=True)
            except Exception as exc:  # noqa: BLE001
                plan, row = {}, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            wall = round((time.perf_counter() - t) * 1000)
            if case["id"] == "warm":
                continue
            plan = plan or {}
            dec = plan.get("decision") or {}
            pk = row.get("pack") or {}
            rec = {"label": label, "case": case["id"], "src": case.get("src"), "wall_ms": wall,
                   "decision_ms": box.get("decision_ms"), "readings_ms": box.get("readings_ms"),
                   "plan_ms": row.get("plan_ms"), "total_ms": row.get("total_ms"),
                   "degraded": bool(dec.get("degraded")), "error": box.get("decision_error") or row.get("error"),
                   "fast_path": plan.get("fast_path"), "model": dec.get("model"), "parts": dec.get("parts"),
                   "act": plan.get("act"), "level": plan.get("level"), "caps": plan.get("capabilities") or [],
                   "personal": plan.get("personal"), "observations": plan.get("observations") or {},
                   "assessment": plan.get("assessment"), "media": plan.get("media"),
                   "pack": {"tokens": pk.get("tokens_per_message"), "retrieval_ms": pk.get("retrieval_ms"),
                            "blocks": [b.get("id") for b in pk.get("blocks") or []], "late": pk.get("late"),
                            "block_tokens": {b.get("id"): b.get("tokens") for b in pk.get("blocks") or []}},
                   "owner_today": owner_today(), "signals": _raw(box.get("res")),
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{case['id']} {wall} ms", file=sys.stderr, flush=True)
    time.sleep(2)
    calls = _calls(f"bench pfn {label} ", started)
    recs = [json.loads(x) for x in out.read_text().splitlines()]
    with out.open("w") as f:
        for r in recs:
            r["calls"] = calls.get(r["case"], {"calls": 0, "cost_usd": 0.0, "models": {}, "failed": 0})
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(out)
    return out


def _raw(res) -> dict:
    """The decision as the model gave it, compact: probabilities by option, nouls, spans (text, day read, found), and
    what the resolver changed — to tell a model miss from a resolver or plan miss."""
    if not isinstance(res, dict):
        return {}
    out = {}
    for k, v in (res.get("signals") or {}).items():
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("spans"), list):
            out[k] = [{f: s.get(f) for f in ("text", "date", "end", "found", "read_by") if s.get(f) is not None}
                      for s in v["spans"] if isinstance(s, dict)]
        elif v.get("probabilities"):
            out[k] = {o: round(p, 3) for o, p in v["probabilities"].items() if isinstance(p, (int, float))}
        elif isinstance(v.get("noul"), (int, float)):
            out[k] = round(v["noul"], 3)
    ch = (res.get("resolution") or {}).get("changed")
    if ch:
        out["_changed"] = {k: (v or {}).get("by") for k, v in ch.items()}
    return out


def _accepted(spec: str, today: str) -> set[str]:
    """A date expectation relative to the owner's day of the run → the readings accepted ('YYYY-MM-DD' or
    'start..end'). d+N, d-N, week-1, weekend-1, month-1, month0td, monthend, dow+thu[+7], md+N, an ISO day, a..b."""
    import calendar
    from datetime import date, timedelta
    t = date.fromisoformat(today)
    iso = lambda d: d.isoformat()                                         # noqa: E731

    def one(x: str) -> str:
        if x.startswith("d") and x[1:2] in "+-" and x[2:].isdigit():
            return iso(t + timedelta(days=int(x[1:])))
        if x == "d0":
            return iso(t)
        if x == "monthend":
            return iso(t.replace(day=calendar.monthrange(t.year, t.month)[1]))
        return x
    if ".." in spec and not spec.startswith(("week", "weekend", "month")):
        a, b = spec.split("..")
        return {f"{one(a)}..{one(b)}"}
    if spec.startswith("*.."):                                           # any period ending on that day
        return {"*.." + one(spec[3:])}
    if spec == "week0":
        mon = t - timedelta(days=t.weekday())
        return {f"{iso(mon)}..{iso(mon + timedelta(days=6))}"}
    if spec == "week+1":
        mon = t - timedelta(days=t.weekday()) + timedelta(days=7)
        return {f"{iso(mon)}..{iso(mon + timedelta(days=6))}"}
    if spec == "week-1":
        mon = t - timedelta(days=t.weekday() + 7)
        return {f"{iso(mon)}..{iso(mon + timedelta(days=6))}"}
    if spec == "weekend-1":
        sat = t - timedelta(days=(t.weekday() - 5) % 7 or 7)
        return {f"{iso(sat)}..{iso(sat + timedelta(days=1))}"}
    if spec == "month-1":
        last = t.replace(day=1) - timedelta(days=1)
        return {f"{iso(last.replace(day=1))}..{iso(last)}"}
    if spec == "month0td":
        return {f"{iso(t.replace(day=1))}..{iso(t)}"}
    if spec.startswith(("dow+", "dow-")):                                 # the next / the last such weekday
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        w, _, extra = spec[4:].partition("+")
        if spec[3] == "+":
            d = t + timedelta(days=(days.index(w) - t.weekday()) % 7 or 7) + timedelta(days=int(extra or 0))
        else:
            d = t - timedelta(days=(t.weekday() - days.index(w)) % 7 or 7)
        return {iso(d)}
    if spec.startswith("md+"):
        n, y, m = int(spec[3:]), t.year, t.month
        for _ in range(2):
            try:
                d = date(y, m, n)
                if d >= t:
                    return {iso(d)}
            except ValueError:
                pass
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return set()
    return {one(spec)}


def _date_reads(r: dict) -> list[tuple[str, str]]:
    """(text, reading) of the plan's dates: 'start' or 'start..end' for a period."""
    out = []
    for o in (r.get("observations") or {}).get("dates") or []:
        if isinstance(o, dict) and o.get("date"):
            out.append((o.get("text", ""), o["date"] + (f"..{o['end']}" if o.get("end") else "")))
    return out


# ── scoring ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _match(expected: list[str], got: list[str]) -> tuple[int, int, int]:
    got = [g.lower().strip(" .,!?'«»") for g in got if g]
    good = sum(1 for e in expected if any(e.lower() in g or g in e.lower() for g in got if g))
    extra = sum(1 for g in got if not any(e.lower() in g or g in e.lower() for e in expected))
    return good, len(expected), extra


def _texts(obs: dict, key: str) -> list[str]:
    return [o.get("text", "") for o in (obs or {}).get(key) or [] if isinstance(o, dict)]


def _level(lv) -> int | None:
    try:
        return int(str(lv).lstrip("L"))
    except (TypeError, ValueError):
        return None


def score(recs: list[dict], gold: dict) -> dict:
    G = {c["id"]: c["gold"] for c in gold["cases"]}
    m = {k: [0, 0] for k in ("act", "needs_hit", "needs_false", "personal_hit", "personal_false", "pack_hit",
                             "level_min", "level_max", "clarity", "urgency", "image", "date_value")}
    spans = {k: [0, 0, 0] for k in ("places", "people", "dates", "amounts")}
    per: dict = {}
    for r in recs:
        g = G.get(r["case"])
        if g is None:
            continue
        ok = {}
        caps = set(r.get("caps") or [])
        pers = set(r.get("personal") or [])
        blocks = set((r.get("pack") or {}).get("blocks") or [])
        if "act" in g:
            m["act"][1] += 1; m["act"][0] += r.get("act") in g["act"]; ok["act"] = r.get("act") in g["act"]
        for n in g.get("needs", []):
            m["needs_hit"][1] += 1; m["needs_hit"][0] += n in caps
        for n in g.get("needs_not", []):
            m["needs_false"][1] += 1; m["needs_false"][0] += n in caps
        for n in g.get("personal", []):
            m["personal_hit"][1] += 1; m["personal_hit"][0] += n in pers
        for n in g.get("personal_not", []):
            m["personal_false"][1] += 1; m["personal_false"][0] += n in pers
        for b in g.get("pack", []):
            hit = bool(blocks & MEMORY_BLOCKS) if b == "memory" else b in blocks
            m["pack_hit"][1] += 1; m["pack_hit"][0] += hit
            ok[f"pack_{b}"] = hit
        lv = _level(r.get("level"))
        if "level_min" in g:
            m["level_min"][1] += 1; m["level_min"][0] += lv is not None and lv >= g["level_min"]
        if "level_max" in g:
            m["level_max"][1] += 1; m["level_max"][0] += lv is not None and lv <= g["level_max"]
        a = r.get("assessment") or {}
        for k in ("clarity", "urgency"):
            if k in g:
                m[k][1] += 1; m[k][0] += a.get(k) in g[k]
        if "image" in g:
            m["image"][1] += 1; m["image"][0] += (r.get("media") or {}).get("image") == g["image"]
        for k in spans:
            exp = g.get(k) or []
            got = _texts(r.get("observations"), k)
            a_, b_, c_ = _match(exp, got)
            spans[k][0] += a_; spans[k][1] += b_; spans[k][2] += c_
        today = r.get("owner_today") or gold.get("now")
        reads = _date_reads(r)
        for dv in g.get("date_values", []):
            ok_specs = set().union(*(_accepted(s, today) for s in (dv["value"] if isinstance(dv["value"], list)
                                                                    else [dv["value"]])))
            hit = any(v in ok_specs or any(o.startswith("*..") and ".." in v and v.endswith(o[1:]) for o in ok_specs)
                      for _, v in reads)
            if dv.get("optional") and not reads:
                continue                    # an implicit date may go unread; read, it must be right
            m["date_value"][1] += 1; m["date_value"][0] += hit
            ok[f"date_{dv['kind']}"] = hit
        per[r["case"]] = ok
    return {"fields": m, "spans": spans, "per_case": per}


def report(labels: list[str], set_name: str = "gold") -> dict:
    gold = json.loads(_gold_file(set_name).read_text())
    out = {"gold": _gold_file(set_name).name, "cases": len(gold["cases"]), "labels": {}}
    tag = "" if set_name == "gold" else f"{set_name}-"
    G = {c["id"]: c["gold"] for c in gold["cases"]}
    for label in labels:
        f = sorted(BENCH.glob(f"pfn-{tag}{label}-*.jsonl"))[-1]
        recs = [json.loads(x) for x in f.read_text().splitlines()]
        s = score(recs, gold)
        lat = {k: {"p50": _pct([r.get(k) for r in recs], .5), "p95": _pct([r.get(k) for r in recs], .95)}
               for k in ("decision_ms", "plan_ms", "total_ms", "wall_ms")}
        calls = [r["calls"]["calls"] for r in recs if r.get("calls")]
        cost = sum(r["calls"]["cost_usd"] for r in recs if r.get("calls"))
        models: dict = {}
        for r in recs:
            for k, v in (r.get("calls") or {}).get("models", {}).items():
                models[k] = models.get(k, 0) + v
        out["labels"][label] = {
            "file": f.name, "n": len(recs), "errors": sum(1 for r in recs if r.get("error")),
            "degraded": sum(r["degraded"] for r in recs), "fast_path": sum(1 for r in recs if r.get("fast_path")),
            "latency": lat, "calls_per_case": {"mean": round(statistics.mean(calls), 2) if calls else None,
                                               "max": max(calls) if calls else None},
            "cost_usd_total": round(cost, 6), "cost_usd_per_case": round(cost / max(1, len(recs)), 7),
            "models": models, "pack_tokens_p50": _pct([(r.get("pack") or {}).get("tokens") for r in recs], .5),
            "pack_tokens_p95": _pct([(r.get("pack") or {}).get("tokens") for r in recs], .95),
            "pack_tokens_p50_no_pack_expected": _pct([(r.get("pack") or {}).get("tokens") for r in recs
                                                      if not (G.get(r["case"]) or {}).get("pack")], .5),
            "block_tokens": {b: {"cases": len(v), "p50": _pct(v, .5), "sum": sum(v)} for b, v in sorted(
                _by_block(recs).items())},
            "levels": {lv: sum(1 for r in recs if r.get("level") == lv) for lv in ("L0", "L1", "L2", "L3", "L4")},
            "fields": s["fields"], "spans": s["spans"],
            "by_src": {src: score([r for r in recs if r.get("src") == src], gold)["fields"]
                       for src in ("real", "synthetic")}}
    return out


def _by_block(recs: list[dict]) -> dict:
    out: dict = {}
    for r in recs:
        for b, n in ((r.get("pack") or {}).get("block_tokens") or {}).items():
            if isinstance(n, (int, float)):
                out.setdefault(b, []).append(n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--limit", type=int)
    r.add_argument("--only")
    r.add_argument("--need", help="the gateway need to ask under (a candidate policy)")
    r.add_argument("--readings-apart", choices=["true", "false"])
    r.add_argument("--without", help="models taken out of the decision chain, comma-separated (outage drill)")
    r.add_argument("--set", default="gold", choices=["gold", "indep", "hold"])
    p = sub.add_parser("report")
    p.add_argument("--labels", required=True)
    p.add_argument("--set", default="gold", choices=["gold", "indep", "hold"])
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.label, a.limit, a.only.split(",") if a.only else None, a.need,
            None if a.readings_apart is None else a.readings_apart == "true",
            a.without.split(",") if a.without else None, a.set)
    else:
        rep = report(a.labels.split(","), a.set)
        dest = BENCH / f"pfn-report-{'' if a.set == 'gold' else a.set + '-'}{'-'.join(a.labels.split(','))}.json"
        dest.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
