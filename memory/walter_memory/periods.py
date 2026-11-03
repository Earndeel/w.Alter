"""Period syntheses (Memory V1 P1.6): a day, a week, a month — rebuilt from what is true, never from a lower level's text.

Each period is a view (kind period): `period:day:2026-11-03`, `period:week:2026-W45`, `period:month:2026-11` (the
owner's local time zone, organic.toml [periods] tz). Every level reads the knowledge, episodes and measures of ITS
window directly:
  work          sessions with W.Alter's agents per subject (flows.work_sessions)
  changes       V1 knowledge established in the window: decisions (with their stage), rules, corrections, goals; an item
                replaced since is shown with its fate ("remplacé le …") — the history stays, the current state is clear
  commitments   opened / closed in the window, still open at its end
  agenda        appointments (calendar)
  episodes      the episodes of the window, at their own status (hypotheses stay hypotheses)
  measures      local variant only: places visited, conversation bursts and the people they were with
Two projections: `…` from cloud_allowed inputs only, `…:local` from everything (local_only by its evidence). A version
is rebuilt only when its inputs changed (inputs_hash); a correction marks the views that list the corrected item stale
(views.evidence, backwards), and their parents (day → week → month) through `view` evidence — only that path is rebuilt.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone

from . import privacy
from .db import connection
from .flows import tz

log = logging.getLogger("walter.periods")
BUILDER = "periods@1"
TITLES = {"decision": "Décision", "constraint": "Règle", "preference": "Préférence", "correction": "Correction",
          "goal": "Objectif", "commitment": "Engagement", "fact": "Fait"}
STAGE = {"requested": "demandé", "proposed": "proposé", "decided": "validé", "executed": "exécution rapportée",
         "verified": "vérifié", "abandoned": "abandonné", "open": "ouvert", "done": "tenu", "stated": ""}


def window(kind: str, d: date) -> tuple[datetime, datetime, str]:
    z = tz()
    if kind == "day":
        start = datetime.combine(d, dtime(0), z)
        return start, start + timedelta(days=1), f"period:day:{d.isoformat()}"
    if kind == "week":
        monday = d - timedelta(days=d.weekday())
        start = datetime.combine(monday, dtime(0), z)
        y, w, _ = monday.isocalendar()
        return start, start + timedelta(days=7), f"period:week:{y}-W{w:02d}"
    first = d.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return datetime.combine(first, dtime(0), z), datetime.combine(nxt, dtime(0), z), f"period:month:{first:%Y-%m}"


def title_of(kind: str, start: datetime, end: datetime) -> str:
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    if kind == "day":
        return f"Journée du {days[start.weekday()]} {start:%d/%m/%Y}"
    if kind == "week":
        return f"Semaine du {start:%d/%m} au {(end - timedelta(days=1)):%d/%m/%Y}"
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre"]
    return f"Mois de {months[start.month - 1]} {start.year}"


def inputs(conn, start: datetime, end: datetime, allowed: list[str]) -> dict:
    know = conn.execute("""select d.item_id::text id, d.kind, d.content, d.status, d.stage, d.scope, d.epistemic, d.valid_to,
                                  d.privacy_class, coalesce(d.valid_from, d.created_at) at,
                                  d.attributes->>'superseded_by' superseded_by, d.subject_entity_ids,
                                  case when n.privacy_class = any(%s) then n.content end replaced_by,
                                  coalesce(n.valid_from, n.created_at) replaced_at
                           from core.derived_items d
                           left join core.derived_items n on n.item_id::text = d.attributes->>'superseded_by'
                           where d.generation = 'g1' and d.derived_by = 'l3.extract'
                             and d.kind = any(%s) and coalesce(d.valid_from, d.created_at) >= %s
                             and coalesce(d.valid_from, d.created_at) < %s and d.privacy_class = any(%s)
                             and d.status in ('derived', 'verified', 'superseded')
                           order by at""", (allowed, list(TITLES), start, end, allowed)).fetchall()
    obs = conn.execute("""select item_id::text id, kind, content, attributes, privacy_class, valid_from at
                          from core.derived_items where generation = 'g1' and status = 'derived'
                            and kind in ('work_session', 'appointment', 'visit', 'conversation')
                            and valid_from >= %s and valid_from < %s and privacy_class = any(%s)
                          order by valid_from""", (start, end, allowed)).fetchall()
    eps = conn.execute("""select v.view_key, v.title, v.epistemic, v.starts_at, v.privacy_class from views.view v
                          where v.kind = 'episode' and v.generation = 'g1' and v.status = 'active'
                            and v.starts_at >= %s and v.starts_at < %s and v.privacy_class = any(%s)
                            and (v.view_key like %s) = %s
                          order by v.starts_at""", (start, end, allowed, "%:local", "local_only" in allowed)).fetchall()
    open_c = conn.execute("""select item_id::text id, content, coalesce(valid_from, created_at) at, privacy_class
                             from core.derived_items where generation = 'g1' and derived_by = 'l3.extract'
                               and kind = 'commitment' and status in ('derived','verified') and coalesce(stage,'open') = 'open'
                               and coalesce(valid_from, created_at) < %s and privacy_class = any(%s)
                               and (valid_to is null or valid_to > %s)""", (end, allowed, end)).fetchall()
    names = {}
    ids = {str(e) for k in know for e in k["subject_entity_ids"] or []}
    if ids:
        names = {r["id"]: r["canonical_name"] for r in conn.execute(
            "select entity_id::text id, canonical_name from core.entities where entity_id = any(%s::uuid[])", (list(ids),))}
    return {"knowledge": know, "observations": obs, "episodes": eps, "open_commitments": open_c, "names": names}


def render(kind: str, start: datetime, end: datetime, data: dict, *, local: bool) -> dict:
    z = tz()
    lines = [f"# {title_of(kind, start, end)}", ""]
    obs = data["observations"]
    work = [o for o in obs if o["kind"] == "work_session"]
    by_subject = defaultdict(lambda: {"owner": 0, "first": None, "last": None, "runtimes": set()})
    for w in work:
        a = w["attributes"]
        title = w["content"].split("sujet « ")[-1].rstrip("»").strip() if "sujet « " in w["content"] else "(sans sujet)"
        s = by_subject[title]
        s["owner"] += int(a.get("owner_messages") or 0)
        s["runtimes"].add(a.get("source"))
        st, en = datetime.fromisoformat(a["start"]), datetime.fromisoformat(a["end"])
        s["first"] = min(filter(None, [s["first"], st]))
        s["last"] = max(filter(None, [s["last"], en]))
    if by_subject:
        lines.append("## Travail avec W.Alter")
        for t, s in sorted(by_subject.items(), key=lambda x: -x[1]["owner"])[:12]:
            span = f"{s['first'].astimezone(z):%d/%m %H:%M}–{s['last'].astimezone(z):%H:%M}" if kind == "day" else \
                f"{s['first'].astimezone(z):%d/%m}→{s['last'].astimezone(z):%d/%m}"
            lines.append(f"- {t} : {s['owner']} messages de Monsieur ({', '.join(sorted(filter(None, s['runtimes'])))}, {span})")
        lines.append("")
    know = data["knowledge"]
    compact_lines: list[str] = []          # the overview's version of this section: a few per project, compacted
    if know:
        from .working import _compact
        lines.append("## Décisions, règles et changements")
        compact_lines.append("## Décisions, règles et changements")
        limit = {"day": 30, "week": 40, "month": 30}[kind]
        main = [k for k in know if k["kind"] in ("decision", "correction", "constraint", "preference", "goal")]
        if kind != "day":     # longer windows: the owner's decisions and rules first, the rest counted
            main = [k for k in main if k["epistemic"] == "stated_owner"] or main
        by_proj = defaultdict(list)
        for k in main:
            proj = next((data["names"].get(str(e)) for e in k["subject_entity_ids"] or [] if data["names"].get(str(e))), "")
            by_proj[proj].append(k)
        shown = 0
        for proj, items in sorted(by_proj.items(), key=lambda x: -len(x[1])):
            if proj:
                lines.append(f"### {proj}")
            rank = sorted(items, key=lambda k: (k["status"] == "superseded", k["kind"] != "decision" or k["stage"] != "decided",
                                                k["kind"] != "correction",
                                                -k["at"].timestamp()))
            top = rank[:4]
            compact_lines.append(f"- {proj or 'Divers'} ({len(items)}) :")
            for k in top:
                fate = ""
                if k["status"] == "superseded":
                    fate = " → remplacé" + (f" le {k['replaced_at'].astimezone(z):%d/%m} : {_compact(k['replaced_by'], k['superseded_by'] or '')}"
                                            if k["replaced_by"] else "")
                compact_lines.append(f"  - {TITLES[k['kind']]} : {_compact(k['content'], k['id'])}{fate}")
            for k in items:
                if shown >= limit:
                    break
                fate = ""
                if k["status"] == "superseded":
                    fate = " → remplacé depuis" + (f" (le {k['replaced_at'].astimezone(z):%d/%m} : {k['replaced_by']} "
                                                   f"[{k['superseded_by'][:8]}])" if k["replaced_by"] else
                                                   f" (par {k['superseded_by'][:8]})" if k["superseded_by"] else "")
                elif k["valid_to"] and k["valid_to"] <= datetime.now(timezone.utc):
                    fate = " → n'est plus en vigueur"
                stage = STAGE.get(k["stage"] or "", "")
                lines.append(f"- [{k['at'].astimezone(z):%d/%m %H:%M}] {TITLES[k['kind']]}{', ' + stage if stage else ''} : "
                             f"{k['content']}{fate} [{k['id'][:8]}]")
                shown += 1
        rest = len(know) - shown
        if rest > 0:
            c = Counter(k["kind"] for k in know)
            lines.append(f"- (+{rest} autres éléments : {', '.join(f'{n} {TITLES[x].lower()}' for x, n in c.items())} ; "
                         f"memory_view {kind} details)")
        lines.append("")
        compact_lines.append("")
    new_c = [k for k in know if k["kind"] == "commitment"]
    if new_c or data["open_commitments"]:
        lines.append("## Engagements")
        for k in new_c:
            lines.append(f"- pris : {k['content']} ({STAGE.get(k['stage'] or 'open', '')}) [{k['id'][:8]}]")
        if data["open_commitments"]:
            lines.append(f"- encore ouverts en fin de période : {len(data['open_commitments'])}")
            for c in data["open_commitments"][:5]:
                lines.append(f"  - {c['content']} [{c['id'][:8]}]")
        lines.append("")
    appts = [o for o in obs if o["kind"] == "appointment"]
    if appts:
        lines.append("## Agenda")
        lines += [f"- {o['content']}" for o in appts[:15]]
        lines.append("")
    if data["episodes"]:
        lines.append("## Épisodes (statut de chaque hypothèse conservé)")
        lines += [f"- [{e['view_key']}] {e['title']} ({e['epistemic']})" for e in data["episodes"][:15]]
        lines.append("")
    visits = [o for o in obs if o["kind"] == "visit"]          # only in the local projection (local_only evidence)
    convs = [o for o in obs if o["kind"] == "conversation"]    # also in the cloud one when messaging may be read there
    if local or convs:
        if visits:
            lines.append("## Lieux (GPS, calculé sur la VM)")
            if kind == "day":
                lines += [f"- {o['content']}" for o in visits[:20]]
            else:
                c = Counter(o["content"].split("« ")[1].split(" »")[0] for o in visits if "« " in o["content"])
                lines += [f"- {p} : {n} présence(s)" for p, n in c.most_common(10)]
            lines.append("")
        if convs:
            people = Counter()
            for o in convs:
                for n in o["content"].split(" ; avec ")[-1].split(", ") if " ; avec " in o["content"] else []:
                    people[n] += 1
            lines.append("## Échanges (messageries)")
            lines.append(f"- {len(convs)} conversations, {sum(int(o['attributes'].get('messages') or 0) for o in convs)} "
                         f"messages dont {sum(int(o['attributes'].get('owner_messages') or 0) for o in convs)} de Monsieur")
            if people:
                lines.append("- avec : " + ", ".join(f"{p} ({n})" for p, n in people.most_common(10)))
            lines.append("")
    if len(lines) <= 2:
        lines.append("(rien d'enregistré sur cette période)")
    details = "\n".join(lines)
    # overview: the same sections, the knowledge one replaced by its compact form (budgeted, never silent)
    head, sep = [], "## Décisions, règles et changements"
    if sep in lines:
        i = lines.index(sep)
        j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
        head = lines[:i] + compact_lines + lines[j:]
    overview = _overview(head or lines)
    decided = sum(1 for k in know if k["kind"] == "decision" and k["stage"] == "decided" and k["status"] != "superseded")
    index = (f"{title_of(kind, start, end)} — {len(work)} sessions de travail, {decided} décisions validées, "
             f"{len(data['episodes'])} épisodes")
    return {"index": index, "overview": overview, "details": details}


def _overview(lines: list[str], budget_chars: int = 2400, per_section: int = 4) -> str:
    """Every section keeps its heading and its first lines (a period is work, decisions, places, people alike), then
    the remaining budget goes to the rest in order; what is left out is counted, never silent."""
    sections, cur = [], []
    for l in lines:
        if l.startswith("## ") and cur:
            sections.append(cur); cur = []
        cur.append(l)
    if cur:
        sections.append(cur)
    keep = [s[:1 + per_section] for s in sections]
    used = sum(len(l) for s in keep for l in s)
    for k, s in enumerate(sections):
        for l in s[1 + per_section:]:
            if used + len(l) > budget_chars:
                break
            keep[k].append(l); used += len(l)
    skipped = sum(len(s) for s in sections) - sum(len(s) for s in keep)
    out = [l for s in keep for l in s]
    if skipped:
        out.append(f"(+{skipped} lignes : profondeur details)")
    return "\n".join(out)


def build(kind: str, d: date, *, force: bool = False) -> dict:
    from .consolidate import set_embedding
    start, end, key = window(kind, d)
    out = {}
    for variant in ("cloud", "local"):
        allowed = privacy.allowed_classes("cloud_allowed" if variant == "cloud" else "local_only")
        vkey = key + (":local" if variant == "local" else "")
        with connection() as conn:
            data = inputs(conn, start, end, allowed)
            refs = [k["id"] for k in data["knowledge"]] + [o["id"] for o in data["observations"]] + \
                   [c["id"] for c in data["open_commitments"]]
            sig = sorted((k["id"], k["status"], str(k["valid_to"]), k["stage"] or "", k["replaced_by"] or "")
                         for k in data["knowledge"])
            h = hashlib.sha256(json.dumps([sig, sorted(refs), [(e["view_key"], e["title"], e["epistemic"])
                                                              for e in data["episodes"]]], default=str).encode()).hexdigest()[:20]
            last = conn.execute("""select inputs_hash, stale_since from views.version where view_key = %s and depth = 'overview'
                                   order by version desc limit 1""", (vkey,)).fetchone()
            if last and last["inputs_hash"] == h and not last["stale_since"] and not force:
                out[variant] = {"key": vkey, "rebuilt": False}
                continue
            texts = render(kind, start, end, data, local=variant == "local" or privacy.cloud_readable("local_only"))
            conn.execute("""insert into views.view (view_key, domain, horizon, title, status, generation, kind, starts_at, ends_at,
                                tz, attributes, privacy_class, first_at, last_at)
                            values (%s, 'activities', %s, %s, 'active', 'g1', 'period', %s, %s, %s, %s, 'cloud_allowed', %s, %s)
                            on conflict (view_key) do update set updated_at = now(), title = excluded.title""",
                         (vkey, {"day": "day", "week": "medium", "month": "long"}[kind], title_of(kind, start, end), start,
                          end, str(tz()), json.dumps({"period": kind, "variant": variant, "builder": BUILDER}), start, end))
            classes = {k["id"]: k["privacy_class"] for k in data["knowledge"]} | \
                      {o["id"]: o["privacy_class"] for o in data["observations"]} | \
                      {c["id"]: c["privacy_class"] for c in data["open_commitments"]}
            conn.execute("delete from views.evidence where view_key = %s and added_by = %s and not (ref_id = any(%s))",
                         (vkey, BUILDER, refs + [e["view_key"] for e in data["episodes"]]))
            for rid, cls in classes.items():
                conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                                values (%s, 'derived', %s, 'contains', %s, %s) on conflict do nothing""", (vkey, rid, cls, BUILDER))
            for e in data["episodes"]:
                conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                                values (%s, 'view', %s, 'contains', %s, %s) on conflict do nothing""",
                             (vkey, e["view_key"], e["privacy_class"], BUILDER))
            if kind != "day":     # the lower periods are an index of this one (and their staleness reaches it)
                d0 = start.date()
                subs = [window("day", d0 + timedelta(days=k))[2] for k in range((end - start).days)] if kind == "week" \
                    else sorted({window("week", d0 + timedelta(days=k))[2] for k in range((end - start).days)})
                for s in subs:
                    s = s + (":local" if variant == "local" else "")
                    if conn.execute("select 1 from views.view where view_key = %s", (s,)).fetchone():
                        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                                        values (%s, 'view', %s, 'index', %s, %s) on conflict do nothing""",
                                     (vkey, s, "local_only" if variant == "local" else "cloud_allowed", BUILDER))
            vclass = conn.execute("select privacy_class from views.view where view_key = %s", (vkey,)).fetchone()["privacy_class"]
            for depth, content in texts.items():
                conn.execute("""insert into views.version (view_key, depth, version, content, source_refs, watermark, builder,
                                    privacy_class, inputs_hash)
                                values (%s, %s, coalesce((select max(version) from views.version where view_key = %s
                                        and depth = %s), 0) + 1, %s, %s, now(), %s, %s, %s)""",
                             (vkey, depth, vkey, depth, content, json.dumps({"refs": len(refs)}), BUILDER, vclass, h))
            set_embedding(conn, vkey, texts["index"] + "\n" + texts["overview"][:1500])
            conn.execute("insert into views.ledger (view_key, action, detail) values (%s, 'rebuilt', %s)",
                         (vkey, json.dumps({"builder": BUILDER, "refs": len(refs), "privacy_class": vclass})))
            out[variant] = {"key": vkey, "rebuilt": True, "refs": len(refs), "privacy_class": vclass,
                            "tokens": len(texts["overview"]) // 4}
    return out


def stale_keys(conn) -> list[str]:
    return [r["view_key"] for r in conn.execute("""
        select distinct v.view_key from views.view v join views.version x on x.view_key = v.view_key
        where v.kind = 'period' and x.stale_since is not null
          and x.version = (select max(version) from views.version y where y.view_key = x.view_key and y.depth = x.depth)""")]


def _parse(key: str) -> tuple[str, date]:
    _, kind, label = key.split(":")[:3]
    if kind == "day":
        return kind, date.fromisoformat(label)
    if kind == "week":
        y, w = label.split("-W")
        return kind, date.fromisocalendar(int(y), int(w), 1)
    return kind, date.fromisoformat(label + "-01")


def tick(days: int = 2) -> dict:
    """Rebuild today and the recent days (inputs_hash: nothing if unchanged), their week and month, and every stale
    period (a correction anywhere in time)."""
    z = tz()
    today = datetime.now(timezone.utc).astimezone(z).date()
    todo = {("day", today - timedelta(days=k)) for k in range(days)}
    todo |= {("week", d) for _, d in list(todo)} | {("month", d) for _, d in list(todo)}
    with connection() as conn:
        todo |= {_parse(k.removesuffix(":local")) for k in stale_keys(conn)}
    order = {"day": 0, "week": 1, "month": 2}
    built = 0
    for kind, d in sorted(todo, key=lambda x: (order[x[0]], x[1])):
        try:
            r = build(kind, d)
            built += sum(1 for v in r.values() if v.get("rebuilt"))
        except Exception:
            log.exception("period %s %s failed", kind, d)
    return {"periods": len(todo), "rebuilt": built}
