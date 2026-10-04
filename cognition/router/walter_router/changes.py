"""What CHANGED since the previous cycle — the only thing worth a Telegram message (Monsieur, 2026-10-04).

Three kinds of change, measured between the latest snapshot of each source and the previous snapshot collected at
least MIN_GAP_H earlier (one cycle back), compared by the source's own external key (immune to our renames):
  new        a model appears on a leaderboard it was not on, or is newly listed by a provider
  nerf       a model's score on a leaderboard dropped by more than the board's threshold
  price_drop an offer of a model got cheaper by more than PRICE_DROP (same provider, same SKU)
A static comparison between models already known ("Astra beats Sol on criteria X") is never news: if Monsieur did
not choose it before, it was not interesting then and nothing has changed since.
"""
from __future__ import annotations

from . import select as sel

MIN_GAP_H = 24
PRICE_DROP = 0.15
NERF = {"aa_intelligence": 2.0, "bridgebench": 30.0}   # Elo-type boards: NERF_ELO
NERF_ELO = 15.0
BENCH_KINDS = ("aa", "mm", "da", "arena", "bridgebench")
OFFER_KINDS = ("openrouter", "kie", "hermes_providers")


def _previous(conn, kind: str) -> tuple[int | None, int | None]:
    latest = conn.execute("""select snapshot_id, fetched_at from models.snapshots where kind = %s
                             order by fetched_at desc, snapshot_id desc limit 1""", (kind,)).fetchone()
    if not latest:
        return None, None
    prev = conn.execute("""select snapshot_id from models.snapshots where kind = %s
                           and fetched_at < %s - make_interval(hours => %s)
                           order by fetched_at desc limit 1""", (kind, latest["fetched_at"], MIN_GAP_H)).fetchone()
    return latest["snapshot_id"], prev["snapshot_id"] if prev else None


def events(conn) -> dict:
    """{'new': {model_id: [why]}, 'nerf': {model_id: [why]}, 'price_drop': {model_id: [why]}}."""
    out: dict[str, dict[str, list]] = {"new": {}, "nerf": {}, "price_drop": {}}
    for kind in BENCH_KINDS:
        cur, prev = _previous(conn, kind)
        if not cur or not prev:
            continue
        old = {(r["benchmark"], r["task"], r["external_key"]): r["score"] for r in conn.execute(
            "select benchmark, task, external_key, max(score) as score from models.benchmarks where snapshot_id = %s "
            "group by 1, 2, 3", (prev,))}
        boards_before = {(b, t) for b, t, _ in old}
        for r in conn.execute("""select benchmark, task, external_key, model_id, max(score) as score
                                 from models.benchmarks where snapshot_id = %s group by 1, 2, 3, 4""", (cur,)):
            key = (r["benchmark"], r["task"], r["external_key"])
            board = f'{r["benchmark"]}:{r["task"]}'
            if key not in old:
                if (r["benchmark"], r["task"]) in boards_before:  # a brand-new board is not a new model
                    out["new"].setdefault(r["model_id"], []).append(f"nouveau sur {board}")
                continue
            limit = NERF.get(r["benchmark"], NERF_ELO)
            if old[key] - r["score"] > limit:
                out["nerf"].setdefault(r["model_id"], []).append(
                    {"board": board, "before": round(old[key], 1), "after": round(r["score"], 1)})
    for kind in OFFER_KINDS:
        cur, prev = _previous(conn, kind)
        if not cur or not prev:
            continue
        for r in conn.execute("""select n.model_id, n.provider, n.offer_key,
                                        coalesce(o.norm_price, (3 * o.price_in_1m + o.price_out_1m) / 4) as before,
                                        coalesce(n.norm_price, (3 * n.price_in_1m + n.price_out_1m) / 4) as after
                                 from models.offers n join models.offers o
                                   on o.snapshot_id = %s and o.provider = n.provider and o.offer_key = n.offer_key
                                 where n.snapshot_id = %s""", (prev, cur)):
            if r["before"] and r["after"] is not None and r["after"] < r["before"] * (1 - PRICE_DROP):
                out["price_drop"].setdefault(r["model_id"], []).append(
                    {"provider": r["provider"], "before": r["before"], "after": r["after"],
                     "drop_pct": round(100 * (1 - r["after"] / r["before"]))})
    for kind in OFFER_KINDS:  # a model newly listed by a provider (release), by catalogue id
        cur, prev = _previous(conn, kind)
        if not cur or not prev:
            continue
        for r in conn.execute("""select distinct n.model_id, n.provider from models.offers n
                                 where n.snapshot_id = %s and n.offer_key not like '%% | %%'
                                 and not exists (select 1 from models.offers o where o.snapshot_id = %s
                                                 and o.provider = n.provider and o.offer_key = n.offer_key)""",
                              (cur, prev)):
            out["new"].setdefault(r["model_id"], []).append(f'nouveau chez {r["provider"]}')
    return out


def changed(ev: dict, model_id: str) -> list:
    """Reasons a model counts as news (new or cheaper)."""
    return ev["new"].get(model_id, []) + [f'prix −{p["drop_pct"]} % ({p["provider"]})'
                                          for p in ev["price_drop"].get(model_id, [])]


def frontier_entrants(conn, run_id: int) -> list[dict]:
    """Text Pareto frontier points of this run that were not on the previous run's frontier."""
    prev = conn.execute("""select run_id from models.runs where status = 'ok' and run_id < %s
                           order by run_id desc limit 1""", (run_id,)).fetchone()
    if not prev:
        return []
    before = {(r["model_id"], r["variant"]) for r in conn.execute(
        "select model_id, variant from models.selection where run_id = %s and task = 'general' and level = 'frontier'",
        (prev["run_id"],))}
    return [r for r in conn.execute("""select * from models.selection where run_id = %s and task = 'general'
                                       and level = 'frontier' order by rank""", (run_id,))
            if (r["model_id"], r["variant"]) not in before]


def latest_snapshot_ids(conn) -> dict:
    return sel.latest_snapshots(conn)
