"""Projections Personnel and Situationnel (docs/PROJECTIONS.md § 2, lot P2): « où en suis-je ? ».

Like the project projection (projection.py), a projection here is a READ of what memory already holds — no table, no
cache, no model call — with the same rules of reliability and the same effective states of goals:

  personal(at=)   the owner (subject `owner`, and statements moved off a project as one of his own things):
                  rules in force (constraints, corrections, his decisions; preferences apart), what holds until a
                  date, his goals and commitments by what their evidence shows (projection.goal_buckets), his facts,
                  and the transient states older than state_ttl_days, marked « à revérifier ».
  situation()     now: where (whereabouts), what is on the agenda (calendar), the owner's open objectives on the
                  Run Plane, the subjects memory learned about lately, the day / week views and recent episodes;
                  every line with its freshness. With a session: that thread's working state.

Privacy (P2 criterion « aucune donnée local_only vers un modèle cloud »): for a cloud reader these projections carry
only `cloud_allowed` rows, whatever the cloud ceiling of Context is; a local row (position, places, local episodes
and period views) is counted, never rendered. A local reader (max_privacy="local_only") gets everything.

Keys: `owner` (aliases moi, monsieur, personnel) and `now` (maintenant, situation); `me` = both (« où en suis-je »).
Read by memory_view(depth="state", key=…), `walter-memory state owner|now|me`, and Context's « État courant »
section when the message asks for the owner's own state."""
from __future__ import annotations

import contextlib
import re
from functools import lru_cache
import time
from datetime import datetime, timedelta, timezone

from . import projection as P
from .db import connection

OWNER_KEYS = {"owner", "monsieur", "moi", "personnel", "personal"}
NOW_KEYS = {"now", "maintenant", "situation", "situationnel"}
BOTH_KEYS = {"me", "ouensuisje"}
ORDER_CLASSES = ["cloud_allowed", "redacted_cloud", "local_only"]
AGENDA = timedelta(days=7)
LEARNED = timedelta(days=3)          # « appris récemment »: the subjects memory got new knowledge about
EPISODES = timedelta(days=7)
RULE_ORDER = {"correction": 0, "constraint": 1, "decision": 2, "preference": 3}
FACT_FRESH = timedelta(days=30)      # a fact said once, longer ago: shown dated « non reconfirmé », after the fresh ones
VIEW_FRESH = timedelta(hours=36)     # a day / week view built longer ago is shown as old, never as the current period

# P2 corrections (19/11). A rule is normative: it says what must or must not be done, what he wants or refuses. A
# « constraint » or « correction » that only describes (a technical detail, a biographical fact) is not a rule.
NORM = re.compile(r"(?i)(\bjamais\b|\btoujours\b|\bne (?:doit|doivent|faut|veut|souhaite|plus|pas)\b|\bdoi(?:t|vent)\b|"
                  r"\bil faut\b|\bveut (?:que|qu'|des?|les?|la|un|une|du|plus|moins|être)\b|\bexige|\binterdi|\brefuse|"
                  r"\bpr[ée]f[èe]re|\bpas de\b|\bplus de\b|\bchaque (?:fois|message|réponse|changement)\b|"
                  r"\bsyst[ée]matiquement\b|\bavant (?:de|tout|toute)\b|\buniquement\b|\bseulement\b|\bsans (?:son |lui )?"
                  r"(?:demander|accord|validation|go|feu vert)\b|\bà (?:éviter|proscrire)\b|\bn'(?:envoie|utilise|ajoute|accepte)\b|"
                  r"\bpriorit|\bnever\b|\balways\b|\bmust\b)")
BIO = re.compile(r"(?i)\b(est n[ée]e?\b|habite|vit (?:à|en|au|chez)|travaille (?:chez|à|comme|pour)|s'appelle|a \d+ ans|"
                 r"son (?:père|frère|fils|associé|ami)|sa (?:mère|sœur|fille|femme|compagne|famille)|ses (?:parents|enfants)|"
                 r"poss[èe]de|est (?:propriétaire|marié|né|originaire))")
# a one-off request is not a durable aim: « Monsieur demande… », « veut que W.Alter vérifie… », « veut un rapport »
ONE_OFF = re.compile(r"(?i)^\s*(?:Monsieur\s+)?(?:a\s+)?(?:re)?(?:demand|veut (?:que (?:W\.?Alter|Claude|l'agent|tu|on|"
                     r"ce|cette|le|la|les|l')\b|savoir|voir|comprendre|qu'on|un (?:exemple|rapport|résumé|audit|point|test)|"
                     r"une (?:liste|explication|vérification|réponse|analyse))|souhaite (?:savoir|voir)|aimerait savoir)")
