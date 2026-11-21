"""Memory V1 bench (P1.1 follow-up + P1.2), THROWAWAY test database only.

Per real thread (read-only from production), replayed turn by turn under two policies (systematic, adaptive):
  P1.1  after each turn, for every reference item: present in memory (its canonical event: always), present in the
        working state (interpreted, or its owner message kept verbatim), SELECTED in the budgeted state Context would
        inject, interpreted.
  P1.2  (adaptive replay) the thread becomes a subject; its g1 view is built from current knowledge: reference coverage of
        the overview (budgeted) and of details, tokens per depth; then reconsolidation is applied (Router) and the view
        rebuilt: active items before/after, coverage kept.
  Validation  two judges from different model families (Router `general` vs Claude Sonnet 5.5, subscription) match
        references to extracted items: agreement and kappa; a second annotator (Gemini 3.8 Flash, subscription) annotates
        every thread blind: agreement with the reference annotations, disagreements listed for the owner's arbitration.

  WALTER_MEMORY_DATABASE_URL=<test dsn> walter-python bench/memory_v1.py REFERENCE.jsonl OUT_DIR
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

assert "5433" not in os.environ.get("WALTER_MEMORY_DATABASE_URL", "5433"), "bench writes only to the test database"
from walter_memory import consolidate, events, extract2, llm, working  # noqa: E402
from walter_memory.db import connection  # noqa: E402

_spec = importlib.util.spec_from_file_location("wm", Path(__file__).with_name("working_memory.py"))
wm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(wm)
POLICIES = ("systematic", "adaptive")


def exact(provider: str, model: str, prompt: str, timeout: int = 600) -> str:
    spec = {"route": {"provider": provider, "model": model}, "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout}
    r = subprocess.run(["walter-llm", "call"], input=json.dumps(spec), capture_output=True, text=True, timeout=timeout + 60)
    d = json.loads(r.stdout or "{}")
    if not d.get("ok"):
        raise RuntimeError(f"{provider}/{model}: {d.get('error')}")
    c = d["message"]["content"]
    return c if isinstance(c, str) else "".join(x.get("text", "") for x in c if isinstance(x, dict))


def jparse(c: str) -> dict:
    return json.loads(c[c.find("{"):c.rfind("}") + 1])


def replay(thread_id: str, pol: str) -> dict:
    source, rows = wm.load_thread(thread_id)
    turns = wm.turns_of(rows)
    tid = f"{thread_id}#{pol}"
    owner_ids, timeline = [], []
    for k, turn in enumerate(turns):
        ids = events.record_events([{"event_type": r["event_type"], "source": source, "source_account": "bench",
                                     "source_id": f"{r['source_id']}#{pol}", "thread_id": tid,
                                     "occurred_at": r["occurred_at"], "content": r["content"],
                                     "privacy_class": "cloud_allowed", "payload": r["payload"] or {}} for r in turn])
        if turn[0]["event_type"] == "message.sent":
            owner_ids.append(ids["event_ids"][0])
        nxt = turns[k + 1][0]["occurred_at"] - timedelta(seconds=1) if k + 1 < len(turns) \
            else turn[-1]["occurred_at"] + timedelta(minutes=30)
        if pol == "systematic":
            extract2.process_thread(source, tid, force=True)
        else:
            extract2.process_thread(source, tid, mode="adaptive", now=nxt)
        st = working.state(source, tid, subject=False, at=None)
        shown: list = []
        text = working.render(st, None, shown)
        timeline.append({"turn": len(owner_ids), "pending": [p["event_id"] for p in st["pending"]],
                         "state": [i["id"] for v in st["interpreted"].values() for i in v], "shown": shown,
                         "tokens": len(text) // 4, "tokens_unbudgeted": len(working.render(st, {})) // 4})
    if pol == "adaptive":
        extract2.process_thread(source, tid, mode="adaptive", now=turns[-1][-1]["occurred_at"] + timedelta(minutes=30))
    with connection() as conn:
        items = conn.execute("""select item_id::text id, kind, content, stage, created_at, status from core.derived_items
                                where derived_by = 'l3.extract' and source_refs->>'thread' = %s and kind <> 'summary'""",
                             (tid,)).fetchall()
        segs = conn.execute("""select status, usage, latency_ms from extraction.segments where thread_id = %s""", (tid,)).fetchall()
    return {"thread": thread_id, "policy": pol, "source": source, "tid": tid, "owner_ids": owner_ids,
            "timeline": timeline, "items": items, "segments": segs}


JUDGE = wm.JUDGE


def judge_with(fn, refs: list[dict], items: list[dict]) -> dict[int, list[str]]:
    if not items:
        return {i: [] for i in range(len(refs))}
    prompt = JUDGE.format(refs="\n".join(f"R{i + 1}. [{r['kind']}] {r['text']}" for i, r in enumerate(refs)),
                          items="\n".join(f"{j + 1}. [{it['kind']}] {it['content']}" for j, it in enumerate(items)))
    data = jparse(fn(prompt)).get("matches", {})
    return {i: [items[n - 1]["id"] for n in (data.get(f"R{i + 1}") or []) if isinstance(n, int) and 1 <= n <= len(items)]
            for i in range(len(refs))}


def judge1(prompt: str) -> str:
    return llm.chat([{"role": "user", "content": prompt}], poste="general", processor="bench.v1.judge1",
                    privacy_class="cloud_allowed", budget="recurring", response_format={"type": "json_object"},
                    max_tokens=3000, timeout=300)["content"]


def judge2(prompt: str) -> str:
    return exact("claude-pro", "claude-sonnet-5-5", prompt + "\nRéponds uniquement par le JSON.")


ANNOTATE = """Tu annotes une conversation entre Monsieur (le propriétaire) et son assistant W.Alter, pour un banc de mémoire.
Messages de Monsieur numérotés [Mk] ; réponses de W.Alter résumées (W).
{dump}

