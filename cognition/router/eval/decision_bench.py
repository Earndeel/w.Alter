"""Decision bench (2026-11-13): the decision model, use by use, judged against the owner's own blind answers.

Why: the decision model settles, at each use, what W.Alter does (understand each owner message, sort incoming
messages, route a request). Public leaderboards measure it in general; this bench measures it on the owner's uses.

Uses (levels) and where their questions come from — always the use's own code, never a copy:
  comprehension  walter-context preflight-questions  (the preflight of each owner message)
  triage         walter-memory decision-questions triage  (incoming messages; fictitious cases only)
  routing        serve/intent.classify_questions  (the Router's own request routing)

Cases: the instance's fictitious set (@instance/config/router/decision-bench-cases.json) and, for comprehension, a
draw of the owner's own recent messages to W.Alter (cloud-safe events of sources claude_code and dsh, never Beeper
or third parties), with their previous exchange. Cases the production rules settle without a model are left out.

Blind: every model answers every case (`run`, several samples), the answers are stored and never shown; the owner
labels the same cases on Telegram (`label`: one case per message, buttons per question, data
`wr:b:<case>:<question>:<option>`, through the door's existing `wr` callback); `report` compares afterwards.
State in @instance/state/router/decision-bench/ (cases.json, answers.jsonl, labels.json); nothing here is sent to
memory. Calls go straight to each provider (intent._decisions), with a spending cap.
"""
from __future__ import annotations

import fcntl
import json
import random
import re
import statistics
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance

MODELS = ("nace/drex-max-v1.1", "liquid/d1-ultra", "cloudflare/clef", "cloudflare/clef-flash", "baseten/mammoth-1",
          "perplexity/pplx-decider-v1.2", "typesafe/jev-1.14", "google/gemini-decision-1")
# openai/gpt-6-luna-decisions left out: OpenRouter answers 401 with the instance's key (2026-11-13)
SAMPLES = 3
CAP_USD = 3.0                       # the owner's approval of 2026-11-13 (« Oui » to a 3 € calibration budget)
OPENROUTER_CAP_USD = 1.0            # its credit was 4.1 $ that day: production keeps the rest
OWNER_DRAW = {"claude_code": 8, "dsh": 8}
SEED = 20261113
LEVEL_NAMES = {"comprehension": "Compréhension de vos messages", "triage": "Tri des messages entrants",
               "routing": "Aiguillage d'une demande (Router)"}
YES_NO = {"yes": "Oui", "no": "Non"}
LEVEL3 = {"L1": "Simple", "L2": "Exigeant", "L3": "Très exigeant"}
# What the owner answers, per use: question key → (question in plain French, option key → button text).
# Options None = the question's own criteria (thread, task: labels from their descriptions); noul = yes/no.
LABELED = {
    "comprehension": [
        ("act", "Que fait ce message ?", {"new": "Nouveau sujet", "continue": "Suite du sujet", "approve": "Accord, go",
                                         "correct": "Corrige", "inform": "Informe"}),
        ("thread", "À quel sujet appartient-il ?", None),
        ("plan", "Que doit voir l'assistant en plus du message ?", {
            "none": "Rien", "last_exchange": "Dernier échange", "thread": "Historique du sujet",
            "thread_and_memory": "Sujet + mémoire"}),
        ("model_level", "Difficulté du travail demandé ?", LEVEL3),
        ("work", "Travail à mener (pas seulement répondre) ?", YES_NO),
        ("task", "Quel type de travail ?", None)],
    "triage": [
        ("action", "Que doit faire votre assistant ?", {"ignore": "Ignorer", "remember": "Retenir",
                                                        "notify": "Me prévenir", "prepare_reply": "Préparer réponse"}),
        ("urgency", "Quand devez-vous le voir ?", {"now": "Maintenant", "today": "Aujourd'hui", "later": "Plus tard"}),
        ("needs_reply", "Quelqu'un attend votre réponse ?", YES_NO)],
    "routing": [
        ("task", "Quel type de travail ?", None),
        ("level", "Difficulté pour un modèle texte ?", LEVEL3),
        ("unrestricted", "Faut-il un modèle sans restriction ?", {"no": "Non", "yes": "Oui"})],
}
_lock = threading.Lock()