ACTION = re.compile(r"(?i)\b(lancer?|lance|corrig|vérifi|ajout|supprim|install|test(?:er|e)\b|regard|envoi|expliqu|montr|"
                    r"donn|implément|commit|redémarr|relanc|rédig|prépar|analys|audit|compar|cherch|trouv|mesur|"
                    r"exécut|répar|reprend|termin|livr|publi|déploi)")
DURABLE = re.compile(r"(?i)(à (?:long )?terme|durablement|devien|puisse|capable|autonom|toujours|systématiquement|\bvise\b|"
                     r"ambition|apprendre|un jour|vision|de manière générale|en général|à l'avenir|désormais)")


@lru_cache(maxsize=50000)
def _normative(text: str) -> bool:
    return bool(NORM.search(text or ""))


@lru_cache(maxsize=50000)
def _technical(text: str) -> bool:
    return len(P.TECH.findall(P.SELON.sub("", text or ""))) >= 2


@lru_cache(maxsize=50000)
def _bio(text: str) -> bool:
    return bool(BIO.search(text or ""))


@lru_cache(maxsize=50000)
def one_off(text: str) -> bool:
    """A request for one piece of work, not a durable aim (its head asks for an action, nothing durable is said)."""
    t = text or ""
    return bool(ONE_OFF.search(t) or ACTION.search(t[:70])) and not DURABLE.search(t)

# « où en suis-je », « mon état (courant) », « ma situation », « ce que j'ai en cours », « mes engagements »
ME_HINT = re.compile(r"(?i)(o[uù] en suis[- ]je|o[uù] j'en suis|\bmon [ée]tat\b|\bma situation\b|"
                     r"(qu'est-ce que|ce que) j'ai en cours|\bmes (t[âa]ches|engagements|objectifs|r[èe]gles)\b|"
                     r"\b[ée]tat (courant )?personnel\b)")


def kind_of(key: str) -> str | None:
    """'owner' | 'now' | 'me' for a personal key, else None (a project)."""
    k = re.sub(r"[^a-z]", "", P._fold(key or "").replace("project:", ""))
    return "owner" if k in OWNER_KEYS else "now" if k in NOW_KEYS else "me" if k in BOTH_KEYS else None


def _allowed(max_privacy: str) -> list[str]:
    """Not the cloud ceiling: a cloud reader of these projections gets cloud_allowed rows only."""
    return ORDER_CLASSES[: ORDER_CLASSES.index(max_privacy) + 1] if max_privacy in ORDER_CLASSES else ["cloud_allowed"]


def _ttl_days() -> float:
    try:
        from . import organic
        return float((organic.settings().get("reconcile") or {}).get("state_ttl_days") or 7)
    except Exception:  # noqa: BLE001
        return 7.0


def _withheld(conn, at: datetime | None, allowed: list[str]) -> int:
    """How many of the owner's current items a reader of this class does not get (counted, never shown)."""
    if "local_only" in allowed:
        return 0
    return conn.execute(f"""select count(*) n from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and {P.SUBJ} = 'owner'
          and status in ('derived', 'verified') and (valid_to is null or valid_to > coalesce(%s, now()))
          and not (privacy_class = any(%s))""", (at, allowed)).fetchone()["n"]