Liste ce que Monsieur a établi et qu'un assistant devrait retenir pour la suite : décisions (y compris une approbation courte
d'une proposition, « oui », « envoi », « vas-y »), contraintes et règles (y compris une attente exprimée sous forme de question),
objectifs (ce qu'il demande d'accomplir), corrections, préférences. Pas les faits ni ce que W.Alter a fait de lui-même.
JSON : {{"items": [{{"m": numéro du message de Monsieur, "kind": "decision|constraint|goal|correction|preference",
"implicit": true si ce n'est pas dit explicitement, "text": "formulation autonome"}}]}}"""


def dump_thread(thread_id: str) -> str:
    _, rows = wm.load_thread(thread_id)
    out, k = [], 0
    for r in rows:
        t = re.sub(r"\s+", " ", r["content"] or "")
        if r["event_type"] == "message.sent":
            k += 1
            out.append(f"[M{k}] {t[:1600]}")
        else:
            out.append(f"   (W) {t[:160]} … {t[-220:] if len(t) > 380 else ''}")
    return "\n".join(out)


def kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def subject_view(run: dict, refs: list[dict], matches: dict[int, list[str]]) -> dict:
    key = f"bench-{run['tid']}"
    with connection() as conn:
        conn.execute("""insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', %s, now())
                        on conflict do nothing""", (key, f"Fil {run['thread'][:8]}"))
        conn.execute("""insert into views.member (session_id, seq, view_key, occurred_at, runtime, attached_by)
                        values (%s, 1, %s, now(), %s, 'bench') on conflict do nothing""",
                     (f"{run['source']}/bench/{run['tid']}", key, run["source"]))

    def coverage():
        built = consolidate.build_subject(key, force=True)["cloud"]
        with connection() as conn:
            cur = consolidate.current(consolidate.items_of(conn, consolidate.threads_of(conn, key), ["cloud_allowed"]),
                                      datetime.now(timezone.utc))
        shown: list = []
        working.render({"interpreted": consolidate._as_state(cur), "pending": [], "plan": None, "question": None}, None, shown)
        cur_ids = {i["id"] for i in cur}
        # an item superseded by a merge still covers its reference through the item that replaced it
        with connection() as conn:
            repl = {r["item_id"]: r["by"] for r in conn.execute("""select item_id::text, attributes->>'superseded_by' as by
                    from core.derived_items where source_refs->>'thread' = %s and status = 'superseded'""", (run["tid"],))}

        def resolve(i):
            seen = set()
            while i in repl and i not in seen:
                seen.add(i); i = repl[i]
            return i
        ov = sum(1 for i in matches if {resolve(x) for x in matches[i]} & set(shown))
        de = sum(1 for i in matches if {resolve(x) for x in matches[i]} & cur_ids)
        return {"current_items": len(cur), "overview_refs": ov, "details_refs": de, "tokens": built.get("tokens")}
    before = coverage()
    try:
        rec = consolidate.reconsolidate(key, apply=True)
    except Exception as e:
        rec = {"error": str(e)}
    after = coverage()
    return {"before": before, "after": after, "reconsolidation": rec.get("proposals"), "refs": len(refs)}


def main():
    ref_path, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = defaultdict(list)
    for line in open(ref_path):
        if line.strip():
            r = json.loads(line); refs[r["thread"]].append(r)
    threads = list(refs)
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=1))
    with connection() as conn:
        for t in threads:
            for r in wm.load_thread(t)[1]:
                conn.execute("select core.ensure_event_partition(%s)", (r["occurred_at"],))
    runs = {}
    t0 = time.time()
    with cf.ThreadPoolExecutor(6) as ex:
        for run in ex.map(lambda tp: replay(*tp), [(t, p) for t in threads for p in POLICIES]):
            runs[(run["thread"], run["policy"])] = run
            print(f"replayed {run['thread'][:12]} {run['policy']} ({round(time.time() - t0)} s)", flush=True)
    res = {"threads": len(threads), "references": sum(len(v) for v in refs.values()), "policies": {}, "views": {},
           "judges": {}, "annotator2": {}}
    m1, m2 = {}, {}
    for (t, pol), run in runs.items():
        m1[(t, pol)] = judge_with(judge1, refs[t], run["items"])
        try:
            m2[(t, pol)] = judge_with(judge2, refs[t], run["items"])
        except Exception as e:
            print("judge2 failed", t, pol, e, flush=True)
    for pol in POLICIES:
        rows, calls, ptok, ctok, lat = [], 0, 0, 0, []
        for t in threads:
            run, m = runs[(t, pol)], m1[(t, pol)]
            for i, r in enumerate(refs[t]):
                if r["m"] > len(run["owner_ids"]):
                    continue
                src = run["owner_ids"][r["m"] - 1]
                snap = next((s for s in run["timeline"] if s["turn"] == r["m"]), None)
                if not snap:
                    continue
                ids = set(m[i])
                rows.append({"thread": t, "m": r["m"], "kind": r["kind"], "implicit": r["implicit"], "ref": r["text"],
                             "in_memory": True,
                             "in_state": bool(ids & set(snap["state"])) or src in snap["pending"],
                             "selected": bool(ids & set(snap["shown"])) or src in snap["shown"],
                             "pending_verbatim": src in snap["pending"],
                             "interpreted_next": bool(ids & set(snap["state"])),
                             "interpreted_final": bool(ids)})
            for s in run["segments"]:
                if s["status"] in ("extracted", "empty"):
                    calls += 1
                    u = s["usage"] or {}
                    ptok += int(u.get("prompt_tokens") or 0); ctok += int(u.get("completion_tokens") or 0)
                    lat.append(s["latency_ms"] or 0)

        def pct(key, sub=None):
            rr = [x for x in rows if sub is None or x["implicit"] == sub]
            return round(100 * sum(x[key] for x in rr) / max(1, len(rr)), 1)
        lat.sort()
        toks = sorted(s["tokens"] for t in threads for s in runs[(t, pol)]["timeline"])
        toks_u = sorted(s["tokens_unbudgeted"] for t in threads for s in runs[(t, pol)]["timeline"])
        res["policies"][pol] = {
            "model_calls": calls, "tokens": ptok + ctok, "latency_ms_p50": lat[len(lat) // 2] if lat else None,
            "in_memory_pct": 100.0, "in_state_pct": pct("in_state"), "selected_pct": pct("selected"),
            "selected_implicit_pct": pct("selected", True), "interpreted_next_pct": pct("interpreted_next"),
            "interpreted_final_pct": pct("interpreted_final"), "interpreted_final_implicit_pct": pct("interpreted_final", True),
            "state_tokens_p50": toks[len(toks) // 2], "state_tokens_p95": toks[int(len(toks) * .95)],
            "state_tokens_unbudgeted_p95": toks_u[int(len(toks_u) * .95)],
            "not_in_state": [x for x in rows if not x["in_state"]],
            "in_state_not_selected": [x for x in rows if x["in_state"] and not x["selected"]]}
    # judges agreement (per reference, matched or not), both policies
    a, b = [], []
    for k in m1:
        if k in m2:
            for i in m1[k]:
                a.append(bool(m1[k][i])); b.append(bool(m2[k][i]))
    res["judges"] = {"pairs": len(a), "agreement_pct": round(100 * sum(x == y for x, y in zip(a, b)) / max(1, len(a)), 1),
                     "kappa": kappa(a, b), "judge1_matched_pct": round(100 * sum(a) / max(1, len(a)), 1),
                     "judge2_matched_pct": round(100 * sum(b) / max(1, len(b)), 1)}
    # P1.2 views on the adaptive replays
    for t in threads:
        res["views"][t] = subject_view(runs[(t, "adaptive")], refs[t], m1[(t, "adaptive")])
    v = res["views"].values()
    res["views_summary"] = {k: sum(x[s][f] for x in v) for s in ("before", "after")
                            for f, k in [("current_items", f"{s}_current_items"), ("overview_refs", f"{s}_overview_refs"),
                                         ("details_refs", f"{s}_details_refs")]}
    # second annotator (blind) vs reference annotations
    agree_ref, agree_ann, disagreements = 0, 0, []
    for t in threads:
        try:
            ann = jparse(exact("antigravity", "gemini-3.8-flash-high", ANNOTATE.format(dump=dump_thread(t))))["items"]
        except Exception as e:
            print("annotator2 failed", t, e, flush=True); continue
        ann_items = [{"id": f"A{k}", "kind": x.get("kind", "?"), "content": x.get("text", "")} for k, x in enumerate(ann)]
        found = judge_with(judge2, refs[t], ann_items)        # which of my references the second annotator also has
        hit = {i for i, v in found.items() if v}
        agree_ref += len(hit)
        used = {x for v in found.values() for x in v}
        agree_ann += len(used)
        disagreements += [{"thread": t, "who": "reference only", "implicit": refs[t][i]["implicit"], "m": refs[t][i]["m"],
                           "text": refs[t][i]["text"]} for i in range(len(refs[t])) if i not in hit]
        disagreements += [{"thread": t, "who": "annotator2 only", "implicit": ann[k].get("implicit"), "m": ann[k].get("m"),
                           "text": ann[k].get("text")} for k in range(len(ann)) if f"A{k}" not in used]
        res["annotator2"][t] = {"items": len(ann)}
    n_ann = sum(x["items"] for x in res["annotator2"].values())
    res["annotator2_summary"] = {"reference_items_also_found_pct": round(100 * agree_ref / max(1, res["references"]), 1),
                                 "annotator2_items": n_ann,
                                 "annotator2_items_in_reference_pct": round(100 * agree_ann / max(1, n_ann), 1)}
    (out_dir / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    (out_dir / "disagreements.json").write_text(json.dumps(disagreements, ensure_ascii=False, indent=1))
    for f in out_dir.iterdir():
        os.chmod(f, 0o600)
    print(json.dumps({k: v for k, v in res.items() if k in ("judges", "views_summary", "annotator2_summary")}, indent=1))
    for pol, d in res["policies"].items():
        print(pol, {k: v for k, v in d.items() if not isinstance(v, list)})


if __name__ == "__main__":
    main()