# ── files ────────────────────────────────────────────────────────────────────────────────────────────────────────
def home() -> Path:
    p = instance.state_file("decision-bench")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(name: str, default):
    p = home() / name
    return json.loads(p.read_text()) if p.is_file() else default


def _write(name: str, data) -> None:
    p = home() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(p)


def answers() -> list[dict]:
    p = home() / "answers.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []


# ── build ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _cmd(args: list[str], stdin: str | None = None) -> dict:
    r = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} {args[1]}: exit {r.returncode}")
    return json.loads(r.stdout)


def _usable(text: str) -> bool:
    t = (text or "").strip()
    return (15 <= len(t) <= 600 and not t.startswith(("<", "[", "{", "/")) and "session is being continued" not in t
            and not re.search(r"(sk|key|token|pass(word)?)[-_ :=]+[A-Za-z0-9]{12,}", t, re.I))


def draw_owner(source: str, n: int, rng: random.Random) -> list[dict]:
    """n of the owner's own recent messages to W.Alter, with the exchange before each (public CLI, cloud-safe)."""
    evs = _cmd(["walter-memory", "events", "--source", source, "--type", "message.sent", "--cloud-safe",
                "--since", "2026-10-15", "--limit", "400", "--compact", "700"])["events"]
    evs = [e for e in evs if e.get("actor") == instance.owner() and _usable(e.get("content") or "")]
    rng.shuffle(evs)
    out = []
    for e in evs:
        if len(out) >= n:
            break
        before = _cmd(["walter-memory", "events", "--source", source, "--thread", e["thread_id"], "--cloud-safe",
                       "--until", e["occurred_at"], "--order", "desc", "--limit", "4", "--compact", "500"])["events"]
        before = [b for b in before if b["event_id"] != e["event_id"]]
        answer = next((b for b in before if b["event_type"] == "message.received"), None)
        asked = next((b for b in before if b["event_type"] == "message.sent"), None)
        prev = None
        if answer:
            age = (datetime.fromisoformat(e["occurred_at"]) - datetime.fromisoformat(answer["occurred_at"])).total_seconds()
            prev = {"message": (asked or {}).get("content") or "", "answer": answer.get("content") or "",
                    "age_s": max(age, 0), "thread_id": "t_session"}
        out.append({"id": f"o{source[:2]}{len(out) + 1:02d}", "source": source, "message": e["content"],
                    "previous": prev, "candidates": [{"id": "t_session", "title": "Sujet de cette session"}] if prev else []})
    return out


def build(conn) -> dict:
    """Write cases.json: fictitious + drawn cases with the exact payload of their use, in a fixed shuffled order."""
    from walter_router.serve import intent
    if (home() / "answers.jsonl").is_file() or _read("labels.json", {}):
        raise RuntimeError("bench already run or labelled: move decision-bench/ aside before rebuilding")
    spec = json.loads(instance.config_path("decision-bench-cases.json").read_text())
    rng = random.Random(SEED)
    cases, skipped = [], 0
    comp = [dict(c, source="fictif") for c in spec["comprehension"]]
    for source, n in OWNER_DRAW.items():
        comp += draw_owner(source, n, rng)
    for c in comp:
        p = _cmd(["walter-context", "preflight-questions"], json.dumps(c))
        if p.get("fast_path"):
            skipped += 1
            continue
        cases.append({"id": c["id"], "level": "comprehension", "source": c["source"], "case": c,
                      "state": p["state"], "questions": p["questions"]})
    tq = _cmd(["walter-memory", "decision-questions", "triage"])["questions"]
    for c in spec["triage"]:
        cases.append({"id": c["id"], "level": "triage", "source": "fictif", "case": c, "state": c["state"],
                      "questions": tq})
    for c in spec["routing"]:
        state, q = intent.classify_questions(conn, c["request"])
        cases.append({"id": c["id"], "level": "routing", "source": "fictif", "case": c, "state": state, "questions": q})
    names = {r["task"]: r["label"] for r in conn.execute("select task, label from models.tasks") if r["label"]}
    for c in cases:   # short button texts for the task question, from the Router's own task names
        if "task" in c["questions"]:
            c["option_labels"] = {"task": {k: names.get(k, k) for k in c["questions"]["task"].get("criteria") or {}}}
    rng.shuffle(cases)
    _write("cases.json", {"built_at": datetime.now(timezone.utc).isoformat(), "seed": SEED, "cases": cases})
    return {"cases": len(cases), "fast_path_left_out": skipped,
            "by_level": {lv: sum(c["level"] == lv for c in cases) for lv in LEVEL_NAMES},
            "owner_messages": sum(c["source"] != "fictif" for c in cases)}