# ───────────────────────────── Personnel ─────────────────────────────
def personal(*, at: datetime | str | None = None, max_privacy: str = "cloud_allowed", conn=None) -> dict:
    t0 = time.perf_counter()
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    now = at or datetime.now(timezone.utc)
    allowed = _allowed(max_privacy)
    stack = contextlib.ExitStack()
    if conn is None:
        conn = stack.enter_context(connection())
    with stack:
        rows = [r for r in P._items(conn, {"owner": "owner", "other": "other"}, at, allowed)
                if r["project"] == "owner" or r.get("dom") == "personal"]
        tasks = P._task_status(conn, rows)
        withheld = _withheld(conn, at, allowed)
    ttl = timedelta(days=_ttl_days())
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["kind"], []).append(r)
    owner = lambda r: r["epistemic"] == "stated_owner"                         # noqa: E731
    temporary = [r for r in rows if r.get("valid_to") and r["kind"] != "goal"]
    temp_ids = {r["item_id"] for r in temporary}
    # rules in force: what he said himself and still holds, durable (a task's working rule is not his rule)
    rules, prefs, described = [], [], []
    technical = 0
    for r in rows:
        if r["item_id"] in temp_ids or not owner(r) or r.get("scope") == "task" or r.get("dom") == "task":
            continue
        if r["kind"] in ("constraint", "correction") or (r["kind"] == "decision" and r["stage"] in P.IN_FORCE
                                                          | {"requested"}):
            if _normative(r["content"]) and not _bio(r["content"]):
                rules.append(r)
            elif _technical(r["content"]):
                technical += 1             # a technical detail filed as a rule: not his rule, counted
            else:
                described.append(r)        # a description (biographical, factual): with his facts, not his rules
        elif r["kind"] == "preference":
            prefs.append(r)
    # reaffirmed first (several sources), plain words before technical ones, the strongest kind, then the newest
    key = lambda r: (-(min(r.get("nsrc") or 1, 3)), _technical(r["content"]), RULE_ORDER.get(r["kind"], 9),  # noqa: E731
                     -r["from"].timestamp())
    rules.sort(key=key)
    prefs.sort(key=key)
    goals = P.goal_buckets(by.get("goal", []) + by.get("commitment", []), tasks, (), now)
    # his durable aims (« Monsieur veut que… »), taken up or not: shown with their real status, the newest first
    durable = [r for r in by.get("goal", []) if r.get("scope") != "task" and r.get("dom") != "task"
               and not P._is_test(r["content"]) and P.effective(r) == "open" and not P._last_step(r)]
    requests = [r for r in durable if one_off(r["content"])]       # one piece of work asked: not a durable aim
    aims = [P._line(r, effective=P.effective(r)) for r in sorted(
        (r for r in durable if not one_off(r["content"])), key=lambda r: -r["from"].timestamp())]
    facts, reverify = [], []
    for r in by.get("fact", []) + described:
        if r["item_id"] in temp_ids:
            continue
        transient = r.get("scope") in ("task", "until") or r.get("dom") == "task" or P._stateful(r["content"])
        if transient and now - r["from"] > ttl:
            reverify.append(P._line(r))
        elif r.get("scope") != "task" and r.get("dom") != "task":
            if _technical(r["content"]) and not _bio(r["content"]):
                technical += 1             # a technical detail of his work, not a fact about him
                continue
            old = now - r["from"] > FACT_FRESH and (r.get("nsrc") or 1) < 2 and r["epistemic"] != "verified"
            facts.append(P._line(r, weight=P.weight(r, (), now), old=old))
    facts.sort(key=lambda l: (l["old"], l["who"] not in ("vérifié", "Monsieur"), -l["weight"], -l["said"].timestamp()))
    reverify.sort(key=lambda l: -l["said"].timestamp())
    return {"key": "owner", "name": "Monsieur", "at": at, "count": len(rows), "withheld": withheld,
            "set_aside": {"technical": technical, "requests": len(requests)},
            "sections": {"rules": [P._line(r) for r in rules], "prefs": [P._line(r) for r in prefs],
                         "temporary": [P._line(r) for r in sorted(temporary, key=lambda r: r["valid_to"])],
                         "goals": goals, "aims": aims, "facts": facts, "reverify": reverify},
            "sources": [r["item_id"] for r in rows], "ttl_days": ttl.days,
            "watermark": max((r["created_at"] for r in rows), default=None),
            "ms": round((time.perf_counter() - t0) * 1000, 1)}


# ───────────────────────────── Situationnel ─────────────────────────────
def _ago(dt: datetime, now: datetime) -> str:
    s = (now - dt).total_seconds()
    if s < 3600:
        return f"il y a {max(1, round(s / 60))} min"
    if s < 86400 * 2:
        return f"il y a {round(s / 3600)} h"
    return f"le {P._d(dt)}"


def _place(allowed: list[str], now: datetime) -> dict:
    if "local_only" not in allowed:
        return {"status": "withheld"}
    from . import whereabouts
    return whereabouts.current(max_privacy="local_only")


