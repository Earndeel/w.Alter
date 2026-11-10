#!/usr/bin/env python3
"""Selective g0 → g1 migration (2026-11-10 mandate, steps 4-5): which pre-V1 messages to re-read, and what it gives.

  walter-python bench/g0_migrate.py select                 seeds = source messages of the g0 items worth keeping
  walter-python bench/g0_migrate.py run --tag T [--scope sample|corpus|all] [--max-threads N]
                                                           extract2.backfill on those seeds (the live extraction path)
  walter-python bench/g0_migrate.py eval --tag T           what the backfill produced (class of each new item, by the
                                                           g0 audit labeller) and how much of the kept g0 knowledge of
                                                           the processed threads g1 now holds (uniqueness re-check)

What is worth keeping (Monsieur, 2026-11-10): personal knowledge first, his other projects; Walter's own technical
history is NOT migrated (its truth is the module documentation and the decisions register; g0 stays readable as a
targeted fallback). An item is a candidate when the audit labelled it personal / other_project with value >= 1, not
stale, and absent or partly absent from g1; items the audit only predicted (local classifier, CV accuracy in
report.json) count when that prediction is personal / other_project with p >= 0.5. Only items with a canonical source
message can be re-read (the others are counted, not migrated).

Run it against a restored copy first: WALTER_MEMORY_DATABASE_URL points every walter_memory call at that database.
Outputs (ids and numbers only) in `walter instance path state memory`/bench/g0_migrate/, 0600. Prints aggregates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

import g0_audit  # noqa: E402

KEEP = ("personal", "other_project")


def out_dir() -> Path:
    d = g0_audit.out_dir().parent / "g0_migrate"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def save(path: Path, obj) -> None:
    g0_audit.save(path, obj)


def select(_a) -> None:
    from walter_memory.db import connection
    a_dir = g0_audit.out_dir()
    lab = json.loads((a_dir / "sample-labels.json").read_text())["labels"]
    uniq = json.loads((a_dir / "sample-unique.json").read_text())
    pred = json.loads((a_dir / "predicted.json").read_text())
    cands, why = [], Counter()
    for i, p in pred.items():
        if i in lab:
            l = lab[i]
            ok = l["c"] in KEEP and l["u"] >= 1 and l["v"] != "s" and uniq.get(i, "n") != "y"
            why["labelled_" + ("kept" if ok else "dropped")] += 1
        else:
            ok = p["c"] in KEEP and max(p["p"].get(c, 0) for c in KEEP) >= 0.5
            why["predicted_" + ("kept" if ok else "dropped")] += 1
        if ok:
            cands.append(i)
    with connection() as conn:
        rows = conn.execute("""select d.item_id::text id, array(select e.event_id::text from core.events e
                                   where e.event_id = any(d.source_event_ids) and e.event_type like 'message.%%'
                                     and e.thread_id is not null) evs
                               from core.derived_items d where d.item_id = any(%s::uuid[])""", (cands,)).fetchall()
        item_events = {r["id"]: r["evs"] for r in rows}
        # items whose source is a whole session (conversation.started): its 2 messages closest to the item (local
        # embeddings, same thread). extract2 keeps only what an exact quote of those messages establishes.
        sess = conn.execute("""select d.item_id::text id, e.source, e.thread_id, c.embedding::text emb
                               from core.derived_items d join core.events e on e.event_id = d.source_event_ids[1]
                               join search.chunks c on c.kind = 'derived' and c.ref_id = d.item_id and c.chunk_no = 0
                               where d.item_id = any(%s::uuid[]) and e.event_type = 'conversation.started'
                                 and e.thread_id is not null""", ([i for i, v in item_events.items() if not v],)).fetchall()
        for r in sess:
            near = conn.execute("""select c.ref_id::text id from search.chunks c join core.events e on e.event_id = c.ref_id
                                   where c.kind = 'event' and c.source = %s and c.thread_id = %s
                                     and e.event_type like 'message.%%' and c.embedding is not null
                                   order by c.embedding <=> %s::vector limit 2""",
                                (r["source"], r["thread_id"], r["emb"])).fetchall()
            item_events[r["id"]] = [x["id"] for x in near]
            why["session_source_resolved" if near else "session_source_unresolved"] += 1
        ev = sorted({e for v in item_events.values() for e in v})
        th = conn.execute("""select event_id::text, source || '/' || thread_id t from core.events
                             where event_id = any(%s::uuid[])""", (ev,)).fetchall()
    thread_of = {r["event_id"]: r["t"] for r in th}
    # the sample threads: threads holding a labelled candidate (recall is measured on them, with model labels)
    sample_threads = sorted({thread_of[e] for i in cands if i in lab for e in item_events.get(i, []) if e in thread_of})
    out = {"candidates": cands, "item_events": item_events, "thread_of": thread_of, "sample_threads": sample_threads}
    save(out_dir() / "selection.json", out)
    print(json.dumps({"why": why, "candidates": len(cands), "with_source_message": sum(1 for v in item_events.values() if v),
                      "seed_events": len(ev), "threads": len(set(thread_of.values())),
                      "sample_threads": len(sample_threads),
                      "candidates_by_class": Counter((lab.get(i) or pred[i])["c"] for i in cands)}, indent=1))


def run(a) -> None:
    from walter_memory import extract2
    sel = json.loads((out_dir() / "selection.json").read_text())
    if a.scope == "corpus":
        # the selected threads that hold a benchmark question (corpus v2 was sampled independently of the selection;
        # the seeds stay the selection's): the bench then measures what a real migration of those threads gives
        from walter_memory.db import connection
        rows = json.loads((g0_audit.out_dir().parent / "g0_g1" / "corpus-v2.json").read_text())
        rows = rows["rows"] if isinstance(rows, dict) else rows
        with connection() as conn:
            q = conn.execute("""select source || '/' || thread_id t from core.events where event_id = any(%s::uuid[])""",
                             ([r["source_event"] for r in rows],)).fetchall()
        threads = {r["t"] for r in q} & set(sel["thread_of"].values())
    else:
        threads = set(sel["sample_threads"]) if a.scope == "sample" else set(sel["thread_of"].values())
    seeds = sorted(e for e, t in sel["thread_of"].items() if t in threads)
    if a.max_threads:
        keep = sorted(threads, key=lambda t: hashlib.sha256(f"{a.tag}:{t}".encode()).hexdigest())[:a.max_threads]
        seeds = [e for e in seeds if sel["thread_of"][e] in set(keep)]
    db = os.environ.get("WALTER_MEMORY_DATABASE_URL", "production")
    print(f"database: {'copy' if '5433' not in db and db != 'production' else 'PRODUCTION'}; threads "
          f"{len({sel['thread_of'][e] for e in seeds})}, seeds {len(seeds)}", file=sys.stderr)
    if ("5433" in db or db == "production") and not a.production:
        sys.exit("refused: this is the production database (pass --production for the validated rollout)")
    # personal knowledge first: threads ordered by how many candidates they carry back, then by batches, each one
    # checked against the Codex weekly meter (Walter Router's reading; above QUOTA_SWITCH the router would move the
    # extraction poste to paid routes) and against the segment cap of this run
    weight = Counter(sel["thread_of"][e] for i in sel["candidates"] for e in sel["item_events"].get(i, [])
                     if e in sel["thread_of"])
    order = sorted({sel["thread_of"][e] for e in seeds}, key=lambda t: (-weight[t], t))
    total, done_seg = Counter(), 0
    for k in range(0, len(order), a.batch):
        meter = codex_meter()
        if meter is not None and meter >= a.ceiling:
            total["stopped_quota"] = meter
            break
        if a.max_segments and done_seg >= a.max_segments:
            total["stopped_segments"] = done_seg
            break
        batch = set(order[k:k + a.batch])
        r = extract2.backfill([e for e in seeds if sel["thread_of"][e] in batch], tag=a.tag, workers=a.workers,
                              dry=a.dry)
        done_seg += r["segments"]
        total.update({x: v for x, v in r.items() if isinstance(v, (int, float)) and x != "tag"})
        print(json.dumps({"batch": k // a.batch, "meter": meter, **{x: r[x] for x in ("threads", "segments", "items")}}),
              file=sys.stderr)
    out = {"tag": a.tag, **total}
    prev = out_dir() / f"run-{a.tag}.json"
    old = json.loads(prev.read_text())["seeds"] if prev.exists() else []
    save(prev, {"seeds": sorted(set(old) | set(seeds)), "result": out})
    print(json.dumps(out, indent=1))


def codex_meter() -> float | None:
    """Weekly Codex quota used (%), as Walter Router last read it (models.latest_subscription_usage, read-only)."""
    from walter_memory.db import connection
    try:
        with connection() as conn:
            r = conn.execute("""select max(used_percent) p from models.latest_subscription_usage
                                where source = 'codex_usage_api' and window_name = 'weekly'""").fetchone()
        return float(r["p"]) if r and r["p"] is not None else None
    except Exception:  # noqa: BLE001 — no meter: the segment cap still bounds the run
        return None


EVAL_SAMPLE = 400


def evaluate(a) -> None:
    from walter_memory import search
    from walter_memory.db import connection
    sel = json.loads((out_dir() / "selection.json").read_text())
    run_ = json.loads((out_dir() / f"run-{a.tag}.json").read_text())
    search.index_pending()
    with connection() as conn:
        new = conn.execute("""select item_id::text id, kind, status, attributes->>'subject' subject,
                                     attributes->>'epistemic' epistemic, scope, stage
                              from core.derived_items where attributes->>'backfill' = %s""", (a.tag,)).fetchall()
    ids = sorted((r["id"] for r in new if r["status"] == "derived"),
                 key=lambda x: hashlib.sha256(x.encode()).hexdigest())[:EVAL_SAMPLE]
    labels = g0_audit.label_ids(ids)              # same labeller as the audit: comparable classes
    subj = Counter((r["subject"] or "-").split(":")[0] for r in new)
    # recall: the labelled g0 candidates of the processed threads — is their information in g1 now?
    seeds = set(run_["seeds"])
    done_threads = {sel["thread_of"][e] for e in seeds}
    lab = json.loads((g0_audit.out_dir() / "sample-labels.json").read_text())["labels"]
    before = json.loads((g0_audit.out_dir() / "sample-unique.json").read_text())
    probe = [i for i in sel["candidates"] if i in lab and any(sel["thread_of"].get(e) in done_threads
                                                               for e in sel["item_events"].get(i, []))]
    after = g0_audit.uniqueness_of(probe)
    res = {"tag": a.tag, "run": run_["result"], "new_items": len(new),
           "status": Counter(r["status"] for r in new), "kinds": Counter(r["kind"] for r in new),
           "subjects": subj, "scope": Counter(r["scope"] for r in new),
           "labelled_new": len(labels), "new_class": Counter(v["c"] for v in labels.values()),
           "new_value": Counter(f"u{v['u']}" for v in labels.values()),
           "new_stale": sum(v["v"] == "s" for v in labels.values()),
           "recall_probe": len(probe),
           "before": Counter(before.get(i, "?") for i in probe), "after": Counter(after.get(i, "?") for i in probe),
           "per_class_after": {c: Counter(after.get(i, "?") for i in probe if lab[i]["c"] == c) for c in KEEP}}
    save(out_dir() / f"eval-{a.tag}.json", {**res, "probe": {i: [before.get(i), after.get(i)] for i in probe}})
    print(json.dumps(res, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    p = sub.add_parser("run")
    p.add_argument("--tag", required=True)
    p.add_argument("--scope", choices=("sample", "corpus", "all"), default="sample")
    p.add_argument("--max-threads", type=int, default=0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--production", action="store_true")
    p.add_argument("--batch", type=int, default=50, help="threads per batch (meter checked between batches)")
    p.add_argument("--ceiling", type=float, default=60.0, help="stop when the Codex weekly meter reaches this %%")
    p.add_argument("--max-segments", type=int, default=0)
    p = sub.add_parser("eval")
    p.add_argument("--tag", required=True)
    a = ap.parse_args()
    {"select": select, "run": run, "eval": evaluate}[a.cmd](a)


if __name__ == "__main__":
    main()
