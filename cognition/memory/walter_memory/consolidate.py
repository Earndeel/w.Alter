"""Consolidated views rebuilt from current knowledge and evidence (Memory V1 P1.2).

A subject view (`views.view`, kind subject) is no longer the previous card plus the last exchange: every version is
rebuilt from what is true now — the current V1 knowledge (g1) of the threads attached to the subject — with its
evidence recorded in `views.evidence`. Nothing is carried over from a previous text, so nothing drifts and nothing
disappears because a summary dropped it.

  key            g1 views mirror the subjects the live attachment engine maintains (views.member): g1:<subject>
                 (cloud projection: built from cloud_allowed evidence only) and g1:<subject>:local (all evidence,
                 local_only by construction, built only when local evidence exists)
  depths         index (one line) · overview (budgeted, densified current state) · synthesis (how it evolved: lineages,
                 stages, replacements, expired task rules) · details (every current item with stage, provenance and id)
                 — all deterministic, no model call
  freshness      inputs_hash: a view is rebuilt only when its inputs changed; invalidate() marks the views depending on
                 an item (evidence, backwards) or a thread stale; expire() ends task-scoped rules whose work stopped
  privacy        enforced in the database (migration 029): the class of a view is the strictest of its evidence and a
                 version is never looser than its view
  reconsolidate  one Router call over a subject's current items proposes merges of duplicates, replacements and
                 expirations ([consolidation] mode: "shadow" = proposals recorded in views.ledger, nothing applied)
Modes ([consolidation] mode): "active" (2026-11-03) = g1 views are served (status active) and reconsolidation applies
only what is safe (strict duplicates, finished task items, replaced decisions; a durable rule is never closed by a
model: such proposals stay recorded); "shadow" = views built, not served, nothing applied; "off" = nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from . import organic, privacy
from .db import connection

log = logging.getLogger("walter.consolidate")
BUILDER = "consolidate@1"
TASK_TTL = timedelta(days=7)
KINDS = ("goal", "constraint", "preference", "correction", "decision", "commitment", "fact")
TITLES = {"goal": "Objectif", "constraint": "Contraintes en vigueur", "preference": "Préférences",
          "correction": "Corrections", "decision": "Décisions", "commitment": "Engagements ouverts", "fact": "Faits"}
STAGE_WORD = {"requested": "demandé", "proposed": "proposé", "decided": "validé", "executed": "exécution rapportée",
              "verified": "résultat vérifié", "abandoned": "abandonné", "open": "ouvert", "done": "tenu", "stated": ""}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mode() -> str:
    m = organic.settings().get("consolidation", {}).get("mode", "shadow")
    return "active" if m == "apply" else m


def view_status() -> str:
    return "active" if mode() == "active" else "shadow"


def key_for(subject: str, variant: str = "cloud") -> str:
    return f"g1:{subject}" + (":local" if variant == "local" else "")


def threads_of(conn, subject: str) -> list[tuple[str, str]]:
    rows = conn.execute("""select distinct split_part(session_id, '/', 1) as source, split_part(session_id, '/', 3) as thread
                           from views.member where view_key = %s""", (subject,)).fetchall()
    return [(r["source"], r["thread"]) for r in rows if r["thread"]]


def items_of(conn, threads: list[tuple[str, str]], allowed: list[str]) -> list[dict]:
    if not threads:
        return []
    return conn.execute("""
        select item_id::text as id, kind, content, status, stage, scope, epistemic, lineage_id::text as lineage,
               valid_from, valid_to, created_at, privacy_class, source_event_ids, attributes,
               source_refs->>'thread' as thread
        from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind = any(%s) and privacy_class = any(%s)
          and (source_refs->>'source', source_refs->>'thread') in (select * from unnest(%s::text[], %s::text[]))
        order by created_at""", (list(KINDS), allowed, [s for s, _ in threads], [t for _, t in threads])).fetchall()


def current(items: list[dict], now: datetime) -> list[dict]:
    return [i for i in items if i["status"] in ("derived", "verified") and (i["valid_to"] is None or i["valid_to"] > now)]


def _inputs_hash(items: list[dict], title: str) -> str:
    sig = sorted((i["id"], i["status"], str(i["valid_to"]), i["stage"] or "") for i in items)
    return hashlib.sha256(json.dumps([title, sig]).encode()).hexdigest()[:20]


# ───────────────────────────── rendering (deterministic) ─────────────────────────────
def _as_state(items: list[dict]) -> dict:
    from .working import KINDS as WK
    out = {k: [] for k in WK}
    for i in items:
        if i["kind"] in out and (i["stage"] or "") not in ("abandoned", "done"):
            out[i["kind"]].append({"id": i["id"], "text": i["content"], "stage": i["stage"], "state": i["stage"],
                                   "scope": i["scope"], "epistemic": i["epistemic"], "at": i["valid_from"] or i["created_at"],
                                   "privacy_class": i["privacy_class"]})
    return out


def render_overview(title: str, cur: list[dict], budget: dict | None = None) -> str:
    from . import working
    st = {"interpreted": _as_state(cur), "pending": [], "plan": None, "question": None}
    body = working.render(st, budget)
    body = body.split("\n", 1)[1] if body else "(aucune connaissance V1 en vigueur)"
    when = [i["valid_from"] or i["created_at"] for i in cur]
    period = f"{min(when):%d/%m/%Y} → {max(when):%d/%m/%Y}" if when else ""
    return f"# {title}\nPériode : {period}\n{body}"


def render_index(title: str, cur: list[dict]) -> str:
    dec = [i for i in cur if i["kind"] == "decision"]
    cons = [i for i in cur if i["kind"] in ("constraint", "preference")]
    last = dec[-1] if dec else (cur[-1] if cur else None)
    tail = ""
    if last:
        from .working import _compact
        tail = f" ; dernier point : {_compact(last['content'], last['id'])} ({(last['valid_from'] or last['created_at']):%d/%m})"
    return f"{title} — {len(dec)} décisions, {len(cons)} règles en vigueur{tail}"


def render_synthesis(title: str, items: list[dict], now: datetime) -> str:
    """How the subject evolved: each lineage in time order with its stages; replacements and expirations shown."""
    lines = [f"# {title} — évolution", ""]
    by_lineage: dict[str, list[dict]] = {}
    for i in items:
        by_lineage.setdefault(i["lineage"] or i["id"], []).append(i)
    chains = sorted(by_lineage.values(), key=lambda c: c[0]["valid_from"] or c[0]["created_at"])
    for chain in chains:
        chain.sort(key=lambda i: i["valid_from"] or i["created_at"])
        head = chain[-1]
        alive = head["status"] in ("derived", "verified") and (head["valid_to"] is None or head["valid_to"] > now)
        for k, i in enumerate(chain):
            when = (i["valid_from"] or i["created_at"]).strftime("%d/%m %H:%M")
            stage = STAGE_WORD.get(i["stage"] or "", "")
            if i["status"] == "superseded":
                fate = " → remplacé"
            elif i["valid_to"] and i["valid_to"] <= now:
                fate = f" → expiré ({(i['attributes'] or {}).get('expired_reason', 'échéance')})"
            elif k == len(chain) - 1:
                fate = " (en vigueur)" if alive else ""
            else:
                fate = ""
            lines.append(f"- {when} [{TITLES.get(i['kind'], i['kind'])}{', ' + stage if stage else ''}] {i['content']}{fate}")
    return "\n".join(lines)


def render_details(title: str, items: list[dict], now: datetime) -> str:
    lines = [f"# {title} — détails (connaissances V1 et preuves)", ""]
    for kind in KINDS:
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        lines.append(f"## {TITLES[kind]}")
        for i in group:
            status = i["status"] if i["status"] != "derived" else ("expiré" if i["valid_to"] and i["valid_to"] <= now else "en vigueur")
            lines.append(f"- {i['content']} — {status}; étape {i['stage'] or '-'}; portée {i['scope'] or '-'}; "
                         f"{i['epistemic'] or '-'}; {len(i['source_event_ids'] or [])} preuve(s); id {i['id']}")
    return "\n".join(lines)


# ───────────────────────────── building ─────────────────────────────
def _ensure_view(conn, key: str, subject: str, title: str, variant: str) -> None:
    status = view_status()
    conn.execute("""insert into views.view (view_key, domain, horizon, title, status, generation, kind, attributes, privacy_class)
                    values (%s, 'projects', 'medium', %s, %s, 'g1', 'subject', %s, 'cloud_allowed')
                    on conflict (view_key) do update set title = excluded.title, updated_at = now(),
                        status = case when views.view.status in ('shadow', 'active') then excluded.status
                                      else views.view.status end""",
                 (key, title, status, json.dumps({"mirrors": subject, "variant": variant, "builder": BUILDER})))


def set_embedding(conn, key: str, text: str) -> None:
    """Local embedding of a view (its index + overview), for related_views(): no model call, nothing leaves the VM."""
    try:
        from .search import embed, vec
        conn.execute("update views.view set embedding = %s::vector where view_key = %s", (vec(embed([text[:2000]])[0]), key))
    except Exception as e:  # an embedding is an optimisation
        log.warning("view embedding failed for %s: %s", key, e)


def related_views(query: str, *, max_privacy: str = "cloud_allowed", limit: int = 6, min_sim: float = 0.3) -> list[str]:
    """Index lines of the active V1 views (subjects, episodes, periods, people, projects) closest to the query: pointers
    a model can open with memory_view(key, depth) — a short context that says where the details are."""
    from .search import embed, vec
    allowed = privacy.allowed_classes(max_privacy)
    qv = vec(embed([query[:2000]])[0])
    with connection() as conn:
        rows = conn.execute("""
            select v.view_key, v.kind, v.epistemic, v.last_at, x.content, x.stale_since,
                   1 - (v.embedding <=> %s::vector) as sim
            from views.view v join lateral (select content, stale_since from views.version where view_key = v.view_key
                                            and depth = 'index' order by version desc limit 1) x on true
            where v.generation = 'g1' and v.status = 'active' and v.privacy_class = any(%s) and v.embedding is not null
            order by v.embedding <=> %s::vector limit %s""", (qv, allowed, qv, limit * 3)).fetchall()
    out = []
    for r in rows:
        if r["sim"] is None or r["sim"] < min_sim:
            continue
        flag = " (à reconstruire)" if r["stale_since"] else ""
        out.append(f"- [{r['view_key']}] {r['content']}{flag}")
        if len(out) >= limit:
            break
    return out


def _sync_evidence(conn, key: str, cur: list[dict]) -> None:
    ids = [i["id"] for i in cur]
    conn.execute("""delete from views.evidence where view_key = %s and added_by = %s and ref_kind = 'derived'
                    and not (ref_id = any(%s))""", (key, BUILDER, ids))
    for i in cur:
        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                        values (%s, 'derived', %s, 'contains', %s, %s) on conflict do nothing""",
                     (key, i["id"], i["privacy_class"], BUILDER))