# ── run (blind: nothing printed but counts) ─────────────────────────────────────────────────────────────────────────
def _prices(conn) -> dict:
    rows = conn.execute("""select o.offer_key, min(o.price_in_1m) p from models.offers o join models.latest_snapshots s
                           using (snapshot_id) where o.interface = 'decisions' group by 1""").fetchall()
    return {r["offer_key"]: r["p"] for r in rows if r["p"] is not None}


def _call(conn, model: str, case: dict, prices: dict) -> dict:
    from walter_router.serve import intent
    t0 = time.monotonic()
    row = {"case": case["id"], "model": model, "at": datetime.now(timezone.utc).isoformat()}
    try:
        a, data, ms, _ = intent._decisions(conn, case["state"], case["questions"], 30, models=(model,))
        usage = data.get("usage") or {}
        tok = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        cost = usage.get("cost")
        if cost is None and prices.get(model) is not None:
            cost = tok * prices[model] / 1e6
        row.update(ok=True, answers=a, ms=ms, input_tokens=tok, cost_usd=cost)
    except Exception as exc:  # noqa: BLE001 — recorded, the report counts it
        row.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:200], ms=int((time.monotonic() - t0) * 1000))
    return row


def run(conn, models: tuple = MODELS, samples: int = SAMPLES, workers: int = 8) -> dict:
    cases = _read("cases.json", {}).get("cases") or []
    if not cases:
        raise RuntimeError("no cases: run `decision-bench build` first")
    done: dict = {}
    spent = {"all": 0.0, "openrouter": 0.0}
    for r in answers():
        if r.get("ok"):
            done[(r["case"], r["model"])] = done.get((r["case"], r["model"]), 0) + 1
            c = r.get("cost_usd") or 0
            spent["all"] += c
            spent["openrouter"] += c if not r["model"].startswith(("nace/", "cloudflare/")) else 0
    jobs = [(m, c) for c in cases for m in models for _ in range(max(samples - done.get((c["id"], m), 0), 0))]
    prices = _prices(conn)
    stopped = {"cap": False}
    out = home() / "answers.jsonl"

    def one(job):
        model, case = job
        with _lock:
            on_or = not model.startswith(("nace/", "cloudflare/"))
            if spent["all"] >= CAP_USD or (on_or and spent["openrouter"] >= OPENROUTER_CAP_USD):
                stopped["cap"] = True
                return None
        from walter_router.store import db
        with db.connect() as c:
            row = _call(c, model, case, prices)
        with _lock:
            cost = row.get("cost_usd") or 0
            spent["all"] += cost
            spent["openrouter"] += cost if on_or else 0
            with out.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row["ok"]

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, jobs))
    return {"calls": len(jobs), "ok": sum(r is True for r in res), "failed": sum(r is False for r in res),
            "not_run_cap": sum(r is None for r in res), "spent_usd": round(spent["all"], 4),
            "openrouter_usd": round(spent["openrouter"], 4), "cap_reached": stopped["cap"]}