def _agenda(conn, now: datetime, allowed: list[str]) -> dict:
    # bounds computed here: a literal range prunes the event partitions at planning time (now() would plan them all)
    rows = conn.execute("""select distinct on (coalesce(payload->>'event_id', event_id::text)) occurred_at, content,
                                  payload->'start' start, payload->>'location' location, privacy_class,
                                  coalesce(payload->>'calendar_id', '') cal
                           from core.events where source = 'calendar' and event_type = 'calendar.event'
                             and occurred_at >= %s and occurred_at < %s
                             and coalesce(payload->>'status', 'confirmed') <> 'cancelled'
                           order by coalesce(payload->>'event_id', event_id::text), ingested_at desc""",
                        (now - timedelta(hours=12), now + timedelta(days=60))).fetchall()
    rows = sorted(rows, key=lambda r: r["occurred_at"])
    # a subscribed calendar (holidays, week numbers…) gives landmarks, never an appointment of his (P2 fix, 19/11)
    marks = [r for r in rows if _subscribed(r["cal"])]
    rows = [r for r in rows if not _subscribed(r["cal"])]
    shown = [r for r in rows if r["privacy_class"] in allowed]
    inweek = lambda r: r["occurred_at"] < now + AGENDA and (r["occurred_at"] >= now or "date" in (r["start"] or {}))  # noqa: E731
    week = [r for r in shown if inweek(r)]
    nxt = None if week else next((r for r in shown if r["occurred_at"] >= now), None)
    holidays = [r for r in marks if "#holiday" in r["cal"] and inweek(r) and r["privacy_class"] in allowed]
    sync = conn.execute("select max(last_success_at) m from ingestion.connectors where source = 'calendar'").fetchone()
    return {"week": week, "next": nxt, "withheld": len(rows) - len(shown), "synced": sync["m"] if sync else None,
            "holidays": holidays, "landmarks": len(marks)}


def _subscribed(cal: str) -> bool:
    """Google's public calendars (holidays, week numbers, phases of the moon…): not the owner's agenda."""
    return cal.endswith("@group.v.calendar.google.com") or "#" in cal


def _tasks(limit: int = 8) -> list[dict]:
    try:
        from . import runs
        return runs.tasks_list(status=None, limit=limit, channels=["owner"])
    except Exception:  # noqa: BLE001 — the Run Plane is optional here
        return []


def _learned(conn, now: datetime, allowed: list[str]) -> dict:
    """The freshness of what memory knows about HIM (P2 fix, 19/11: never the volume ingested about everything): his
    newest knowledge, how much is new in LEARNED, and why it stops when it stops (the live extraction's gate and the
    conversations waiting). Counts over every class: a count is not a content."""
    r = conn.execute(f"""select max(created_at) last, count(*) filter (where created_at > %s) n,
                                count(*) filter (where created_at > %s and not (privacy_class = any(%s))) local_n
        from core.derived_items where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary'
          and status in ('derived', 'verified') and ({P.SUBJ} = 'owner' or attributes->>'domain' = 'personal')""",
                     (now - LEARNED, now - LEARNED, allowed)).fetchone()
    from . import extract2
    return {"last": r["last"], "n": r["n"], "local_n": r["local_n"], **extract2.live_status(conn)}


def _views(conn, now: datetime, allowed: list[str]) -> dict:
    from .flows import tz
    day = now.astimezone(tz()).date()
    keys = [f"period:day:{day.isoformat()}", f"period:week:{day.isocalendar()[0]}-W{day.isocalendar()[1]:02d}"]
    periods = conn.execute("""select v.view_key, v.privacy_class, x.content, x.built_at from views.view v
                              left join lateral (select content, built_at from views.version where view_key = v.view_key
                                                 and depth = 'index' order by version desc limit 1) x on true
                              where v.view_key = any(%s)""", (keys,)).fetchall()
    eps = conn.execute("""select view_key, title, status, privacy_class, last_at from views.view where kind = 'episode'
                          and status = 'active' and last_at > %s order by last_at desc""",
                       (now - EPISODES,)).fetchall()
    return {"periods": [dict(r) for r in periods], "episodes": [dict(r) for r in eps if r["privacy_class"] in allowed],
            "episodes_withheld": sum(r["privacy_class"] not in allowed for r in eps)}