def build_subject(subject: str, *, now: datetime | None = None, force: bool = False) -> dict:
    """(Re)build the g1 projections of one subject. Returns what was written per variant."""
    now = now or _now()
    out = {}
    with connection() as conn:
        src = conn.execute("select title from views.view where view_key = %s", (subject,)).fetchone()
        title = (src or {}).get("title") or subject
        threads = threads_of(conn, subject)
        everything = items_of(conn, threads, privacy.allowed_classes("local_only"))
    has_local = any(i["privacy_class"] != "cloud_allowed" for i in everything)
    for variant in ("cloud", "local"):
        if variant == "local" and not has_local:
            continue
        allowed = privacy.allowed_classes("cloud_allowed" if variant == "cloud" else "local_only")
        items = [i for i in everything if i["privacy_class"] in allowed]
        cur = current(items, now)
        key = key_for(subject, variant)
        h = _inputs_hash(items, title) + ("" if variant == "cloud" else "L")
        with connection() as conn:
            _ensure_view(conn, key, subject, title, variant)
            last = conn.execute("""select inputs_hash, stale_since from views.version where view_key = %s and depth = 'overview'
                                   order by version desc limit 1""", (key,)).fetchone()
            if last and last["inputs_hash"] == h and not last["stale_since"] and not force:
                out[variant] = {"key": key, "rebuilt": False}
                continue
            _sync_evidence(conn, key, cur)
            vclass = conn.execute("select privacy_class from views.view where view_key = %s", (key,)).fetchone()["privacy_class"]
            texts = {"index": render_index(title, cur), "overview": render_overview(title, cur),
                     "synthesis": render_synthesis(title, items, now), "details": render_details(title, items, now)}
            refs = {"items": [i["id"] for i in items], "current": [i["id"] for i in cur], "threads": threads,
                    "builder": BUILDER}
            watermark = max((i["created_at"] for i in items), default=None)
            set_embedding(conn, key, texts["index"] + "\n" + texts["overview"])
            for depth, content in texts.items():
                conn.execute("""insert into views.version (view_key, depth, version, content, source_refs, watermark, builder,
                                    model, privacy_class, inputs_hash)
                                values (%s, %s, coalesce((select max(version) from views.version where view_key = %s
                                        and depth = %s), 0) + 1, %s, %s, %s, %s, null, %s, %s)""",
                             (key, depth, key, depth, content, json.dumps(refs, default=str), watermark, BUILDER, vclass, h))
            conn.execute("""update views.view set last_at = greatest(coalesce(last_at, %s), %s), updated_at = now(),
                              first_at = least(coalesce(first_at, %s), %s) where view_key = %s""",
                         (watermark or now, watermark or now, watermark or now, watermark or now, key))
            conn.execute("""insert into views.ledger (view_key, action, detail) values (%s, 'rebuilt', %s)""",
                         (key, json.dumps({"builder": BUILDER, "items": len(items), "current": len(cur),
                                           "tokens": {d: len(t) // 4 for d, t in texts.items()}})))
        out[variant] = {"key": key, "rebuilt": True, "items": len(items), "current": len(cur),
                        "tokens": {d: len(t) // 4 for d, t in texts.items()}, "privacy_class": vclass}
    return out


def invalidate(*, item_ids: list[str] | None = None, threads: list[tuple[str, str]] | None = None) -> int:
    """Mark stale the latest versions of the g1 views that depend on these items (evidence, backwards) or threads, and
    of every view that contains or indexes a stale view (episode → day → week → month)."""
    keys: set[str] = set()
    with connection() as conn:
        if item_ids:
            keys |= {r["view_key"] for r in conn.execute(
                "select distinct view_key from views.evidence where ref_kind = 'derived' and ref_id = any(%s)", (item_ids,))}
        for source, thread in threads or []:
            subjects = {r["view_key"] for r in conn.execute(
                "select distinct view_key from views.member where session_id like %s", (f"{source}/%/{thread}",))}
            keys |= {key_for(s) for s in subjects} | {key_for(s, "local") for s in subjects}
        frontier = set(keys)
        while frontier:    # parents: a day lists an episode, a week indexes its days, a month its weeks (P1.6)
            parents = {r["view_key"] for r in conn.execute(
                "select distinct view_key from views.evidence where ref_kind = 'view' and ref_id = any(%s)",
                (list(frontier),))} - keys
            keys |= parents
            frontier = parents
        if keys:
            conn.execute("""update views.version v set stale_since = coalesce(stale_since, now())
                            where v.view_key = any(%s) and v.version = (select max(version) from views.version x
                                  where x.view_key = v.view_key and x.depth = v.depth)""", (list(keys),))
    return len(keys)


def expire(now: datetime | None = None) -> dict:
    """End task-scoped rules whose work stopped (no message in their thread for TASK_TTL), and mark the views that
    depended on them or on items that reached their valid_to stale."""
    now = now or _now()
    with connection() as conn:
        rows = conn.execute("""
            update core.derived_items d set valid_to = %s,
                   attributes = d.attributes || jsonb_build_object('expired_reason', 'travail terminé (fil inactif)')
            where d.generation = 'g1' and d.derived_by = 'l3.extract' and d.scope = 'task'
              and d.status in ('derived', 'verified') and d.valid_to is null
              and not exists (select 1 from core.events e where e.source = d.source_refs->>'source'
                              and e.thread_id = d.source_refs->>'thread' and e.occurred_at > %s::timestamptz
                              and e.occurred_at >= %s::timestamptz - interval '30 days')
            returning item_id::text""", (now, now - TASK_TTL, now)).fetchall()
        due = conn.execute("""select item_id::text from core.derived_items where generation = 'g1'
                              and valid_to <= %s::timestamptz and valid_to > %s::timestamptz - interval '1 day'""",
                           (now, now)).fetchall()
    ids = [r["item_id"] for r in rows] + [r["item_id"] for r in due]
    return {"expired_task_rules": len(rows), "views_invalidated": invalidate(item_ids=ids) if ids else 0}


def tick(limit: int = 10) -> dict:
    """Build the g1 projection of subjects that have V1 knowledge and no fresh version (shadow)."""
    if mode() == "off":
        return {"built": 0}
    with connection() as conn:
        subjects = [r["view_key"] for r in conn.execute("""
            select v.view_key from views.view v
            where v.generation = 'g0' and v.status = 'active' and v.kind = 'subject'
              and exists (select 1 from views.member m join core.derived_items d
                          on d.source_refs->>'thread' = split_part(m.session_id, '/', 3)
                          and d.source_refs->>'source' = split_part(m.session_id, '/', 1)
                          where m.view_key = v.view_key and d.generation = 'g1' and d.derived_by = 'l3.extract')
              and (not exists (select 1 from views.version x where x.view_key = 'g1:' || v.view_key)
                   or exists (select 1 from views.version x where x.view_key in ('g1:' || v.view_key, 'g1:' || v.view_key || ':local')
                              and x.stale_since is not null
                              and x.version = (select max(version) from views.version y where y.view_key = x.view_key
                                               and y.depth = x.depth)))
            order by v.last_at desc nulls last limit %s""", (limit,))]
    built, proposed = 0, 0
    for s in subjects:
        try:
            r = build_subject(s)
            built += sum(1 for v in r.values() if v.get("rebuilt"))
            if r.get("cloud", {}).get("current", 0) >= RECON_MIN_ITEMS and _recon_due(s):
                reconsolidate(s)          # shadow: proposals recorded in views.ledger; apply mode applies them
                proposed += 1
        except Exception:
            log.exception("consolidate: %s failed", s)
    return {"subjects": len(subjects), "built": built, "reconsolidated": proposed}


RECON_MIN_ITEMS = 8
RECON_EVERY = timedelta(hours=6)


def _recon_due(subject: str) -> bool:
    with connection() as conn:
        r = conn.execute("""select max(at) at from views.ledger where view_key = %s and action like 'reconsolidate.%%'""",
                         (key_for(subject),)).fetchone()
    return r["at"] is None or r["at"] < _now() - RECON_EVERY


# ───────────────────────────── reconsolidation (Router, shadow first) ─────────────────────────────
RECON_PROMPT = """Voici les connaissances EN VIGUEUR d'un même sujet de travail de Monsieur, de la plus ancienne à la plus récente.
Chaque ligne : identifiant, catégorie, étape, portée, origine (stated_owner = dit par Monsieur ; agent_reported = rapporté par W.Alter), date, texte.

{items}

Repère ce qui est établi par les connaissances elles-mêmes :
- "merge" : groupes d'identifiants qui disent la même chose (même catégorie, même portée) ; le plus récent sera gardé ;
- "supersede" : une connaissance plus récente qui en remplace une plus ancienne : un choix changé, une règle modifiée, ou
  une consigne d'étape dépassée parce que l'étape a été franchie (ex. « montre-moi les résultats avant de passer à l'étape B »
  est remplacée par une connaissance plus récente qui valide l'étape A ou lance l'étape B) ;
- "expire" : un élément de portée « task » dont le travail est terminé ou franchi d'après une connaissance plus récente
  (une règle de travail prend fin ; une demande accomplie sera marquée exécutée, pas effacée).
Ne regroupe pas deux règles différentes ; ne remplace pas une règle durable par une simple demande ponctuelle. Réponds en JSON :
{{"merge": [["id", "id"]], "supersede": [{{"old": "id", "new": "id", "why": "..."}}], "expire": [{{"id": "id", "why": "..."}}]}}"""


def reconsolidate(subject: str, *, chat=None, apply: bool | None = None) -> dict:
    """One Router call over the subject's current cloud items. Proposals are validated (ids exist, same kind for a
    merge, the replacing item is newer and stated by the owner) and recorded; applied only in mode 'apply'."""
    from . import llm
    chat = chat or llm.chat
    apply = (mode() == "active") if apply is None else apply
    now = _now()
    with connection() as conn:
        items = current(items_of(conn, threads_of(conn, subject), ["cloud_allowed"]), now)
    if len(items) < 4:
        return {"skipped": "too few items"}
    short = {i["id"][:8]: i for i in items}
    text = "\n".join(f"{k} | {i['kind']} | {i['stage'] or '-'} | {i['scope'] or '-'} | {i['epistemic'] or '-'} | "
                     f"{(i['valid_from'] or i['created_at']):%d/%m %H:%M} | {i['content']}" for k, i in short.items())
    poste = organic.settings().get("consolidation", {}).get("poste", "general/L3")   # a Router tier, never a model
    res = chat([{"role": "user", "content": RECON_PROMPT.format(items=text)}], poste=poste,
               processor="consolidate.reconsolidate", processor_version="1", privacy_class="cloud_allowed",
               budget="recurring", purpose=f"reconsolidate {subject}", response_format={"type": "json_object"},
               max_tokens=3000, timeout=300)
    c = res["content"] or "{}"
    data = json.loads(c[c.find("{"):c.rfind("}") + 1] or "{}")
    when = lambda i: i["valid_from"] or i["created_at"]
    ok = {"merge": [], "supersede": [], "expire": []}
    for group in data.get("merge") or []:
        g = [short[x] for x in group if isinstance(x, str) and x in short]
        if len(g) >= 2 and len({i["kind"] for i in g}) == 1:
            ok["merge"].append([i["id"] for i in sorted(g, key=when)])
    for s in data.get("supersede") or []:
        old, new = short.get(str(s.get("old"))), short.get(str(s.get("new")))
        if old and new and old is not new and when(new) >= when(old) and new["epistemic"] == "stated_owner":
            ok["supersede"].append({"old": old["id"], "new": new["id"], "why": str(s.get("why", ""))[:300]})
    for e in data.get("expire") or []:
        it = short.get(str(e.get("id")))
        if it and it["scope"] == "task" and it["kind"] != "correction":   # a correction ends only by a newer one
            ok["expire"].append({"id": it["id"], "why": str(e.get("why", ""))[:300]})
    held = {"merge": [], "supersede": []}
    if apply:      # safe application only (owner, 2026-11-03): no destructive or uncertain closing of a durable rule
        ok, held = _safe(ok, {i["id"]: i for i in items})
    with connection() as conn:
        conn.execute("insert into views.ledger (view_key, action, detail) values (%s, %s, %s)",
                     (key_for(subject), "reconsolidate.applied" if apply else "reconsolidate.proposed",
                      json.dumps({**ok, "withheld": held, "items": len(items), "model": res.get("model")})))
        if apply:
            for group in ok["merge"]:
                keep = group[-1]
                for old in group[:-1]:
                    _supersede(conn, old, keep, "merged")
            for s in ok["supersede"]:
                _supersede(conn, s["old"], s["new"], "superseded")
            for s in held["supersede"]:     # a durable rule stays in force, flagged so a reader knows it may be outdated
                conn.execute("""update core.derived_items set attributes = attributes || jsonb_build_object(
                                  'replacement_proposed', jsonb_build_object('by', %s::text, 'why', %s::text, 'at', now()))
                                where item_id = %s and status in ('derived','verified')""", (s["new"], s["why"], s["old"]))
            for e in ok["expire"]:
                kind = next(i["kind"] for i in items if i["id"] == e["id"])
                if kind in ("decision", "goal", "commitment"):   # done is not gone: the decision stays, as executed
                    conn.execute("""update core.derived_items set stage = case when kind = 'commitment' then 'done'
                                      else 'executed' end, attributes = attributes || jsonb_build_object('completed_reason',
                                      %s::text) where item_id = %s""", (e["why"] or "accompli", e["id"]))
                else:                                               # a task rule whose work is over ends
                    conn.execute("""update core.derived_items set valid_to = now(), attributes = attributes ||
                                      jsonb_build_object('expired_reason', %s::text) where item_id = %s and valid_to is null""",
                                 (e["why"] or "dépassé", e["id"]))
    if apply:
        invalidate(item_ids=[x for g in ok["merge"] for x in g] + [s["old"] for s in ok["supersede"]]
                   + [e["id"] for e in ok["expire"]])
    return {"proposals": ok, "withheld": held, "applied": apply, "items": len(items)}


DURABLE_RULES = ("constraint", "preference", "correction")


def _safe(ok: dict, by_id: dict) -> tuple[dict, dict]:
    """What may be applied without the owner: merges of strict duplicates only (same kind and scope, close meaning,
    mostly the same words, the same numbers — working._same), replacements that do not close a durable rule, and the
    already-guarded expirations of task items. The rest is withheld (kept in the ledger as proposals)."""
    from .working import _same
    applied, held = {"merge": [], "supersede": [], "expire": ok["expire"]}, {"merge": [], "supersede": []}
    try:
        from .search import embed
    except Exception:
        embed = None
    for group in ok["merge"]:
        keep = by_id[group[-1]]
        same = [group[-1]]
        for old in group[:-1]:
            o = by_id[old]
            cos = 0.0
            if embed is not None:
                v = embed([o["content"][:400], keep["content"][:400]])
                cos = float(v[0] @ v[1])
            if o["scope"] == keep["scope"] and _same(o["content"], keep["content"], cos):
                same.insert(0, old)
            else:
                held["merge"].append([old, group[-1]])
        if len(same) >= 2:
            applied["merge"].append(same)
    for sp in ok["supersede"]:
        old = by_id[sp["old"]]
        if old["kind"] in DURABLE_RULES and (old["scope"] or "durable") != "task":
            held["supersede"].append(sp)
        else:
            applied["supersede"].append(sp)
    return applied, held


def _supersede(conn, old: str, new: str, how: str) -> None:
    conn.execute("""update core.derived_items set status = 'superseded', valid_to = now(),
                      attributes = attributes || jsonb_build_object('superseded_by', %s::text, 'how', %s::text)
                    where item_id = %s and status in ('derived','verified')""", (new, how, old))
    conn.execute("""update core.derived_items n set lineage_id = o.lineage_id from core.derived_items o
                    where n.item_id = %s and o.item_id = %s and o.lineage_id is not null""", (new, old))
    conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                    values ('derived_items', %s, 'derived', %s, 'supersedes') on conflict do nothing""", (new, old))
