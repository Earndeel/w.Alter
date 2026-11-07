"""`walter-router research [CATEGORY…] [--source KIND] [--list] [--analyse]`: run research now — categories\n(research/categories), single sources, or the plan module (meters, mails, web, news, cost price) — then\noptionally recompute the choices and republish the page."""
from __future__ import annotations

import json

from walter_router.plan import subscriptions
from walter_router.store import db


def main(args) -> int:
    """walter-router research [CATEGORY…] [--source KIND] [--list] [--analyse]"""
    from walter_router.analysis import ingest
    from walter_router.research import categories, sources
    if args.list:
        out = {n: {"label": categories.get(n).LABEL[0], "sources": {k: sorted(v) if v else "tout"
                                                                    for k, v in categories.get(n).SOURCES.items()}}
               for n in categories.NAMES}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    if args.sources:
        unknown = sorted(set(args.sources) - set(sources.SOURCES))
        if unknown:
            print(json.dumps({"error": f"unknown source(s) {unknown}", "sources": sorted(sources.SOURCES)}))
            return 1
        parts, plans, names = None, False, []
    else:
        names = list(categories.NAMES) if not args.categories or "all" in args.categories else args.categories
        try:
            parts, plans = categories.plan(names)
        except KeyError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 1
    with db.connect() as conn:
        out = {"categories": names, "sources": sources.collect_all(conn, ingest.store, only=args.sources, parts=parts)}
        conn.commit()
        if plans:   # research plans: meters, billing mails, web research, then the cost price of a token
            from walter_router.plan import mail, watch
            out["plans"] = {"meters": subscriptions.refresh(conn)}
            conn.commit()
            for step, fn in (("mails", mail.scan), ("web", None if args.no_web else watch.run)):
                if fn is None:
                    continue
                try:
                    out["plans"][step] = fn(conn)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001 — one step down never blocks the others
                    conn.rollback()
                    out["plans"][step] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            from walter_router.plan import declared, news
            out["plans"]["offers_ending"] = declared.expiring(conn)
            try:
                out["plans"]["news_from_mails"] = len(news.from_mail(conn))
            except Exception as exc:  # noqa: BLE001
                out["plans"]["news_from_mails"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            out["plans"]["cost_price"] = subscriptions.record_costs(conn)
            conn.commit()
            if not args.no_notify:   # plan news, proposals and offer ends go out now, not at the next cycle
                from walter_router.analysis import telegram
                if conn.execute("select 1 from models.alerts where kind = 'plan_change' and status = 'open'").fetchone():
                    out["plans"]["notify"] = telegram.notify(conn)
                    conn.commit()
    if args.analyse:
        from walter_router.analysis.refresh import refresh
        out["analysis"] = {k: v for k, v in refresh(notify=False, skip_collect=True).items() if k in ("run_id", "selection_rows")}
        from walter_router.interface import library
        with db.connect() as conn:
            out["page"] = library.publish(conn).get("deployed")
    print(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    return 0
