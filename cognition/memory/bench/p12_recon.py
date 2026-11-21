"""P1.2 reconsolidation re-measure on the bench subjects (THROWAWAY test database, after bench/memory_v1.py).

Undoes the previous reconsolidation of the bench subjects, judges the adaptive items with both judges (pairs kept for
audit), applies reconsolidation with the configured Router tier, rebuilds and measures what stays current, what moves to
history and whether a reference is lost.

  WALTER_MEMORY_DATABASE_URL=<test dsn> walter-python bench/p12_recon.py REFERENCE.jsonl OUT_DIR
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

assert "5433" not in os.environ.get("WALTER_MEMORY_DATABASE_URL", "5433")
from walter_memory import consolidate, working  # noqa: E402
from walter_memory.db import connection  # noqa: E402

_s = importlib.util.spec_from_file_location("mv1", Path(__file__).with_name("memory_v1.py"))
mv1 = importlib.util.module_from_spec(_s); _s.loader.exec_module(mv1)


def main():
    refs = defaultdict(list)
    for line in open(sys.argv[1]):
        if line.strip():
            r = json.loads(line); refs[r["thread"]].append(r)
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    with connection() as conn:   # undo the first reconsolidation
        conn.execute("""update core.derived_items set valid_to = null, attributes = attributes - 'expired_reason'
                        where source_refs->>'thread' like '%%#adaptive' and attributes ? 'expired_reason'""")
        conn.execute("""update core.derived_items set status = 'derived', valid_to = null,
                          attributes = attributes - 'superseded_by' - 'how'
                        where source_refs->>'thread' like '%%#adaptive' and attributes->>'how' in ('merged', 'superseded')""")
    rows, audit, props = [], [], []
    for t, rr in refs.items():
        tid, key = f"{t}#adaptive", f"bench-{t}#adaptive"
        with connection() as conn:
            items = conn.execute("""select item_id::text id, kind, content from core.derived_items where derived_by = 'l3.extract'
                                    and source_refs->>'thread' = %s and kind <> 'summary'""", (tid,)).fetchall()
        m1 = mv1.judge_with(mv1.judge1, rr, items)
        m2 = mv1.judge_with(mv1.judge2, rr, items)
        text = {i["id"]: i["content"] for i in items}
        for i, r in enumerate(rr):
            if bool(m1[i]) != bool(m2[i]):
                audit.append({"thread": t, "ref": r["text"], "implicit": r["implicit"],
                              "judge1": [text[x] for x in m1[i]], "judge2": [text[x] for x in m2[i]]})
        before = consolidate.build_subject(key, force=True)["cloud"]
        rec = consolidate.reconsolidate(key, apply=True)
        after = consolidate.build_subject(key, force=True)["cloud"]
        with connection() as conn:
            all_items = {r["id"]: r for r in conn.execute("""select item_id::text id, status, valid_to, stage, attributes
                         from core.derived_items where source_refs->>'thread' = %s and kind <> 'summary'""", (tid,))}
            cur = {i["id"] for i in consolidate.current(consolidate.items_of(conn, consolidate.threads_of(conn, key),
                                                                               ["cloud_allowed"]), mv1.datetime.now(mv1.timezone.utc))}
        repl = {k: (v["attributes"] or {}).get("superseded_by") for k, v in all_items.items() if v["status"] == "superseded"}

        def resolve(x):
            seen = set()
            while x in repl and repl[x] and x not in seen:
                seen.add(x); x = repl[x]
            return x
        for i, r in enumerate(rr):
            ids = {resolve(x) for x in m1[i]}
            rows.append({"thread": t, "ref": r["text"], "kind": r["kind"], "matched": bool(m1[i]),
                         "current_after": bool(ids & cur), "history_after": bool(m1[i])})
        tx = lambda x: (text.get(x) or "")[:140]
        props.append({"thread": t, "current_before": before["current"], "current_after": after["current"],
                      "merge": [[tx(x) for x in g] for g in rec["proposals"]["merge"]],
                      "supersede": [{"old": tx(s["old"]), "new": tx(s["new"]), "why": s["why"]} for s in rec["proposals"]["supersede"]],
                      "expire_or_complete": [{"item": tx(e["id"]), "why": e["why"]} for e in rec["proposals"]["expire"]]})
        print(t[:10], before["current"], "→", after["current"], {k: len(v) for k, v in rec["proposals"].items()}, flush=True)
    n = len(rows)
    res = {"references": n, "matched_pct": round(100 * sum(r["matched"] for r in rows) / n, 1),
           "current_after_pct": round(100 * sum(r["current_after"] for r in rows) / n, 1),
           "lost_after": [r["ref"] for r in rows if r["matched"] and not r["current_after"]],
           "items_before": sum(p["current_before"] for p in props), "items_after": sum(p["current_after"] for p in props),
           "judge_disagreements": len(audit)}
    (out / "recon.json").write_text(json.dumps({"summary": res, "proposals": props}, ensure_ascii=False, indent=1))
    (out / "judge_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1))
    for f in out.iterdir():
        os.chmod(f, 0o600)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