def situation(*, max_privacy: str = "cloud_allowed", session: tuple[str, str] | None = None, conn=None) -> dict:
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc)
    allowed = _allowed(max_privacy)
    stack = contextlib.ExitStack()
    if conn is None:
        conn = stack.enter_context(connection())
    with stack:
        learned = P._side_pool().submit(lambda: P._with_conn(lambda c: _learned(c, now, allowed)))
        tasks = P._side_pool().submit(_tasks)
        out = {"key": "now", "name": "maintenant", "at": None, "now": now, "allowed": allowed,
               "place": _place(allowed, now), "agenda": _agenda(conn, now, allowed), "views": _views(conn, now, allowed)}
        out["learned"], out["tasks"] = learned.result(), tasks.result()
    out["working"] = None
    if session and session[1]:
        try:
            from . import working
            st = working.state(session[0], session[1],
                               audience="owner_local" if "local_only" in allowed else "cloud_model")
            if st["privacy_class"] in allowed:
                out["working"] = st["text"]
        except Exception:  # noqa: BLE001 — an addition
            pass
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out


# ───────────────────────────── rendering ─────────────────────────────
FLOOR = {"place": 1, "agenda": 2, "tasks": 3, "learned": 1, "views": 1, "working": 1,
         "rules": 4, "prefs": 2, "temporary": 2, "goals": 2, "aims": 2, "facts": 2, "reverify": 1}
ORDER_NOW = ("place", "agenda", "tasks", "working", "learned", "views")
ORDER_OWNER = ("rules", "temporary", "goals", "prefs", "aims", "facts", "reverify")


def _fit(blocks: dict, order: tuple, budget: int) -> tuple[list[str], list[str]]:
    """The same three rounds as the project projection: one line each, then the floors, then the rest."""
    take = {k: 0 for k in blocks}
    cost = {k: P._tokens(f"### {blocks[k][0]}") + sum(P._tokens(t) for t in blocks[k][2])
            for k in blocks if blocks[k][1]}
    for rnd in ("one", "floor", "more"):
        for k in order:
            if k not in cost:
                continue
            lines = blocks[k][1]
            stop = {"one": 1, "floor": FLOOR.get(k, 1)}.get(rnd, len(lines))
            while take[k] < min(stop, len(lines)):
                t = P._tokens(lines[take[k]][0]) + (cost[k] if take[k] == 0 else 0)
                if t > budget:
                    break
                budget -= t
                take[k] += 1
    out, shown = [], []
    for k in order:
        if k not in cost or not take[k]:
            continue
        title, lines, always = blocks[k]
        out.append(f"### {title}")
        for ln, i in lines[:take[k]]:
            out.append(ln)
            if i:
                shown.append(i)
        out += always
    return out, shown


def _when(dt: datetime, allday: bool) -> str:
    from .flows import tz
    d = dt.astimezone(tz())
    days = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
    return f"{days[d.weekday()]} {d:%d/%m}" + ("" if allday else f" {d:%H:%M}")