# ── labelling on Telegram ───────────────────────────────────────────────────────────────────────────────────────
def _short(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _options(case: dict, key: str, given: dict | None) -> list[tuple[str, str]]:
    q = case["questions"].get(key) or {}
    if given is not None:
        return list(given.items())
    crit = q.get("criteria") or {}
    named = (case.get("option_labels") or {}).get(key)
    if named:
        return [(k, _short(named.get(k, k), 26)) for k in crit]
    if key == "thread":
        titles = {c["id"]: c.get("title") for c in case["case"].get("candidates") or []}
        return [(k, "Nouveau sujet" if k == "new" else _short(titles.get(k) or k, 30)) for k in crit]
    return [(k, _short(re.split(r"[:—(]", v)[0] if isinstance(v, str) else k, 26)) for k, v in crit.items()]


def labelled_questions(case: dict) -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [(k, text, _options(case, k, given)) for k, text, given in LABELED[case["level"]]
            if k in case["questions"]]


def context_lines(case: dict) -> list[str]:
    """What the owner sees of a case (never a model's answer)."""
    c, lines = case["case"], []
    if case["level"] == "comprehension":
        p = c.get("previous")
        if p:
            mins = round((p.get("age_s") or 0) / 60)
            lines += [f"Échange précédent (il y a {mins} min) :", f"  vous : « {_short(p.get('message'), 300)} »",
                      f"  W.Alter : « {_short(p.get('answer'), 400)} »", ""]
        cands = [x.get("title") for x in c.get("candidates") or [] if x.get("title")]
        if cands and "thread" in case["questions"]:
            lines += ["Sujets en cours : " + " · ".join(cands), ""]
        lines += [f"Nouveau message : « {_short(c['message'], 1500)} »"]
    elif case["level"] == "triage":
        s = c["state"]
        lines += [f"{s['network']} · {s['thread_kind']}" + (f" · objet : {s['subject']}" if s.get("subject") else "")
                  + (" · vous êtes mentionné" if any(v for k, v in s.items() if k.endswith("_mentioned")) else "")]
        for m in s.get("messages") or []:
            who = "vous" if m["from"] == instance.owner() else "eux"
            lines += [f"  {who} (il y a {m['minutes_ago']} min) : « {_short(m['text'], 400)} »"]
    else:
        lines += [f"Demande : « {_short(c['request'], 800)} »"]
    return lines


def case_text(case: dict, n: int, total: int) -> str:
    lines = [f"🧪 Banc décision · cas {n}/{total} · {LEVEL_NAMES[case['level']]}", ""] + context_lines(case)
    lines += [""] + [f"{i + 1}. {text}" for i, (_, text, _) in enumerate(labelled_questions(case))]
    lines += ["", "Répondez à chaque question (« ? » = je ne sais pas)."]
    return "\n".join(lines)


def buttons(case_no: int, case: dict) -> list[list[dict]]:
    rows = []
    for qi, (_, _, opts) in enumerate(labelled_questions(case)):
        btn = [{"text": f"{qi + 1} · {label}", "callback_data": f"wr:b:{case_no}:{qi}:{oi}"} for oi, (_, label) in enumerate(opts)]
        btn.append({"text": f"{qi + 1} · ?", "callback_data": f"wr:b:{case_no}:{qi}:x"})
        per = 2 if max(len(b["text"]) for b in btn) > 16 else 3
        rows += [btn[i:i + per] for i in range(0, len(btn), per)]
    rows.append([{"text": "Passer ce cas", "callback_data": f"wr:b:{case_no}:s"}])
    return rows


def next_case() -> tuple[int, dict] | None:
    cases = _read("cases.json", {}).get("cases") or []
    labels = _read("labels.json", {})
    for i, c in enumerate(cases):
        if c["id"] not in labels or not labels[c["id"]].get("_done"):
            return i, c
    return None


def send_next() -> dict:
    nxt = next_case()
    cases = _read("cases.json", {}).get("cases") or []
    if nxt is None:
        _send(f"✅ Banc décision : tous les cas sont étiquetés. Merci, {instance.owner()}. Je prépare la comparaison.",
              None)
        return {"done": True}
    i, c = nxt
    _send(case_text(c, i + 1, len(cases)), buttons(i, c))
    return {"sent": c["id"], "n": i + 1, "of": len(cases)}


def _send(text: str, rows) -> None:
    args = ["walter-telegram", "send", "--plain"] + (["--buttons", json.dumps(rows, ensure_ascii=False)] if rows else []) + ["-"]
    r = subprocess.run(args, input=text, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"walter-telegram send: exit {r.returncode}")


class RevealedError(ValueError):
    """The case's model answers were shown: the owner's answers to it are frozen."""


def reveal(case_no: int) -> dict:
    """The models' answers to one case, once the owner answered it (or skipped it); his answers freeze from then.
    Per model: per question the majority answer of its samples, how many agree, mean confidence, and whether it
    matches the owner's answer."""
    cases = _read("cases.json", {}).get("cases") or []
    case = cases[case_no]
    with (home() / ".labels.lock").open("w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        labels = _read("labels.json", {})
        lab = labels.get(case["id"]) or {}
        if not lab.get("_done"):
            raise ValueError("answer the case first")
        if not lab.get("_revealed"):
            lab["_revealed"] = datetime.now(timezone.utc).isoformat()
            labels[case["id"]] = lab
            _write("labels.json", labels)
    qs = labelled_questions(case)
    rows = [r for r in answers() if r.get("case") == case["id"]]
    out = []
    for m in dict.fromkeys(r["model"] for r in rows):
        mine = [r for r in rows if r["model"] == m]
        ok = [r for r in mine if r.get("ok")]
        per_q = []
        for key, _, opts in qs:
            names = dict(opts)
            got = [_choice(r.get("answers") or {}, key, case) for r in ok]
            votes = Counter(g for g, _ in got if g is not None)
            top, n = votes.most_common(1)[0] if votes else (None, 0)
            confs = [c for g, c in got if g == top and c is not None]
            gold = lab.get(key, "__none__")
            per_q.append({"key": key, "answer": top, "label": names.get(top, top), "agree": n, "of": len(ok),
                          "confidence": round(statistics.mean(confs), 2) if confs else None,
                          "match": None if gold in (None, "__none__") or top is None else top == gold})
        out.append({"model": m, "failures": len(mine) - len(ok),
                    "ms": sorted(r["ms"] for r in ok)[len(ok) // 2] if ok else None, "questions": per_q})
    return {"case": case["id"], "owner": {k: lab.get(k) for k, _, _ in qs}, "skipped": bool(lab.get("_skipped")),
            "models": out}


def record(case_no: int, qi: int | None, oi: int | None, skip: bool = False) -> dict:
    """One owner answer (oi None = « ? », no gold for it) or a skipped case; shared by Telegram and the web page.
    Returns {case, labels, done}. A file lock: every Telegram press is its own process."""
    cases = _read("cases.json", {}).get("cases") or []
    case = cases[case_no]
    with (home() / ".labels.lock").open("w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        labels = _read("labels.json", {})
        lab = labels.setdefault(case["id"], {})
        if lab.get("_revealed"):          # the owner saw the models' answers: his own stay as given, blind
            raise RevealedError(case["id"])
        qs = labelled_questions(case)
        if skip:
            lab.update(_done=True, _skipped=True, _at=datetime.now(timezone.utc).isoformat())
        else:
            key, _, opts = qs[qi]
            lab[key] = None if oi is None else opts[oi][0]
            lab.pop("_skipped", None)
            if all(k in lab for k, _, _ in qs):
                lab.update(_done=True, _at=datetime.now(timezone.utc).isoformat())
            else:
                lab.pop("_done", None)
        labels[case["id"]] = lab
        _write("labels.json", labels)
    return {"case": case["id"], "labels": lab, "done": bool(lab.get("_done"))}


def button(data: str) -> dict:
    """wr:b:<case_no>:<qi>:<oi|x> or wr:b:<case_no>:s → {ok, toast, drop}; the next case follows a finished one."""
    parts = data.split(":")
    cases = _read("cases.json", {}).get("cases") or []
    try:
        case_no = int(parts[2])
        cases[case_no]
    except (IndexError, ValueError):
        return {"ok": False, "toast": "Cas inconnu"}
    try:
        return _button(case_no, parts)
    except RevealedError:
        return {"ok": False, "toast": "Réponses des modèles déjà vues : la vôtre reste celle donnée avant"}


def _button(case_no: int, parts: list[str]) -> dict:
    if parts[3] == "s":
        out = record(case_no, None, None, skip=True)
        toast, drop = "Cas passé", [f"wr:b:{case_no}:"]
    else:
        qi = int(parts[3])
        out = record(case_no, qi, None if parts[4] == "x" else int(parts[4]))
        toast, drop = "Noté", [f"wr:b:{case_no}:{qi}:"]
        if out["done"]:
            drop = [f"wr:b:{case_no}:"]
    if out["done"]:
        try:
            send_next()
        except Exception:  # noqa: BLE001 — the owner can ask for the next one again
            toast += " · suite non envoyée"
    return {"ok": True, "toast": toast, "drop": drop}


def status() -> dict:
    cases = _read("cases.json", {}).get("cases") or []
    labels = _read("labels.json", {})
    rows = answers()
    return {"cases": len(cases), "labelled": sum(bool(v.get("_done")) and not v.get("_skipped") for v in labels.values()),
            "skipped": sum(bool(v.get("_skipped")) for v in labels.values()),
            "model_answers": sum(r.get("ok") for r in rows), "model_failures": sum(not r.get("ok") for r in rows),
            "spent_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4)}


# ── report (after the owner's labels) ──────────────────────────────────────────────────────────────────────────
def _choice(ans: dict, key: str, case: dict):
    a = ans.get(key) or {}
    if (case["questions"].get(key) or {}).get("type") == "noul":
        p = a.get("noul")
        return (None, None) if p is None else ("yes" if p >= 0.5 else "no", max(p, 1 - p))
    return a.get("choice"), a.get("confidence")


def report() -> dict:
    cases = {c["id"]: c for c in _read("cases.json", {}).get("cases") or []}
    labels = _read("labels.json", {})
    rows = [r for r in answers() if r.get("case") in cases]
    models = sorted({r["model"] for r in rows})
    out: dict = {"labelled_cases": 0, "levels": {}, "models": {}}
    for m in models:
        mine = [r for r in rows if r["model"] == m]
        ok = [r for r in mine if r.get("ok")]
        ms = sorted(r["ms"] for r in ok)
        out["models"][m] = {"calls": len(mine), "failures": len(mine) - len(ok),
                            "p50_ms": ms[len(ms) // 2] if ms else None, "p95_ms": ms[int(len(ms) * .95)] if ms else None,
                            "usd_per_1000": round(1000 * statistics.mean(r.get("cost_usd") or 0 for r in ok), 4) if ok else None}
    for lv in LEVEL_NAMES:
        per_q: dict = {}
        for cid, lab in labels.items():
            c = cases.get(cid)
            if not c or c["level"] != lv or lab.get("_skipped") or not lab.get("_done"):
                continue
            for key, _, _ in labelled_questions(c):
                gold = lab.get(key)
                if gold is None:
                    continue
                for m in models:
                    for r in (r for r in rows if r["case"] == cid and r["model"] == m and r.get("ok")):
                        got, conf = _choice(r["answers"], key, c)
                        s = per_q.setdefault(key, {}).setdefault(m, {"n": 0, "right": 0, "conf_right": [], "conf_wrong": []})
                        s["n"] += 1
                        s["right"] += got == gold
                        (s["conf_right"] if got == gold else s["conf_wrong"]).append(conf or 0)
        out["levels"][lv] = {
            k: {m: {"accuracy": round(s["right"] / s["n"], 3) if s["n"] else None, "answers": s["n"],
                    "confidence_when_right": round(statistics.mean(s["conf_right"]), 3) if s["conf_right"] else None,
                    "confidence_when_wrong": round(statistics.mean(s["conf_wrong"]), 3) if s["conf_wrong"] else None}
                for m, s in v.items()} for k, v in per_q.items()}
    out["labelled_cases"] = sum(bool(v.get("_done")) and not v.get("_skipped") for v in labels.values())
    _write("report.json", out)
    return out
