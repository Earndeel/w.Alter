"""P1.1 bench: adaptive working memory vs systematic per-turn extraction, against reference annotations.

Real threads (read-only from production) are replayed turn by turn into the THROWAWAY test database, once per policy:
  systematic  one extraction call after every turn (option A)
  adaptive    the adaptive trigger (extract2.adaptive_due) evaluated just before the next owner turn starts
After each turn the working state is built (working.state) and compared with the reference items already stated:
  available   the item is interpreted (a matching current item exists) OR its owner message is still pending verbatim
  interpreted the item is interpreted
Matching extracted items to reference items: one judge call per thread and policy (Router poste `general`, L2).
Tokens and latency come from extraction.segments (the model calls of the replay).

  WALTER_MEMORY_DATABASE_URL=<test dsn> walter-python bench/working_memory.py REFERENCE.jsonl OUT.json [--threads N]
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import timedelta

import psycopg
from psycopg.rows import dict_row

assert "5433" not in os.environ.get("WALTER_MEMORY_DATABASE_URL", "5433"), "bench writes only to the test database"
from walter_memory import events, extract2, llm, working  # noqa: E402
from walter_memory.db import connection  # noqa: E402

PROD = "postgresql://hindsight@127.0.0.1:5433/hindsight"
NOISE = re.compile(r'^\s*(The following is the Codex|\{"risk_level"|<system-reminder>|\[Your active task|\[IMPORTANT)')
POLICIES = ("systematic", "adaptive")


def load_thread(thread_id: str) -> tuple[str, list[dict]]:
    with psycopg.connect(PROD, row_factory=dict_row) as c:
        rows = c.execute("""select event_type, source, source_account, source_id, occurred_at, content, privacy_class,
                                   payload from core.events where thread_id = %s and event_type = any(%s)
                                   and privacy_class = 'cloud_allowed' order by occurred_at""",
                         (thread_id, list(extract2.MESSAGE_TYPES))).fetchall()
    rows = [r for r in rows if not NOISE.match(r["content"] or "")]
    return rows[0]["source"], rows


def turns_of(rows: list[dict]) -> list[list[dict]]:
    out = []
    for r in rows:
        if r["event_type"] == "message.sent" or not out:
            out.append([r])
        else:
            out[-1].append(r)
    return out


def replay(thread_id: str, refs: list[dict], pol: str) -> dict:
    source, rows = load_thread(thread_id)
    turns = turns_of(rows)
    tid = f"{thread_id}#{pol}"
    owner_ids, timeline = [], []      # owner event id per ordinal; per turn: state snapshot
    t_model = 0.0
    for k, turn in enumerate(turns):
        ids = events.record_events([{"event_type": r["event_type"], "source": source, "source_account": "bench",
                                     "source_id": f"{r['source_id']}#{pol}", "thread_id": tid,
                                     "occurred_at": r["occurred_at"], "content": r["content"],
                                     "privacy_class": "cloud_allowed", "payload": r["payload"] or {}} for r in turn])
        if turn[0]["event_type"] == "message.sent":
            owner_ids.append(ids["event_ids"][0])
        nxt = turns[k + 1][0]["occurred_at"] - timedelta(seconds=1) if k + 1 < len(turns) \
            else turn[-1]["occurred_at"] + timedelta(minutes=30)
        t0 = time.perf_counter()
        if pol == "systematic":
            extract2.process_thread(source, tid, force=True)
        else:
            extract2.process_thread(source, tid, mode="adaptive", now=nxt)
        t_model += time.perf_counter() - t0
        st = working.state(source, tid, subject=False)
        with connection() as conn:
            current = [r["id"] for r in conn.execute("""select item_id::text id from core.derived_items
                         where derived_by = 'l3.extract' and source_refs->>'thread' = %s and kind <> 'summary'
                           and status in ('derived','verified')""", (tid,))]
        timeline.append({"turn": len(owner_ids), "pending": [p["event_id"] for p in st["pending"]],
                         "items": [i["id"] for v in st["interpreted"].values() for i in v], "current": current,
                         "tokens": st["tokens"], "build_ms": st["build_ms"]})
    if pol == "adaptive":    # end of conversation: whatever still waits is interpreted (quiet)
        extract2.process_thread(source, tid, mode="adaptive", now=turns[-1][-1]["occurred_at"] + timedelta(minutes=30))
    with connection() as conn:
        items = conn.execute("""select item_id::text id, kind, content, created_at from core.derived_items
                                where derived_by = 'l3.extract' and source_refs->>'thread' = %s and kind <> 'summary'""",
                             (tid,)).fetchall()
        segs = conn.execute("""select status, usage, latency_ms, jsonb_array_length(rejected) rej, array_length(event_ids,1) n
                               from extraction.segments where thread_id = %s""", (tid,)).fetchall()
    return {"thread": thread_id, "policy": pol, "owner_ids": owner_ids, "timeline": timeline, "items": items,
            "segments": segs, "wall_s": round(t_model, 1)}


JUDGE = """Tu évalues une extraction de mémoire. Voici des éléments de RÉFÉRENCE (décisions, contraintes, objectifs, corrections,
préférences annotés à la main) et des éléments EXTRAITS automatiquement de la même conversation.
Pour chaque référence, indique les numéros des éléments extraits qui expriment la même chose (même sens ; une formulation
différente compte ; un élément plus large qui la contient clairement compte ; un élément voisin mais différent ne compte pas).
RÉFÉRENCES :
{refs}
EXTRAITS :
{items}
Réponds en JSON : {{"matches": {{"R1": [numéros], "R2": [], ...}}}}"""


def judge(refs: list[dict], items: list[dict]) -> dict[int, list[str]]:
    if not items:
        return {i: [] for i in range(len(refs))}
    prompt = JUDGE.format(refs="\n".join(f"R{i + 1}. [{r['kind']}] {r['text']}" for i, r in enumerate(refs)),
                          items="\n".join(f"{j + 1}. [{it['kind']}] {it['content']}" for j, it in enumerate(items)))
    res = llm.chat([{"role": "user", "content": prompt}], poste="general", processor="bench.p1.1.judge",
                   privacy_class="cloud_allowed", budget="recurring", response_format={"type": "json_object"},
                   max_tokens=3000, timeout=300)
    c = res["content"]
    data = json.loads(c[c.find("{"):c.rfind("}") + 1]).get("matches", {})
    out = {}
    for i in range(len(refs)):
        nums = data.get(f"R{i + 1}") or []
        out[i] = [items[n - 1]["id"] for n in nums if isinstance(n, int) and 1 <= n <= len(items)]
    return out


def score(run: dict, refs: list[dict], matches: dict[int, list[str]]) -> list[dict]:
    created = {it["id"]: it["created_at"] for it in run["items"]}
    rows = []
    for i, r in enumerate(refs):
        if r["m"] > len(run["owner_ids"]):
            continue
        src = run["owner_ids"][r["m"] - 1]
        avail_next = interp_next = in_memory = None
        for snap in run["timeline"]:
            if snap["turn"] == r["m"]:          # state right before the next owner turn
                ok_items = bool(set(matches[i]) & set(snap["items"]))
                interp_next = ok_items
                avail_next = ok_items or src in snap["pending"]
                in_memory = bool(set(matches[i]) & set(snap["current"])) or src in snap["pending"]
        rows.append({"ref": r["text"], "kind": r["kind"], "implicit": r["implicit"], "m": r["m"],
                     "available_next_turn": bool(avail_next), "interpreted_next_turn": bool(interp_next),
                     "available_next_turn_uncapped": bool(in_memory), "matched": matches[i],
                     "interpreted_final": bool(matches[i])})
    return rows


def main():
    ref_path, out_path = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index("--threads") + 1]) if "--threads" in sys.argv else None
    refs = defaultdict(list)
    for line in open(ref_path):
        if line.strip():
            r = json.loads(line); refs[r["thread"]].append(r)
    threads = list(refs)[:limit]
    from datetime import datetime, timezone
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=1))
    with connection() as conn:      # partitions first: parallel replays must not race to create the same month
        for t in threads:
            for r in load_thread(t)[1]:
                conn.execute("select core.ensure_event_partition(%s)", (r["occurred_at"],))
    jobs = [(t, p) for t in threads for p in POLICIES]
    runs = {}
    with cf.ThreadPoolExecutor(6) as ex:
        for run in ex.map(lambda tp: replay(tp[0], refs[tp[0]], tp[1]), jobs):
            runs[(run["thread"], run["policy"])] = run
            print(f"replayed {run['thread'][:12]} {run['policy']}: {len(run['segments'])} segments, {run['wall_s']} s",
                  flush=True)
    results = {"threads": len(threads), "references": sum(len(refs[t]) for t in threads), "policies": {}}
    for pol in POLICIES:
        scored, calls, ptok, ctok, lat, rej, items = [], 0, 0, 0, [], 0, 0
        for t in threads:
            run = runs[(t, pol)]
            m = judge(refs[t], run["items"])
            scored += score(run, refs[t], m)
            for s in run["segments"]:
                if s["status"] in ("extracted", "empty"):
                    calls += 1
                    u = s["usage"] or {}
                    ptok += int(u.get("prompt_tokens") or 0); ctok += int(u.get("completion_tokens") or 0)
                    lat.append(s["latency_ms"] or 0); rej += s["rej"] or 0
            items += len(run["items"])
        n = len(scored)

        def rate(key, subset=None):
            rows = [s for s in scored if subset is None or s["implicit"] == subset]
            return round(100 * sum(s[key] for s in rows) / max(1, len(rows)), 1)
        lat.sort()
        results["policies"][pol] = {
            "model_calls": calls, "prompt_tokens": ptok, "completion_tokens": ctok,
            "latency_ms_p50": lat[len(lat) // 2] if lat else None, "latency_ms_p95": lat[int(len(lat) * .95)] if lat else None,
            "items_extracted": items, "items_rejected": rej, "references_scored": n,
            "available_next_turn_pct": rate("available_next_turn"),
            "available_next_turn_implicit_pct": rate("available_next_turn", True),
            "available_next_turn_uncapped_pct": rate("available_next_turn_uncapped"),
            "interpreted_next_turn_pct": rate("interpreted_next_turn"),
            "interpreted_final_pct": rate("interpreted_final"),
            "interpreted_final_implicit_pct": rate("interpreted_final", True),
            "state_tokens_p50": sorted(s["tokens"] for t in threads for s in runs[(t, pol)]["timeline"])[
                len([1 for t in threads for _ in runs[(t, pol)]["timeline"]]) // 2],
            "state_build_ms_max": max(s["build_ms"] for t in threads for s in runs[(t, pol)]["timeline"]),
            "misses_final": [s["ref"] for s in scored if not s["interpreted_final"]],
            "rows": scored,
            "extracted": {t: [(it["kind"], it["content"]) for it in runs[(t, pol)]["items"]] for t in threads},
        }
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1, default=str)
    os.chmod(out_path, 0o600)
    print(json.dumps({p: {k: v for k, v in d.items() if k != "misses_final"} for p, d in results["policies"].items()},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