def blocks_now(s: dict, skip: tuple = ()) -> dict:
    now, b = s["now"], {}
    pl = s["place"]
    if pl.get("status") == "withheld":
        line = ("- donnée locale, non transmise à un modèle cloud (le bloc position de Context la sert quand la "
                "question en dépend)")
    elif pl.get("status") == "absent":
        line = "- aucun relevé de position"
    else:
        where = (("au domicile" if pl["place"]["home"] else f"à « {pl['place']['name']} »") if pl.get("place")
                 else "hors des lieux connus" + (f", à {round(pl['home']['distance_m'] / 1000, 1)} km du domicile"
                                                if pl.get("home") and pl["home"].get("distance_m") else ""))
        old = " — ancien : il a pu bouger" if pl["status"] == "old" else ""
        line = f"- {where} (relevé {_ago(datetime.fromisoformat(pl['at']), now)}){old}"
    b["place"] = ("Lieu", [(line, None)], [])
    ag = s["agenda"]
    al = [(f"- {_when(r['occurred_at'], 'date' in (r['start'] or {}))} : {P._short(r['content'] or '(sans titre)', 70)}"
           + (f" ({P._short(r['location'], 30)})" if r.get("location") else ""), None) for r in ag["week"]]
    if ag["next"]:
        r = ag["next"]
        al.append((f"- rien dans les 7 jours ; prochain : {_when(r['occurred_at'], 'date' in (r['start'] or {}))} : "
                   f"{P._short(r['content'] or '(sans titre)', 70)}", None))
    tail = [f"- agenda synchronisé {_ago(ag['synced'], now)}"] if ag.get("synced") else ["- agenda non synchronisé"]
    if ag["withheld"]:
        tail.append(f"- aussi : {ag['withheld']} rendez-vous locaux, non transmis")
    if ag.get("holidays"):
        tail.append("- jour férié : " + ", ".join(f"{_when(r['occurred_at'], True)} ({P._short(r['content'] or '', 30)})"
                                                  for r in ag["holidays"][:3]))
    b["agenda"] = ("Agenda (7 jours)", al or [("- aucun rendez-vous dans les 7 jours", None)], tail)
    if "tasks" not in skip:
        fresh_l, stale_l = [], []
        for t in s["tasks"]:
            at = t.get("updated_at")
            at = datetime.fromisoformat(at) if isinstance(at, str) else at
            if at and at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if at and now - at <= P.ACTIVE:
                label = {"open": "en cours", "suspended": "suspendu"}.get(t["status"], t["status"])
                prog = f" — {P._short(t['progress'], 60)}" if t.get("progress") else ""
                fresh_l.append((f"- [{label}] « {P._short(t.get('goal') or '', 90)} » (activité {_ago(at, now)}){prog}",
                                None))
            else:
                stale_l.append((f"- [sans nouvelle depuis le {P._d(at) if at else '?'}, statut inconnu] "
                                f"« {P._short(t.get('goal') or '', 80)} »", None))
        tl = fresh_l + stale_l[:2]
        tail = [f"- aussi : {len(stale_l) - 2} objectifs ouverts sans nouvelle (statut inconnu)"] if len(stale_l) > 2 else []
        b["tasks"] = ("Travaux ouverts (Run Plane)", tl or [("- aucun objectif ouvert", None)], tail)
    if s.get("working"):
        w = s["working"].split("\n", 1)[1] if s["working"].startswith("## ") else s["working"]
        b["working"] = ("Fil en cours", [(x, None) for x in w.splitlines() if x.strip()][:8], [])
    b["learned"] = ("Fraîcheur de la mémoire personnelle", learned_lines(s["learned"], now), [])
    v = s["views"]
    vl = []
    for p in v["periods"]:
        label = "Journée" if ":day:" in p["view_key"] else "Semaine"
        if p["privacy_class"] in _allowed("cloud_allowed") and p.get("content"):
            old = p.get("built_at") and now - p["built_at"] > VIEW_FRESH
            vl.append((f"- {label} : {P._short(p['content'], 110)} (vue du {P._d(p['built_at'])}"
                       + (", ancienne : non reconstruite depuis" if old else "") + ")", None))
        else:
            vl.append((f"- {label} : vue locale `{p['view_key']}` (non transmise ; memory_view avec un lecteur local)",
                       None))
    for e in v["episodes"][:2]:
        vl.append((f"- épisode : « {P._short(e['title'] or '', 80)} » ({P._d(e['last_at'])})", None))
    tail = [f"- aussi : {v['episodes_withheld']} épisodes récents locaux, non transmis"] if v["episodes_withheld"] else []
    if vl or tail:
        b["views"] = ("Période et épisodes", vl, tail)
    return b


def learned_lines(le: dict, now: datetime) -> list[tuple[str, None]]:
    """His newest knowledge, then the delay and its cause: the gate (quota, pause), what waits, when it resumes."""
    out = []
    last = le.get("last")
    if le.get("n"):
        out.append(f"- {le['n']} connaissances personnelles nouvelles en {LEARNED.days} jours"
                   + (f" (dont {le['local_n']} locales)" if le.get("local_n") else "")
                   + f", la dernière {_ago(last, now)}")
    elif last:
        out.append(f"- dernière connaissance personnelle : {P._d(last)} — rien de nouveau depuis")
    g, w = le.get("gate") or {}, le.get("waiting") or {}
    since = _dt(g.get("since"))
    if g.get("state") == "provider_limit":    # a real refusal of every route (no percentage gate, 2026-11-20)
        until = _dt(g.get("until"))
        out.append("- extraction en attente : limite réelle du fournisseur de modèles"
                   + (f" depuis {_ago(since, now).replace("il y a ", "")}" if since else "")
                   + (f" ; reprise automatique le {_when(until, False)}" if until else " ; reprise automatique"))
    elif g.get("state") == "paused":
        out.append("- extraction en pause (décision de Monsieur)" + (f" depuis {_ago(since, now).replace("il y a ", "")}" if since else ""))
    seen = _dt(g.get("seen"))
    if seen and now - seen > timedelta(minutes=15):
        out.append(f"- l'extraction n'a pas tourné depuis {_ago(seen, now).replace("il y a ", "")} (service à vérifier)")
    if w.get("threads"):
        out.append(f"- {w['threads']} conversations en attente d'extraction"
                   + (f", la plus ancienne {_ago(w['oldest'], now)}" if w.get("oldest") else "") + " (rien n'est perdu)")
    return [(x, None) for x in out] or [("- aucune connaissance personnelle", None)]


