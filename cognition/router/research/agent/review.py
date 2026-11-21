"""Deterministic digest of a refresh cycle, the input of the 48 h analysis agent (economic tier model).

Everything here is computed from the database; the agent only reads it, investigates and writes a report with
proposals (aliases, profile notes, weights) — it never changes the database or the configuration itself.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from walter_router.analysis import tiers
from walter_router.analysis import select as sel

MY_PROVIDERS = ("openrouter", "kie", "codex", "arnict", "google-flow")


def _previous_snapshot(conn, kind: str, latest: int) -> int | None:
    row = conn.execute("""select snapshot_id from models.snapshots where kind = %s and snapshot_id <> %s
                          order by fetched_at desc limit 1""", (kind, latest)).fetchone()
    return row["snapshot_id"] if row else None


INTERFACES = ("chat", "image", "video", "audio", "music", "decisions", "rerank", "transcription", "embedding")


def _family(model_id: str) -> str:
    return model_id.split("-", 1)[0]


def blocked_challengers(conn) -> list[dict]:
    """A model that beats one of the owner's choices on a board but has no offer: often the same model sold under
    another name (2026-11-21: AA « Bison 31B » = OpenRouter « Bison 1 », a 31B model). Its unscored offers of the
    same family are the candidates that matter most: the link gives the proposal its price and its route."""
    scored = {r["model_id"] for r in conn.execute("select model_id from models.model_scores")}
    out = []
    for a in conn.execute("""select distinct on (subject) subject, task from models.alerts
                             where kind = 'challenger' and status in ('open', 'notified')
                             and last_seen > now() - interval '7 days' and coalesce(evidence->'callable_via', '[]') = '[]'"""):
        offered = conn.execute("select 1 from models.catalog where model_id = %s and providers && %s",
                               (a["subject"], list(MY_PROVIDERS))).fetchone()
        if offered:
            continue
        iface = conn.execute("select interface from models.tasks where task = %s", (a["task"],)).fetchone()
        for r in conn.execute("""select distinct model_id, interface from models.catalog where not ranked
                                 and interface = %s and providers && %s""",
                              (iface["interface"] if iface else "chat", list(MY_PROVIDERS))):
            if r["model_id"] in scored or _family(r["model_id"]) != _family(a["subject"]):
                continue
            out.append({"model_id": r["model_id"], "interface": r["interface"], "closest_scored": a["subject"],
                        "similarity": round(SequenceMatcher(None, r["model_id"], a["subject"]).ratio(), 2),
                        "why": f"« {a['subject']} » bat un choix de Monsieur ({a['task']}) mais n'a aucune offre"})
    return out


def unmatched(conn, limit: int = 25) -> list[dict]:
    """Callable models without any score, next to a scored model with a very similar id: probable naming gaps
    between sources (candidate aliases for aliases.json). The challengers blocked for want of an offer come first."""
    scored = [r["model_id"] for r in conn.execute("select model_id from models.model_scores")]
    first = blocked_challengers(conn)
    out = []
    for r in conn.execute("""select distinct model_id, interface from models.catalog
                             where not ranked and interface = any(%s)
                             and providers && %s""", (list(INTERFACES), list(MY_PROVIDERS))):
        if any(f["model_id"] == r["model_id"] for f in first):
            continue
        best = max(scored, key=lambda s: SequenceMatcher(None, r["model_id"], s).ratio(), default=None)
        ratio = SequenceMatcher(None, r["model_id"], best).ratio() if best else 0
        if ratio >= 0.82:
            out.append({"model_id": r["model_id"], "interface": r["interface"], "closest_scored": best,
                        "similarity": round(ratio, 2)})
    return (first + sorted(out, key=lambda x: -x["similarity"]))[:limit]


def board_gaps(conn, top: int = 12) -> list[dict]:
    """Leading models (AA Intelligence top, and the text tiers in use) a Design Arena reference has not measured yet:
    the board may lag behind recent releases (owner 2026-11-21), so their absence says nothing about their quality."""
    snaps = sel.latest_snapshots(conn)
    lead = [r["model_id"] for r in conn.execute(
        """select model_id, max(score) as s from models.benchmarks where snapshot_id = %s and benchmark = 'aa'
           group by model_id order by s desc limit %s""", (snaps.get("aa"), top))] if snaps.get("aa") else []
    lead += [r["pinned_model_id"] for r in conn.execute(
        "select pinned_model_id from models.preferences where task = 'general' and pinned_model_id is not null")]
    out = []
    for b in conn.execute("""select tb.task, tb.benchmark, tb.bench_task, p.pinned_model_id from models.task_benchmarks tb
                             left join models.preferences p on p.task = tb.task and p.role = 'default'
                             where tb.benchmark like 'da_%%' and tb.is_primary"""):
        sid = sel.board_snapshot(conn, snaps, b["benchmark"], b["bench_task"])
        if sid is None:
            continue
        have = {r["model_id"] for r in conn.execute("""select distinct model_id from models.benchmarks
                                                      where snapshot_id = %s and benchmark = %s and task = %s""",
                                                   (sid, b["benchmark"], b["bench_task"]))}
        missing = [m for m in dict.fromkeys(lead + [b["pinned_model_id"]]) if m and m not in have]
        if missing:
            out.append({"task": b["task"], "board": f'Design Arena {b["bench_task"]}', "not_measured": missing})
    return out


def price_changes(conn) -> list[dict]:
    """Price moves since the previous snapshot of each provider, restricted to the router's short list."""
    snaps = sel.latest_snapshots(conn)
    short = [r["model_id"] for r in conn.execute("select model_id from models.shortlist")]
    out = []
    for kind in ("openrouter", "kie"):
        if kind not in snaps:
            continue
        prev = _previous_snapshot(conn, kind, snaps[kind])
        if not prev:
            continue
        for r in conn.execute("""select n.model_id, n.offer_key, o.norm_price as before, n.norm_price as after,
                                        o.price_in_1m as in_before, n.price_in_1m as in_after
                                 from models.offers n join models.offers o
                                   on o.snapshot_id = %s and o.provider = n.provider and o.offer_key = n.offer_key
                                 where n.snapshot_id = %s and n.model_id = any(%s)
                                   and (o.norm_price is distinct from n.norm_price
                                        or o.price_in_1m is distinct from n.price_in_1m)""",
                              (prev, snaps[kind], short)):
            out.append({"provider": kind, **r})
    return out[:40]


