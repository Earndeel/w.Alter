"""Read-only HTTP API of the development board + the live stream (SSE relaying pg_notify 'devboard') + the web page
(web/dist). Never writes: corrections go through `walter-devboard correct` (MCP devboard_correct)."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from psycopg.rows import dict_row

from . import cards, config, db

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
COMPONENTS = [("core", "Core"), ("cognition", "Cognition"), ("capabilities", "Capabilities"), ("ops", "Ops"),
              ("lab", "Lab")]
GROUPS = [("waiting_owner", "Attend ton accord"), ("in_progress", "En cours"), ("late_or_stale", "Oublié · en retard"),
          ("paused", "En pause"), ("done", "Fini cette semaine"), ("abandoned", "Abandonné")]
ORDER = {k: i for i, (k, _) in enumerate(GROUPS)}
CARD_COLS = """c.id, c.ref, c.title, c.module, c.status, c.owner, c.change, c.deadline, c.waiting_since, c.created_at,
               c.updated_at, c.last_activity_at,
               coalesce((select array_agg(distinct field) from devboard.corrections k where k.card_id = c.id), '{}')
                 as corrected"""
PING_S = 25.0

app = FastAPI(title="walter-devboard", docs_url=None, redoc_url=None, openapi_url=None)
_cache: dict[str, tuple[float, dict]] = {}
_owner: list[str] = []


def _owner_name() -> str:
    if not _owner:
        try:
            _owner.append(config.load().owner_name)
        except Exception:
            _owner.append(config.Config.owner_name)
    return _owner[0]


def _q(sql: str, args=()) -> list[dict]:
    with psycopg.connect(db.dsn(), row_factory=dict_row, autocommit=True, application_name="walter-devboard-web") as c:
        return c.execute(sql, args).fetchall()


def _cached(key: str, cmd: list[str]) -> dict:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < 60:
        return hit[1]
    try:
        out = json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        out = hit[1] if hit else {"modules": []}
    _cache[key] = (time.monotonic(), out)
    return out


def _layout() -> dict:
    return _cached("layout", ["walter", "layout", "show"])


def _status() -> dict:
    return _cached("status", ["walter", "status"])


def _component(module: str | None) -> str | None:
    layout = _layout()
    root = layout.get("walter_root", "/walter").rstrip("/") + "/"
    for m in layout.get("modules", []):
        if m["id"] == module:
            rest = str(m.get("vision_target") or "").removeprefix(root)
            return rest.split("/", 1)[0] or None
    return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _card(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k != "id"}
    out["flags"] = cards.flags(None, row, _today())
    out["component"] = _component(row["module"])
    out["corrected"] = list(row.get("corrected") or [])
    return out


def _cards(where: str = "true", args=()) -> list[dict]:
    return [_card(r) for r in _q(f"select {CARD_COLS} from devboard.cards c where {where} "
                                  "order by c.last_activity_at desc", args)]


def _group_key(c: dict) -> str | None:
    if c["status"] in ("in_progress", "paused") and (c["flags"]["late"] or c["flags"]["stale"]):
        return "late_or_stale"
    if c["status"] == "done" and c["updated_at"].date() < _today() - timedelta(days=7):
        return None
    return c["status"]


@app.get("/api/summary")
def summary() -> dict:
    all_ = _cards()
    pause = _q("select value from devboard.state where key = 'pause'")
    return {"inbox": sum(c["status"] == "waiting_owner" for c in all_),
            "open": sum(c["status"] in ("waiting_owner", "in_progress", "paused") for c in all_),
            "late_or_stale": sum(_group_key(c) == "late_or_stale" for c in all_),
            "decisions": _q("select count(*) n from devboard.decisions where removed_at is null")[0]["n"],
            "replaced": _q("select count(distinct older_id) n from devboard.decision_links")[0]["n"],
            "live": _q("select count(*) n from devboard.live")[0]["n"],
            "pause": pause[0]["value"] if pause else None, "owner_name": _owner_name()}


@app.get("/api/inbox")
def inbox() -> list[dict]:
    out = _cards("c.status = 'waiting_owner'")
    return sorted(out, key=lambda c: c["waiting_since"] or c["created_at"])


@app.get("/api/cards")
def list_cards(group: str = "status", q: str = "") -> list[dict]:
    where, args = "true", ()
    if q.strip():
        where, args = "(c.title ilike %s or c.ref ilike %s or c.change ilike %s or c.module ilike %s)", (f"%{q}%",) * 4
    items = _cards(where, args)
    if group == "module":
        mods: dict[str, list] = {}
        for c in items:
            if _group_key(c):
                mods.setdefault(c["module"] or "—", []).append(c)
        return [{"key": k, "label": k, "component": _component(k),
                 "cards": sorted(v, key=lambda c: ORDER.get(_group_key(c), 9))} for k, v in sorted(mods.items())]
    groups = {k: [] for k, _ in GROUPS}
    for c in items:
        k = _group_key(c)
        if k:
            groups[k].append(c)
    return [{"key": k, "label": label, "cards": groups[k]} for k, label in GROUPS]


def _decision_refs(anchors: list[str]) -> dict[str, dict]:
    if not anchors:
        return {}
    rows = _q("select id, anchor, date, title, doc_path, removed_at from devboard.decisions where anchor = any(%s)",
              (anchors,))
    links = _links([r["id"] for r in rows])
    return {r["anchor"]: {**_dec(r), **links.get(r["id"], {"replaces": [], "replaced_by": []})} for r in rows}


def _dec(r: dict) -> dict:
    return {"anchor": r["anchor"], "date": r["date"], "title": r["title"], "doc_path": r["doc_path"],
            "removed": r.get("removed_at") is not None}


def _links(ids: list[int] | None = None) -> dict[int, dict]:
    rows = _q("""select l.newer_id, l.older_id, l.quote, n.anchor n_anchor, n.date n_date, n.title n_title,
                        o.anchor o_anchor, o.date o_date, o.title o_title
                 from devboard.decision_links l join devboard.decisions n on n.id = l.newer_id
                 join devboard.decisions o on o.id = l.older_id
                 where %s::int[] is null or l.newer_id = any(%s) or l.older_id = any(%s)""", (ids, ids, ids))
    out: dict[int, dict] = {}
    for r in rows:
        out.setdefault(r["newer_id"], {"replaces": [], "replaced_by": []})["replaces"].append(
            {"anchor": r["o_anchor"], "date": r["o_date"], "title": r["o_title"], "quote": r["quote"]})
        out.setdefault(r["older_id"], {"replaces": [], "replaced_by": []})["replaced_by"].append(
            {"anchor": r["n_anchor"], "date": r["n_date"], "title": r["n_title"], "quote": r["quote"]})
    return out


@app.get("/api/cards/{ref}")
def card_detail(ref: str) -> dict:
    found = _cards("c.ref = %s", (ref,))
    if not found:
        raise HTTPException(404, "carte inconnue")
    c = found[0]
    cid = _q("select id from devboard.cards where ref = %s", (ref,))[0]["id"]
    links = _q("select kind, target from devboard.card_links where card_id = %s order by kind, target", (cid,))
    dec = _decision_refs([l["target"] for l in links if l["kind"] == "decision"])
    c["decisions"] = [dec[l["target"]] for l in links if l["kind"] == "decision" and l["target"] in dec]
    c["files"] = [l["target"] for l in links if l["kind"] == "file"]
    blocks = [l["target"] for l in links if l["kind"] == "blocks"]
    c["blocks"] = _q("select ref, title, status from devboard.cards where ref = any(%s)", (blocks,)) if blocks else []
    c["blocked_by"] = _q("""select c.ref, c.title, c.status from devboard.card_links l join devboard.cards c
                            on c.id = l.card_id where l.kind = 'blocks' and l.target = %s""", (ref,))
    c["evidence"] = _q("""select kind, source_ref, seq, quote, at from devboard.card_evidence where card_id = %s
                          order by at desc, id desc limit 50""", (cid,))
    c["activity"] = _q("""select at, kind, source_ref, text from devboard.activity where card_id = %s
                          order by at desc, id desc limit 100""", (cid,))
    c["corrections"] = _q("""select field, value, reason, by, at from devboard.corrections where card_id = %s
                             order by at desc""", (cid,))
    return c


@app.get("/api/today")
def today() -> list[dict]:
    return _q("""select a.at, a.kind, a.source_ref, a.text, c.ref, c.title, c.module
                 from devboard.activity a left join devboard.cards c on c.id = a.card_id
                 where a.at >= date_trunc('day', now()) order by a.at desc, a.id desc limit 300""")


@app.get("/api/decisions")
def decisions(replaced: int = 0) -> list[dict]:
    rows = _q("""select id, anchor, date, title, doc_path, removed_at from devboard.decisions
                 where removed_at is null order by date desc, id desc""")
    links = _links()
    out = []
    for r in rows:
        d = {**_dec(r), **links.get(r["id"], {"replaces": [], "replaced_by": []})}
        if not replaced or d["replaces"] or d["replaced_by"]:
            out.append(d)
    return out


def _colour(module_cards: list[dict]) -> str:
    if any(c["flags"]["late"] or c["flags"]["stale"] for c in module_cards):
        return "red"
    if any(c["status"] == "waiting_owner" for c in module_cards):
        return "amber"
    recent = [c for c in module_cards if _group_key(c)]
    if recent and all(c["status"] == "done" for c in recent):
        return "green"
    return "blue"


@app.get("/api/vision")
def vision() -> list[dict]:
    layout, status = _layout(), _status()
    health = {m["id"]: m.get("runtime_health") for m in status.get("modules", [])}
    by_module: dict[str, list] = {}
    for c in _cards():
        by_module.setdefault(c["module"], []).append(c)
    comps = {k: {"key": k, "label": label, "modules": []} for k, label in COMPONENTS}
    for m in layout.get("modules", []):
        comp = _component(m["id"])
        if comp not in comps:
            continue
        mc = by_module.get(m["id"], [])
        comps[comp]["modules"].append({
            "id": m["id"], "path": m.get("vision_target"), "health": health.get(m["id"]), "color": _colour(mc),
            "counts": {k: sum(_group_key(c) == k for c in mc) for k, _ in GROUPS}})
    return list(comps.values())


@app.get("/api/live")
def live() -> list[dict]:
    return _q("""select l.session_id, l.runtime, l.title, l.at, c.ref, c.title card_title, c.module
                 from devboard.live l left join devboard.cards c on c.id = l.card_id order by l.at desc""")


@app.get("/api/docs")
def docs_list() -> list[dict]:
    docs = _q("select path, title, kind, mtime from devboard.documents order by kind, path")
    secs = _q("""select doc_path, anchor, heading, level, line from devboard.sections where removed_at is null
                 order by doc_path, line""")
    by: dict[str, list] = {}
    for s in secs:
        by.setdefault(s["doc_path"], []).append({k: s[k] for k in ("anchor", "heading", "level", "line")})
    return [{**d, "sections": by.get(d["path"], [])} for d in docs]


@app.get("/api/docs/{path:path}")
def doc(path: str, anchor: str = "") -> dict:
    full = "/" + path.lstrip("/")
    row = _q("select path, title, kind from devboard.documents where path = %s", (full,))
    if not row:
        raise HTTPException(404, "document inconnu")
    if anchor:
        sec = _q("""select anchor, heading, body from devboard.sections where doc_path = %s and anchor = %s""",
                 (full, anchor))
        if not sec:
            raise HTTPException(404, "section inconnue")
        return {**row[0], "anchor": anchor, "markdown": sec[0]["body"]}
    try:
        text = Path(full).read_text(errors="replace")
    except OSError:
        raise HTTPException(404, "document illisible")
    return {**row[0], "anchor": None, "markdown": text}


@app.get("/api/stream")
async def stream():
    async def events():
        async with await psycopg.AsyncConnection.connect(db.dsn(), autocommit=True,
                                                         application_name="walter-devboard-stream") as c:
            await c.execute("listen devboard")
            yield ": ok\n\n"
            while True:
                got = False
                async for n in c.notifies(timeout=PING_S, stop_after=1):
                    got = True
                    yield f"event: change\ndata: {n.payload}\n\n"
                if not got:
                    yield ": ping\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/{rest:path}", include_in_schema=False)
def page(rest: str = ""):
    if rest.startswith("api/"):
        raise HTTPException(404)
    f = (DIST / rest).resolve()
    if rest and f.is_file() and DIST.resolve() in f.parents:
        return FileResponse(f)
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "interface pas encore construite (web/: npm run build)")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