def _dt(v) -> datetime | None:
    if not v or v == "None":
        return None
    if isinstance(v, datetime):
        return v
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def blocks_owner(p: dict, exclude: set | None = None) -> dict:
    s, b, ex = p["sections"], {}, exclude or set()
    fmt = lambda l, n=110: f"- {P._fmt(l, n)}"                                 # noqa: E731
    keep = lambda ls: [l for l in ls if l["id"] not in ex]                     # noqa: E731
    rules = keep(s["rules"])
    b["rules"] = ("Règles en vigueur (dites par Monsieur ; les plus réaffirmées d'abord)",
                  [(fmt(l), l["id"]) for l in rules[:10]],
                  [f"- aussi : {len(rules) - 10} autres règles en vigueur (memory_search)"] if len(rules) > 10 else [])
    prefs = keep(s["prefs"])
    b["prefs"] = ("Préférences", [(fmt(l, 100), l["id"]) for l in prefs[:6]],
                  [f"- aussi : {len(prefs) - 6} autres préférences"] if len(prefs) > 6 else [])
    b["temporary"] = ("Valable jusqu'à une date", [(fmt(l), l["id"]) for l in keep(s["temporary"])[:5]], [])
    g = s["goals"]
    gl = [(f"- [bloqué] {P._fmt(l, 95)}", l["id"]) for l in g["blocked"][:3]]
    gl += [(f"- [en cours] {P._fmt(l, 95)}" + (f" — dernière étape {P._d(l['step_at'])}" if l.get("step") else ""),
            l["id"]) for l in g["in_progress"][:4]]
    gl += [(f"- [réalisé, vérifié] {P._fmt(l, 95)}", l["id"]) for l in g["done"][:2]]
    gl += [(f"- [annoncé terminé, non vérifié] {P._fmt(l, 95)}", l["id"]) for l in g["claimed"][:2]]
    gl += [(f"- [engagement pris, pas encore commencé] {P._fmt(l, 95)}", l["id"]) for l in g["open"][:3]]
    gl += [(f"- [sans nouvelle depuis le {P._d(l['step_at'] or l['said'])}, statut inconnu] {P._fmt(l, 95)}", l["id"])
           for l in g["stale"][:2]]
    b["goals"] = ("Objectifs et engagements", gl,
                  [f"- aussi : {len(g['stale'])} sans nouvelle, {g['requested'] + g['not_followed']} demandes sans "
                   f"trace d'exécution (statut inconnu)" + (f", {g['tests']} tests ignorés" if g["tests"] else "")])
    aims = [l for l in keep(s["aims"]) if l["id"] not in {x for _, x in gl}]
    b["aims"] = ("Ce que Monsieur a dit vouloir (sans trace d'exécution : statut inconnu)",
                 [(fmt(l, 100), l["id"]) for l in aims[:4]], [])
    b["facts"] = ("Faits personnels (les anciens non reconfirmés en dernier)",
                  [(fmt(l) + (" — non reconfirmé depuis" if l.get("old") else ""), l["id"]) for l in keep(s["facts"])[:4]],
                  [f"- aussi : {len(s['facts']) - 4} autres faits"] if len(s["facts"]) > 4 else [])
    sa = p.get("set_aside") or {}
    if sa.get("technical") or sa.get("requests"):
        b["facts"][2].append(f"- écartés de cet état : {sa.get('technical', 0)} détails techniques, "
                             f"{sa.get('requests', 0)} demandes ponctuelles (memory_search)")
    rv = s["reverify"]
    b["reverify"] = (f"À revérifier (états passagers de plus de {p['ttl_days']} jours)",
                     [(f"- {P._fmt(l, 100)}", l["id"]) for l in keep(rv)[:3]],
                     [f"- aussi : {len(rv) - 3} autres à revérifier"] if len(rv) > 3 else [])
    return b


