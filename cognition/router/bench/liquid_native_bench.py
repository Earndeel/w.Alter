"""Liquid native vs OpenRouter, same data, interleaved in time (17/11/2026). Synthetic French owner messages with
known truths. Phases: A quality/latency/cost (judgements, one-call-all vs split), B stability (3 repeats), C concurrency
8/16, D question count 1/6/12, E idle-gap (cold start).  No key, no personal data in the output.
Run:   walter-python bench/liquid_native_bench.py run  reports/liquid-native-2026-11-17-runN.jsonl
       walter-python bench/liquid_native_bench.py summary reports/liquid-native-2026-11-17-run*.jsonl > OUT.md"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

import liquid_common as lc

sys.path.insert(0, "/walter/cognition/router/llm")
import decision as wd  # noqa: E402

MODELS = ("d1.2", "d1.2-ultra")
TARGETS = [("liquid", m) for m in MODELS] + [("openrouter", m) for m in MODELS]

# ── corpus: 30 synthetic messages with truths ────────────────────────────────────────────────────────────────
PEOPLE = ["Paul Martin", "Sophie Leroy", "Karim Benali", "Chloé Durand", "Hugo Petit", "Inès Moreau"]
CASES = []


def add(text, mail, intent, urgent, person=None, amount=None, due=None):
    CASES.append(dict(id=len(CASES), text=text, mail=mail, intent=intent, urgent=urgent, person=person, amount=amount, due=due))


for i, p in enumerate(PEOPLE):
    first = p.split()[0]
    add(f"Rappelle-moi d'appeler {p} demain avant 18h pour le devis de {1200 + 150 * i} euros, mais ne lui envoie rien par mail.",
        False, "rappel", False, p, 1200 + 150 * i)
    add(f"Envoie un mail à {p} pour confirmer la facture de {89 + 10 * i},90 € avant le {10 + i}/12/2026.",
        True, "instruction", False, p, 89.9 + 10 * i, f"2026-12-{10 + i:02d}")
    add(f"{first} m'a demandé si le paiement de {300 + 50 * i} euros était bien passé, tu peux vérifier ?",
        False, "question", False, first, 300 + 50 * i)
    add(f"URGENT, appelle {p} tout de suite, le serveur est tombé !", False, "instruction", True, p)
    add(f"Merci pour la réunion d'hier, {first}, c'était très utile.", False, "info", False, first)

# 30 messages exactly
CASES = CASES[:30]
JUDGE = {
    "mail": {"type": "noul", "instructions": "Le propriétaire demande-t-il d'envoyer un e-mail ? (Une phrase négative comme « ne lui envoie rien » vaut non.)"},
    "intent": {"type": "choice", "instructions": "Quelle est la nature du message ?", "criteria": {
        "rappel": "demande de rappel ou de tâche à faire plus tard", "instruction": "ordre à exécuter maintenant",
        "question": "question posée au propriétaire ou à l'assistant", "info": "simple information ou remerciement"}},
    "urgent": {"type": "noul", "instructions": "Le message est-il urgent ?"},
}
TYPED = {
    "person": {"type": "text", "instructions": "Quelle personne est citée ?"},
    "amount": {"type": "number", "instructions": "Quel montant en euros ?", "unit": "EUR"},
    "due": {"type": "date", "instructions": "Quelle date précise (jour/mois/année) est écrite ?", "order": "dmy"},
}
ALL = {**JUDGE, **TYPED}


def score(case, ans: dict) -> dict:
    """Per-field correctness against the truth (None = not applicable)."""
    out = {}
    g = lambda k: ans.get(k) or {}
    if "mail" in ans:
        out["mail"] = (g("mail").get("noul", 0.5) >= 0.5) == case["mail"]
        out["urgent"] = (g("urgent").get("noul", 0.5) >= 0.5) == case["urgent"]
        out["intent"] = g("intent").get("choice") == case["intent"]
    if "person" in ans:
        out["person"] = (case["person"] in (g("person").get("text") or "")) if case["person"] else (g("person").get("text") is None or (g("person").get("found") or 0) < 0.5)
        a = g("amount")
        n = a.get("number")
        if n is None and (a.get("found") or 0) >= 0.5:
            n = wd.parse_number(a.get("text"))
        out["amount"] = (n is not None and abs(n - case["amount"]) < 0.01) if case["amount"] is not None else (n is None)
        d = wd.finish({"due": TYPED["due"]}, {"due": g("due")}).get("due", {})
        out["due"] = (d.get("date") == case["due"]) if case["due"] else (d.get("date") is None)
    return out


# ── routes ───────────────────────────────────────────────────────────────────────────────────────────────────
class Runner:
    def __init__(self):
        self.client = {p: httpx.Client(http2=False, timeout=60, limits=httpx.Limits(max_connections=64)) for p in ("liquid", "openrouter")}

    def liquid(self, model, state, questions, **extra):
        return lc.liquid(model, {"state": state, "questions": questions, **extra}, client=self.client["liquid"])

    def or_decide(self, model, state, questions):
        return lc.or_decide(model, {"state": state, "questions": questions}, client=self.client["openrouter"])

    def or_extract(self, model, text, questions):
        return lc.or_extract(model, {"state": text, "fields": wd.extraction_fields(questions)}, client=self.client["openrouter"])


def cost_of(res):
    u = (res["data"] or {}).get("usage") or {}
    return u.get("cost"), u.get("input_tokens") or u.get("prompt_tokens")


def row(f, phase, prov, model, mode, res, **kw):
    c, t = cost_of(res)
    r = dict(phase=phase, provider=prov, model=model, mode=mode, status=res["status"], ms=res["ms"], cost=c, tokens=t,
             at=time.strftime("%H:%M:%S"), rl=res.get("rl") or None, **kw)
    if res["status"] != 200:
        r["error"] = (json.dumps(res["data"])[:160] if res["data"] else res.get("error"))
    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    f.flush()
    return r


def answers(res):
    return (res["data"] or {}).get("answers") or {}


def phase_a(f, R: Runner):
    """Each message to each target, targets rotated per message (interleaved), judgement-only and all-in-one/split."""
    ex = ThreadPoolExecutor(4)
    for i, case in enumerate(CASES):
        order = TARGETS[i % 4:] + TARGETS[:i % 4]
        for prov, model in order:
            if prov == "liquid":
                r1 = R.liquid(model, case["text"], JUDGE)
                row(f, "A", prov, model, "judge3", r1, msg=case["id"], ok=score(case, answers(r1)))
                r6 = R.liquid(model, case["text"], ALL)
                a6 = answers(r6)
                # typed values the same way the Router reads them (number text fallback, date order)
                row(f, "A", prov, model, "all6_one_call", r6, msg=case["id"], ok=score(case, a6))
            else:
                t0 = time.perf_counter()
                fj = ex.submit(R.or_decide, model, case["text"], JUDGE)
                fe = ex.submit(R.or_extract, model, case["text"], TYPED)
                rj, re_ = fj.result(), fe.result()
                wall = round((time.perf_counter() - t0) * 1000, 1)
                row(f, "A", prov, model, "judge3", rj, msg=case["id"], ok=score(case, answers(rj)))
                ext = {k: wd.from_extraction(TYPED[k], (answers(re_) or {}).get(k), case["text"]) or {} for k in TYPED}
                row(f, "A", prov, model, "extract3", re_, msg=case["id"], ok=score(case, ext))
                both = {"status": 200 if rj["status"] == 200 and re_["status"] == 200 else max(rj["status"], re_["status"]), "ms": wall,
                        "data": {"usage": {"cost": (cost_of(rj)[0] or 0) + (cost_of(re_)[0] or 0),
                                           "input_tokens": (cost_of(rj)[1] or 0) + (cost_of(re_)[1] or 0)}}, "rl": None}
                row(f, "A", prov, model, "all6_two_routes_parallel", both, msg=case["id"])
        print(f"A {i + 1}/{len(CASES)}", flush=True)


def phase_b(f, R: Runner):
    """Stability: 3 identical judgement calls on 8 messages, per target (interleaved)."""
    for case in CASES[::4][:8]:
        for rep in range(3):
            for prov, model in TARGETS:
                res = R.liquid(model, case["text"], JUDGE) if prov == "liquid" else R.or_decide(model, case["text"], JUDGE)
                a = answers(res)
                row(f, "B", prov, model, "judge3", res, msg=case["id"], rep=rep,
                    p={"mail": (a.get("mail") or {}).get("noul"), "urgent": (a.get("urgent") or {}).get("noul"),
                       "intent": (a.get("intent") or {}).get("probabilities")})


def phase_c(f, R: Runner):
    """Concurrency 8 and 16: bursts of N parallel judgement calls, 2 bursts each, per target."""
    for n in (8, 16):
        for burst in range(2):
            for prov, model in TARGETS:
                def one(i, prov=prov, model=model):
                    c = CASES[i % len(CASES)]
                    return R.liquid(model, c["text"], JUDGE) if prov == "liquid" else R.or_decide(model, c["text"], JUDGE)
                t0 = time.perf_counter()
                with ThreadPoolExecutor(n) as ex:
                    res = list(ex.map(one, range(n)))
                wall = round((time.perf_counter() - t0) * 1000, 1)
                for r in res:
                    row(f, "C", prov, model, f"conc{n}", r, burst=burst, wall_ms=wall)
                time.sleep(1.0)


def phase_d(f, R: Runner):
    """Cost and latency with 1 / 6 / 12 questions on the same state (5 repeats), plus extraction counts."""
    state = CASES[1]["text"]
    pool = []
    for k in range(12):
        pool.append((f"n{k}", {"type": "noul", "instructions": f"Question {k + 1} : le message parle-t-il {['de mail', 'de facture', 'de date', 'de montant', 'de personne', 'de rappel', 'de réunion', 'de serveur', 'de paiement', 'de devis', 'de téléphone', 'de remerciement'][k]} ?"}))
    for rep in range(5):
        for n in (1, 6, 12):
            qs = dict(pool[:n])
            for prov, model in TARGETS:
                res = R.liquid(model, state, qs) if prov == "liquid" else R.or_decide(model, state, qs)
                row(f, "D", prov, model, f"q{n}", res, rep=rep)
        for n in (1, 3, 6):
            ef = {"person": TYPED["person"], "amount": TYPED["amount"], "due": TYPED["due"], "p2": TYPED["person"], "a2": TYPED["amount"], "d2": TYPED["due"]}
            qs = dict(list(ef.items())[:n])
            for prov, model in TARGETS:
                res = R.liquid(model, state, qs) if prov == "liquid" else R.or_extract(model, state, qs)
                row(f, "D", prov, model, f"extract{n}", res, rep=rep)


def phase_e(f, R: Runner):
    """Idle gaps: one call after 20 s and 90 s of silence per provider (cold start)."""
    for gap in (20, 90):
        time.sleep(gap)
        for prov, model in (("liquid", "d1.2"), ("liquid", "d1.2-ultra"), ("openrouter", "d1.2"), ("openrouter", "d1.2-ultra")):
            res = R.liquid(model, CASES[0]["text"], JUDGE) if prov == "liquid" else R.or_decide(model, CASES[0]["text"], JUDGE)
            row(f, "E", prov, model, f"idle{gap}s", res)


def run(out):
    R = Runner()
    with open(out, "w") as f:
        # warm-up per target (recorded as phase W: the cold first call)
        for prov, model in TARGETS:
            res = R.liquid(model, "bonjour", {"q": {"type": "noul", "instructions": "salutation ?"}}) if prov == "liquid" \
                else R.or_decide(model, "bonjour", {"q": {"type": "noul", "instructions": "salutation ?"}})
            row(f, "W", prov, model, "first_call", res)
        phase_a(f, R)
        phase_b(f, R)
        phase_c(f, R)
        phase_d(f, R)
        phase_e(f, R)


# ── summary ──────────────────────────────────────────────────────────────────────────────────────────────────
def summary(paths):
    rows = [json.loads(l) for p in paths for l in open(p)]
    runs = {p: [json.loads(l) for l in open(p)] for p in paths}
    out = ["# Liquid native vs OpenRouter — bench 2026-11-17", "",
           "Synthetic French corpus (30 messages), same data, targets interleaved per message. No key, no personal data.", ""]
    for p, rs in runs.items():
        ts = [r["at"] for r in rs if "at" in r]
        out.append(f"- `{p.split('/')[-1]}`: {ts[0]} → {ts[-1]} (VM clock, UTC), {len(rs)} calls")
    out.append("")

    def sel(**kw):
        return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]

    def lat(rs):
        ok = [r["ms"] for r in rs if r["status"] == 200]
        if not ok:
            return "-"
        return f"{lc.pct(ok, .5):.0f} / {lc.pct(ok, .95):.0f} / {lc.pct(ok, .99):.0f}  (min {min(ok):.0f}, max {max(ok):.0f}, sd {st.pstdev(ok):.0f}, n={len(ok)})"

    def errs(rs):
        e = [r for r in rs if r["status"] != 200]
        return f"{len(e)}/{len(rs)}" + (f" ({', '.join(sorted({str(r['status']) for r in e}))})" if e else "")

    def cost(rs):
        c = [r["cost"] for r in rs if r.get("cost") is not None and r["status"] == 200]
        return f"{sum(c) / len(c) * 1e6:.1f}" if c else "-"

    def tok(rs):
        c = [r["tokens"] for r in rs if r.get("tokens") and r["status"] == 200]
        return f"{st.mean(c):.0f}" if c else "-"

    out += ["## A. Latency ms p50 / p95 / p99 (warm, sequential), errors, cost per call (µUSD), input tokens", "",
            "| target | mode | latency | errors | µUSD/call | tokens |", "|---|---|---|---|---|---|"]
    for prov, model in TARGETS:
        for mode in ("judge3", "extract3", "all6_one_call", "all6_two_routes_parallel"):
            rs = sel(phase="A", provider=prov, model=model, mode=mode)
            if rs:
                out.append(f"| {prov} {model} | {mode} | {lat(rs)} | {errs(rs)} | {cost(rs)} | {tok(rs)} |")
    out += ["", "## A. Quality vs truth (fraction correct, 30 messages x runs)", "",
            "| target | mode | " + " | ".join(["mail(neg)", "urgent", "intent", "person", "amount", "due"]) + " |", "|---|---|---|---|---|---|---|---|"]
    for prov, model in TARGETS:
        for mode in ("judge3", "extract3", "all6_one_call"):
            rs = [r for r in sel(phase="A", provider=prov, model=model, mode=mode) if r["status"] == 200]
            if not rs:
                continue
            cells = []
            for k in ("mail", "urgent", "intent", "person", "amount", "due"):
                v = [r["ok"][k] for r in rs if k in (r.get("ok") or {})]
                cells.append(f"{sum(v) / len(v):.2f} ({len(v)})" if v else "-")
            out.append(f"| {prov} {model} | {mode} | " + " | ".join(cells) + " |")
    out += ["", "## B. Stability (same input x3): max spread of each probability across repeats (mean over messages)", "",
            "| target | mail | urgent | top intent |", "|---|---|---|---|"]
    for prov, model in TARGETS:
        rs = [r for r in sel(phase="B", provider=prov, model=model) if r["status"] == 200]
        by = {}
        for r in rs:
            by.setdefault((r["msg"], r["rep"] // 100), []).append(r)
        spreads = {"mail": [], "urgent": [], "intent": []}
        for msg in {r["msg"] for r in rs}:
            g = [r["p"] for r in rs if r["msg"] == msg]
            for k in ("mail", "urgent"):
                v = [x[k] for x in g if x.get(k) is not None]
                if len(v) > 1:
                    spreads[k].append(max(v) - min(v))
            tops = [x["intent"] for x in g if x.get("intent")]
            if len(tops) > 1:
                top = max(tops[0], key=tops[0].get)
                v = [t[top] for t in tops]
                spreads["intent"].append(max(v) - min(v))
        m = lambda k: f"{st.mean(spreads[k]):.4f} (max {max(spreads[k]):.4f})" if spreads[k] else "-"
        out.append(f"| {prov} {model} | {m('mail')} | {m('urgent')} | {m('intent')} |")
    out += ["", "## C. Concurrency (per-call latency in bursts; wall = time of the whole burst)", "",
            "| target | burst | latency p50/p95/p99 | errors | mean burst wall ms |", "|---|---|---|---|---|"]
    for prov, model in TARGETS:
        for n in (8, 16):
            rs = sel(phase="C", provider=prov, model=model, mode=f"conc{n}")
            if rs:
                walls = sorted({(r["burst"], r["wall_ms"]) for r in rs})
                out.append(f"| {prov} {model} | {n} | {lat(rs)} | {errs(rs)} | {st.mean(w for _, w in walls):.0f} |")
    out += ["", "## D. Question count (same state)", "", "| target | mode | latency | µUSD/call | tokens |", "|---|---|---|---|---|"]
    for prov, model in TARGETS:
        for mode in ("q1", "q6", "q12", "extract1", "extract3", "extract6"):
            rs = sel(phase="D", provider=prov, model=model, mode=mode)
            if rs:
                out.append(f"| {prov} {model} | {mode} | {lat(rs)} | {cost(rs)} | {tok(rs)} |")
    out += ["", "## E. Cold start (first call of a run and after idle gaps), ms", "", "| target | first call (per run) | after 20 s idle | after 90 s idle |", "|---|---|---|---|"]
    for prov, model in TARGETS:
        f1 = [r["ms"] for r in sel(phase="W", provider=prov, model=model)]
        i20 = [r["ms"] for r in sel(phase="E", provider=prov, model=model, mode="idle20s")]
        i90 = [r["ms"] for r in sel(phase="E", provider=prov, model=model, mode="idle90s")]
        out.append(f"| {prov} {model} | {', '.join(f'{x:.0f}' for x in f1)} | {', '.join(f'{x:.0f}' for x in i20)} | {', '.join(f'{x:.0f}' for x in i90)} |")
    tot = sum(r["cost"] for r in rows if r.get("cost"))
    out += ["", f"Total reported cost of the bench runs: ${tot:.4f}", ""]
    return "\n".join(out)


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        print(summary(sys.argv[2:]))