def digest(conn) -> dict:
    run = conn.execute("""select run_id, status, started_at, finished_at, summary from models.runs
                          order by run_id desc limit 1""").fetchone()
    summary = (run or {}).get("summary") or {}
    sources = {k: v for k, v in (summary.get("sources") or {}).items()}
    tiers_now = {r["level"]: {"model_id": r["model_id"], "variant": r["variant"], "score": r["quality"],
                              "cost": r["real_cost"]}
                 for r in conn.execute("""select * from models.selection where run_id = %s and task = 'general'
                                          and level in ('L1', 'L2', 'L3')""", (run["run_id"],))} if run else {}
    declared = {r["role"]: f'{r["pinned_model_id"]}/{r["pinned_variant"]}' for r in conn.execute(
        "select role, pinned_model_id, pinned_variant from models.preferences where task = 'general'")}
    return {
        "run": {k: run[k] for k in ("run_id", "status", "started_at", "finished_at")} if run else None,
        "sources": sources,
        "alerts_created": summary.get("alerts"),
        "providers": {r["provider"]: {"ok": r["ok"], "detail": r["detail"]}
                      for r in conn.execute("select * from models.provider_status")},
        "tiers": {"method": tiers.__doc__.strip().split("\n\n")[1], "computed": tiers_now, "declared": declared},
        "best_per_task": {r["task"]: {"model_id": r["model_id"], "score": r["quality"], "provider":
                                      r["subscription"] or r["provider"]}
                          for r in conn.execute("""select * from models.selection where run_id = %s and level = 'best'
                                                   and rank = 1""", (run["run_id"],))} if run else {},
        "unmatched_candidates": unmatched(conn),
        "design_arena_not_measured": board_gaps(conn),
        "price_changes_shortlist": price_changes(conn),
        "open_unranked_count": conn.execute("""select count(*) as n from models.alerts where kind = 'unranked'
                                               and status = 'open'""").fetchone()["n"],
        "sources_ages_h": {r["kind"]: round(float(r["h"]), 1) for r in conn.execute(
            "select kind, extract(epoch from now() - fetched_at) / 3600 as h from models.latest_snapshots")},
    }