def render(own: dict | None, now: dict | None, max_tokens: int = 900, exclude: set | None = None,
           skip: tuple = ()) -> tuple[str, list[str]]:
    """Situation first (where, agenda, open work), then the personal state; each within the shared budget."""
    head = []
    if now:
        from .flows import tz
        head.append(f"Situation de Monsieur — {now['now'].astimezone(tz()):%d/%m %H:%M} (chaque ligne avec sa "
                    f"fraîcheur" + ("" if "local_only" in now.get("allowed", []) else
                                    " ; aucune donnée locale vers un modèle cloud") + ").")
    if own:
        when = f"au {P._d(own['at'])}" if own.get("at") else "maintenant"
        head.append(f"État personnel de Monsieur — {when} ({own['count']} connaissances valables"
                    + (f", {own['withheld']} locales non transmises" if own.get("withheld") else "")
                    + " ; rien d'expiré n'est présenté comme courant).")
    blocks, order = {}, ()
    if now:
        blocks.update(blocks_now(now, skip))
        order += ORDER_NOW
    if own:
        blocks.update(blocks_owner(own, exclude))
        order += ORDER_OWNER
    foot = ("Plus : memory_view(key=\"owner\"|\"now\", depth=\"state\") ; détail d'une ligne : memory_search ou "
            "l'historique de son identifiant.")
    budget = max_tokens - P._tokens("\n".join(head)) - P._tokens(foot)
    body, shown = _fit(blocks, order, budget)
    return "\n".join(head + body + [foot]), list(dict.fromkeys(shown))


def read(q: dict, session: tuple[str, str] | None = None) -> dict:
    """memory_view depth="state" for key owner | now | me (MemoryViewQuery v1 shape)."""
    k = kind_of(q["key"])
    mp = q.get("privacy") or "cloud_allowed"
    own = personal(at=q.get("at"), max_privacy=mp) if k in ("owner", "me") else None
    now = situation(max_privacy=mp, session=session) if k in ("now", "me") and not q.get("at") else None
    if k == "now" and q.get("at"):
        return {"error": "la situation n'existe que maintenant ; l'état personnel à une date : key=owner, at=…"}
    text, shown = render(own, now, int(q.get("max_tokens") or 900))
    return {"key": k, "depth": "state", "version": None, "content": text, "built_at": datetime.now(timezone.utc),
            "watermark": (own or {}).get("watermark"), "stale": False, "sources": shown, "deeper": ["history"],
            "at": q.get("at"), "ms": round((own or {}).get("ms", 0) + (now or {}).get("ms", 0), 1)}


def check(*, at: str | None = None, limit_ms: float = 50.0) -> dict:
    """Invariants on real data: nothing expired or replaced cited as current, nothing local cited for a cloud reader,
    every cited item the owner's, and each projection under `limit_ms` once warm."""
    personal(at=at)
    own = personal(at=at)
    now = situation() if not at else None
    if now:
        now = situation()
    text, shown = render(own, now)
    problems = []
    when = own["at"] or datetime.now(timezone.utc)
    with connection() as conn:
        rows = conn.execute("""select item_id::text id, status, valid_to, privacy_class, attributes->>'subject' subject,
                                      attributes->>'domain' dom from core.derived_items where item_id = any(%s::uuid[])""",
                            (shown,)).fetchall()
    for r in rows:
        if r["valid_to"] and r["valid_to"] <= when:
            problems.append(f"{r['id'][:8]} expiré le {P._d(r['valid_to'])} mais cité")
        if own["at"] is None and r["status"] not in ("derived", "verified"):
            problems.append(f"{r['id'][:8]} {r['status']} cité comme courant")
        if r["privacy_class"] != "cloud_allowed":
            problems.append(f"{r['id'][:8]} {r['privacy_class']} cité pour un lecteur cloud")
        if P.knowledge.subject_key(r["subject"] or "") != "owner" and r["dom"] != "personal":
            problems.append(f"{r['id'][:8]} sujet {r['subject']} hors de Monsieur")
    for name, ms in (("owner", own["ms"]), ("now", (now or {}).get("ms", 0))):
        if ms > limit_ms:
            problems.append(f"latence {name} {ms} ms > {limit_ms} ms")
    return {"key": "me", "ok": not problems, "ms": own["ms"], "now_ms": (now or {}).get("ms"), "items": own["count"],
            "withheld": own["withheld"], "cited": len(shown), "tokens": P._tokens(text), "problems": problems}
