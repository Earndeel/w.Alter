"""Current-state projections (PROJECTIONS.md, lot P1: the project projection) — a structured READ of the memory.

A projection stores nothing and asks no model. It takes the current, versioned knowledge of a project:
- l3.extract items whose own subject belongs to the project;
- stage and progress steps of goals, with their Run Plane task when one is linked;
- decisions, constraints and their contested pairs;
- the change log (core.derived_changes).
It orders that knowledge by reliability and by fact date, and renders it under fixed headings. Every line keeps its
item id, its own subject, its dates and its provenance; `knowledge.history(id)` gives its versions.

Hierarchy (owner, 19/11: « je ne veux pas les fusionner avec leur parent »): a project is the set of subjects that
normalise to one key (`knowledge.subject_key`), plus the instance's aliases (`@instance/config/memory/projects.toml`).
A sub-project is linked to its parent:
- explicitly, in the instance's [parents];
- or by its name: « Walter Memory » / « walter-memory » belong to « walter » when that project exists.
A parent shows only its own knowledge. Of each child it shows a short aggregate (counts, the most important change,
a blocked goal or a contradiction), never the child's technical knowledge.

Dates: `valid_from` is when a statement was said (observed). When the text dates the fact itself (« depuis le 16
novembre », « le 14/11 »), that date is the fact date. It orders the lines and places them in a past view (`at=`).
An expired item (valid_to passed) is never current. An unreconciled chain is several current, unlinked statements on
one named thing, for instance a component's state; it is shown as uncertain: the latest text is not taken for a
verified truth.
"""
from __future__ import annotations

import contextlib
import re
import subprocess
import time
import tomllib
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .db import connection
from . import knowledge, privacy

PREFIX = "project:"
RECENT = timedelta(days=14)          # « changements récents » and recently done goals
FOLLOWED = timedelta(days=30)        # an open request older than this with no step has an unknown status
CHILD_RECENT = timedelta(days=7)     # what a sub-project brings up to its parent
CHAIN_WINDOW = timedelta(days=60)  # how far back a chain of unlinked state statements is looked for
CHAIN_SPAN = timedelta(hours=20)     # a chain is an evolution: statements on different days
MIN_ITEMS = 5                        # a subject with fewer current items is not a project of the catalog
PARENT_MIN_ITEMS = 20                # a name-inferred parent must be a real project
DONE = {"executed", "verified", "done"}
PROVEN = {"verified", "done"}         # a goal shown as achieved: proof checked or confirmed by the owner
CLAIMED = {"executed"}                # an agent or the Run Plane says it is done: shown as such, never as verified
ACTIVE = timedelta(days=3)           # work « en cours »: an open Run Plane objective, or a step this recent
DROPPED = {"cancelled", "abandoned"}
IN_FORCE = {"decided", "executed", "verified"}       # a decision; « requested » counts when the owner asked it
RULE_KINDS = {"constraint", "preference", "correction"}
RANK = {"verified": 0, "stated_owner": 1, "observed": 2, "agent_reported": 3, "stated_third_party": 4, "inferred": 5}
WHO = {"stated_owner": "Monsieur", "agent_reported": "rapporté par W.Alter", "observed": "observé",
       "stated_third_party": "tiers", "inferred": "hypothèse"}
BLOCKED = re.compile(r"(?i)(bloqu|en attente d[eu']|impossible|échou|en échec|ne fonctionne pas|refus[ée]|"
                     r"blocked|waiting for|failed)")
STATE_WORDS = re.compile(r"(?i)(\bencore\b|\bplus\b|désormais|retiré|arrêté|\bactif|active|en production|en pause|"
                         r"désactiv|remplac|tourne|fonctionne|installé|désinstall|en service|hors service|still|"
                         r"no longer|running|stopped|retired)")
MONTHS = {m: i for i, m in enumerate(("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                                      "septembre", "octobre", "novembre", "décembre"), 1)}
DATE_FR = re.compile(r"(?i)\b(depuis le|dès le|le|du|au)\s+(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?")
DATE_GATE = re.compile(r"(?i)\b(?:le|du|au)\s+\d")
# Relevance (owner, 19/11: « l'état global, les avancées, les décisions en vigueur, les travaux en cours, les blocages,
# les prochaines étapes ; les détails techniques restent consultables mais ne dominent pas »): a deterministic weight
# from what the extraction recorded (kind, act, scope, epistemic, proof) and from the text's technical density.
TECH = re.compile(r"(`[^`]+`|(?<![\w.])/[a-z_.-]+/[\w./-]*|:\d{2,5}\b|\b\w+_\w+\b|--\w|\b[0-9a-f]{8,}\b|\bhttps?://|"
                  r"\.(?:py|toml|json|md|sh|yaml|service|timer)\b|\b\d+(?:[.,]\d+)?\s?(?:ms|s|Mo|Go|Ko|tokens?|%)(?!\w)|"
                  r"\b[a-z]+\d[\w.-]*\b|\b\w+\.\w+\(|\bmigration \d+|\b(?!w\.alter\b)[a-z]+\.[a-z_]{3,}\b|"
                  r"\b[a-z]+-[a-z]+-[a-z-]+\b)", re.I)
GLOBAL = re.compile(r"(?i)(en production|\bnati(f|ve)\b|désinstall|\bretiré|\barrêté|n'est plus|ne sont plus|"
                    r"n.en dépend|validé|terminé|livré|en service|migr[ée]|\blots?\b|\bphases?\b|architecture|"
                    r"runtime|\bunique\b|repose sur|ne dispose|trajectoire|priorit|basculé|non lancé)")
NEXT = re.compile(r"(?i)(prochaine étape|prochaines étapes|reste à|il reste|à venir|en attente de (son|votre|sa) "
                  r"(go|feu vert|validation|accord)|attend (son|votre|sa) (go|feu vert|validation|accord)|"
                  r"\bnext step)")
# a request that is itself a test of W.Alter (« pour le test socle bd1f68 », « un test de sécurité ») is not
# project work: counted, never shown as a goal
TEST = re.compile(r"(?i)(\btests?\s+(de|d['’]|socle)|pour (le|la|l['’])\s*(test|opération de test|tâche-socle)|"
                  r"tâche-socle|\bPIVOINE-|\bun test\b|\btest [0-9a-f]{6}\b)")
STATE_MIN = 2                        # weight a fact needs to be part of the global state
DATE_NUM = re.compile(r"(?i)\b(depuis le|dès le|le|du|au)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")


# ───────────────────────────── catalog and hierarchy ─────────────────────────────
@lru_cache(maxsize=1)
def _config() -> dict:
    """The instance's aliases and parents (keys normalised); read once per process, like organic.settings."""
    path = None
    try:
        path = subprocess.run(["walter", "instance", "config", "memory", "projects.toml"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        data = tomllib.loads(Path(path).read_text()) if path else {}
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    norm = lambda s: knowledge.subject_key(PREFIX + s) if s else ""   # noqa: E731
    return {"aliases": {norm(k): norm(v) for k, v in (data.get("aliases") or {}).items()},
            "parents": {norm(k): norm(v) for k, v in (data.get("parents") or {}).items()},
            # subjects written without the prefix that belong to a project (raw subject key → project key)
            "subjects": {knowledge.subject_key(k): norm(v) for k, v in (data.get("subjects") or {}).items() if v},
            # the assistant's own project (attribution.py): never the default home of what is said to the assistant
            "assistant": norm((data.get("attribution") or {}).get("assistant") or "")}


def resolve(key_or_name: str) -> str:
    """Any spelling of a project (« W.Alter », « project:walter-memory ») → its key (« project:walter »)."""
    s = (key_or_name or "").strip()
    k = knowledge.subject_key(s if s.lower().startswith(PREFIX) else PREFIX + s)
    return _config()["aliases"].get(k, k)


CATALOG_TTL = 60.0                   # seconds: names and hierarchy only, never the content of a projection
_catalog_memo: dict = {}


def catalog(conn, fresh: bool = False) -> dict[str, dict]:
    """{key: {key, name, labels, count, parent, children}}: every project with current knowledge, its spellings and
    its place in the hierarchy. A read over the current items (index derived_g1_project_label; no table of projects).
    The list of names is reused for CATALOG_TTL seconds in a process (a new project shows up within a minute); what a
    projection says is always read live."""
    m = _catalog_memo.get("v")
    if m and not fresh and time.monotonic() - m[0] < CATALOG_TTL:
        return m[1]
    cat = _catalog(conn)
    _catalog_memo["v"] = (time.monotonic(), cat)
    return cat


def _catalog(conn) -> dict[str, dict]:
    rows = conn.execute("""
        select attributes->>'subject' s, count(*) n from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and status in ('derived', 'verified')
          and (valid_to is null or valid_to > now()) and (attributes->>'subject') ilike 'project:%'
        group by 1""").fetchall()
    bare = _config()["subjects"]
    if bare:
        rows += conn.execute(f"""
            select attributes->>'subject' s, count(*) n from core.derived_items
            where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and {SUBJ} = any(%s)
              and status in ('derived', 'verified') and (valid_to is null or valid_to > now())
            group by 1""", (list(bare),)).fetchall()
    cat: dict[str, dict] = {}
    for r in rows:
        raw = knowledge.subject_key(r["s"])
        k = bare.get(raw) or resolve(r["s"])
        e = cat.setdefault(k, {"key": k, "labels": {}, "count": 0, "parent": None, "children": []})
        if r["s"].lower().startswith(PREFIX):
            label = r["s"][len(PREFIX):]
            e["labels"][label] = e["labels"].get(label, 0) + r["n"]
        else:                     # a subject without the prefix (config [subjects]) counts, but names nothing
            e["bare"] = e.get("bare", 0) + r["n"]
        e["count"] += r["n"]
    cat = {k: e for k, e in cat.items() if e["count"] >= MIN_ITEMS}
    for k, e in cat.items():
        if not e["labels"]:
            e["labels"] = {k[len(PREFIX):]: e["count"]}
        top = max(e["labels"].values())          # the usual spelling; a capitalised one when it is about as frequent
        e["name"] = max(e["labels"], key=lambda l: (e["labels"][l] * 2 >= top and any(c.isupper() for c in l),
                                                     e["labels"][l]))
    parents = _config()["parents"]
    for k, e in cat.items():
        if k in parents:
            p = parents[k] or None
        else:
            p = None
            for label in sorted(e["labels"], key=lambda l: -e["labels"][l]):
                words = [w for w in re.split(r"[\s\-_/]+", label) if w]
                if len(words) >= 2:
                    first = resolve(words[0])
                    if first != k and cat.get(first, {}).get("count", 0) >= PARENT_MIN_ITEMS:
                        p = first
                        break
        if p and p in cat and p != k and parents.get(p) != k:
            e["parent"] = p
    for k, e in cat.items():
        if e["parent"]:
            cat[e["parent"]]["children"].append(k)
    for e in cat.values():
        e["children"].sort(key=lambda c: -cat[c]["count"])
    return cat


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def find_projects(message: str, conn=None, limit: int = 2, cat: dict | None = None) -> list[str]:
    """The projects a message names, by their spellings and aliases (longest name first, so « Walter Memory » is not
    read as « Walter »). Deterministic: no model, no embedding."""
    if cat is None:
        if conn is None:
            with connection() as c:
                cat = catalog(c)
        else:
            cat = catalog(conn)
    names: list[tuple[str, str]] = []
    for k, e in cat.items():
        for label in e["labels"]:
            names.append((label, k))
    for alias, k in _config()["aliases"].items():
        if k in cat:
            names.append((alias[len(PREFIX):], k))
    text = _fold(message)
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []
    for label, k in sorted(names, key=lambda x: -len(x[0])):
        words = [w for w in re.split(r"[^a-z0-9]+", _fold(label)) if w]
        if not words or len("".join(words)) < 4:
            continue
        pat = re.compile(r"(?<![a-z0-9])" + r"[\s\-_.]*".join(map(re.escape, words)) + r"(?![a-z0-9])")
        for m in pat.finditer(text):
            if any(m.start() < b and a < m.end() for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), k))
    out: list[str] = []
    for _, k in sorted(found):
        if k not in out:
            out.append(k)
    return out[:limit]


# ───────────────────────────── dates ─────────────────────────────
@lru_cache(maxsize=50000)
def fact_date(text: str, said: datetime | None) -> datetime | None:
    """The date the text gives to the fact itself (« depuis le 16 novembre 2026 », « le 14/11 »), when it is before the
    statement: a later date is a plan or a deadline, never a fact date."""
    if not text or not said or not DATE_GATE.search(text):
        return None
    found = []
    for m in DATE_FR.finditer(text):
        found.append((m.group(1).lower(), int(m.group(2)), MONTHS[m.group(3).lower()], m.group(4)))
    for m in DATE_NUM.finditer(text):
        found.append((m.group(1).lower(), int(m.group(2)), int(m.group(3)), m.group(4)))
    found.sort(key=lambda f: not f[0].startswith(("depuis", "dès")))      # « depuis le … » first
    for _, d, mo, y in found:
        try:
            year = int(y) if y else said.year
            year = year + 2000 if year < 100 else year
            dt = datetime(year, mo, d, tzinfo=timezone.utc)
            if not y and dt > said + timedelta(days=1):
                if dt - said < timedelta(days=180):    # « le 25 novembre » said on the 18th: a plan, not last year
                    continue
                dt = dt.replace(year=year - 1)         # « le 20 décembre » said in January: last December
        except ValueError:
            continue
        if said - timedelta(days=365) <= dt <= said + timedelta(days=1):
            return min(dt, said)
    return None


def _d(x) -> str:
    """dd/mm, with the year when it is not this year's."""
    if not isinstance(x, datetime):
        return ""
    return x.strftime("%d/%m") if x.year == datetime.now(timezone.utc).year else x.strftime("%d/%m/%Y")


# ───────────────────────────── the read ─────────────────────────────
COLS = """item_id::text, kind, content, stage, scope, epistemic, status, lineage_id::text, privacy_class,
          coalesce(valid_from, created_at) said, valid_to, created_at, attributes->>'subject' subject,
          regexp_replace(lower(attributes->>'subject'), '[^a-z0-9:]', '', 'g') nkey,
          attributes->>'proof' proof, (attributes->>'contested')::boolean contested, attributes->>'task_id' task_id,
          attributes->'progress'->-1 last_step, attributes->>'domain' dom, attributes->>'act' act,
          attributes->>'task_status' task_status, cardinality(source_event_ids) nsrc"""
SUBJ = "regexp_replace(lower(attributes->>'subject'), '[^a-z0-9:]', '', 'g')"


def _items(conn, keymap: dict[str, str], at: datetime | None, allowed: list[str],
           since: datetime | None = None, notable: bool = False) -> list[dict]:
    """The items that hold now (current, not expired) or at `at` (their validity contains it, the fact date counting
    as their start) for these subject keys ({normalised subject: project key}), in one query over the index
    derived_g1_subject_key. Only the fields a projection shows are read (no full attributes)."""
    keys = list(keymap)
    recent = "" if since is None else "and coalesce(valid_from, created_at) > %(since)s"
    if notable:       # what a sub-project may bring up: decisions, goals, commitments, contested items
        recent += " and (kind in ('decision', 'goal', 'commitment') or (attributes->>'contested')::boolean)"
    if at is None:
        rows = conn.execute(f"""select {COLS} from core.derived_items
            where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and {SUBJ} = any(%(keys)s)
              and status in ('derived', 'verified') and (valid_to is null or valid_to > now())
              and privacy_class = any(%(allowed)s) {recent}""",
            {"keys": keys, "allowed": allowed, "since": since}).fetchall()
    else:
        rows = conn.execute(f"""select {COLS} from core.derived_items
            where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and {SUBJ} = any(%(keys)s)
              and status in ('derived', 'verified', 'superseded') and (valid_to is null or valid_to > %(at)s)
              and coalesce(valid_from, created_at) <= %(at)s + interval '400 days'
              and privacy_class = any(%(allowed)s) {recent}""",
            {"keys": keys, "allowed": allowed, "since": since, "at": at}).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        r["project"] = keymap[r.pop("nkey")]
        r["attributes"] = {"proof": r.pop("proof"), "contested": bool(r.pop("contested")),
                           "task_id": r.pop("task_id"), "progress": [x for x in [r.pop("last_step")] if x],
                           "task_status": r.pop("task_status")}
        r["fact"] = fact_date(r["content"], r["said"])
        r["from"] = r["fact"] or r["said"]
        if at is not None and r["from"] > at:
            continue
        out.append(r)
    return out


# What a statement says about a project's own lifecycle: the project is the subject of the state (« Hermes est
# arrêté », « avec Hermes arrêté », « l'arrêt d'Hermes », « Hermes n'est plus utilisé »), never the agent of an action
# (« la purge Memory a retiré des doublons »). Matched on accent-folded text.
_AUX = (r"(?:\s+(?:est|a ete|ont ete|sont|etait|reste|restera|sera|is|was|has been|have been))?"
        r"(?:\s+(?:desormais|maintenant|toujours|bien|completement|definitivement|de nouveau|a nouveau|now|still))?")
_STOP = r"(?:arrete|stoppe|desactive|retire|desinstalle|hors service|en pause|mis de cote|stopped|retired|disabled)"
_RUN = r"(?:actif|active|en production|en service|relance|reactive|remis en service|running|live|enabled)"
_OF = r"\s+(?:de\s+|d'|du\s+)(?:l'|la\s+|le\s+)?"


@lru_cache(maxsize=256)
def _status_rx(names: tuple) -> dict:
    n = "(?:" + "|".join(re.escape(x) for x in sorted(names, key=len, reverse=True)) + ")"
    # the project as a subject: at the start, after punctuation or after a function word (« avec Hermes arrêté »),
    # never inside an identifier (ask_hermes) nor after a noun (« l'extraction Memory fonctionne »)
    # (never after « de » / « du » / « d' »: « l'extraction de Walter Memory est active » is about the extraction)
    # « X et Y sont arrêtés » is about both, « la clé utilisée par la mémoire et le Router est active » about the
    # key: after « et » / « ou » only a plural verb makes the project a subject
    lead = (r"(?:^|[.;:!?«\"(]\s*|\b(?:(?:avec|que|sans|projet|module|service|runtime|agent|application|outil)\s+)?"
            r"(?<!et )(?<!ou )(?:le|la|les)\s+|\b(?:avec|que|sans|projet|module|service|runtime|agent|application|"
            r"outil)\s+|\bl')")
    coord = r"\b(?:et|ou)\s+(?:le\s+|la\s+|les\s+|l')?"
    plural = r"(?:\s+(?:sont|ont ete|etaient|restent|seront|are|were|have been))(?:\s+(?:desormais|maintenant|toujours|bien|completement|definitivement|de nouveau|a nouveau|now|still))?"
    return {"arrêté": re.compile(rf"{lead}{n}{_AUX}\s+{_STOP}\b|{lead}{n}\s+n'?est plus\b|{coord}{n}{plural}\s+{_STOP}|"
                                 rf"\b(?:arret|retrait|desactivation|desinstallation){_OF}{n}(?![a-z0-9_])"),
            # « X tourne » is a state, « X tourne sur Y » says what it runs on
            "actif": re.compile(rf"{lead}{n}{_AUX}\s+{_RUN}\b|{coord}{n}{plural}\s+{_RUN}|"
                                rf"{lead}{n}\s+(?:tourne|fonctionne)\b(?!\s+(?:sur|sous|avec|dans|grace|via|par|comme)\b)|"
                                rf"\b(?:relance|reactivation|remise en service|redemarrage){_OF}{n}(?![a-z0-9_])")}


MENTION_WINDOW = timedelta(days=90)


@lru_cache(maxsize=50000)
def _status_of(text: str, names: tuple) -> str | None:
    """The lifecycle family a statement gives to the project itself (one family only), or None."""
    folded = _fold(text or "").replace("’", "'")
    if not any(n in folded for n in names):
        return None
    fams = [f for f, rx in _status_rx(names).items() if rx.search(folded)]
    return fams[0] if len(fams) == 1 else None


def _mentions(conn, e: dict, keymap: dict[str, str], at: datetime | None, allowed: list[str]) -> list[dict]:
    """Status statements about this project made under another subject (attributes.projects names it): « Hermes est
    arrêté » said about W.Alter. Only facts and decisions that give the project itself a lifecycle state; each keeps
    its own subject."""
    labels = sorted(set(e["labels"]) | {e["name"]})
    t = at or datetime.now(timezone.utc)
    rows = conn.execute(f"""select {COLS} from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and kind in ('fact', 'decision')
          and (attributes->'projects') ?| %(labels)s and not ({SUBJ} = any(%(keys)s))
          and status = any(%(statuses)s) and (valid_to is null or valid_to > %(t)s)
          and coalesce(valid_from, created_at) between %(t)s - interval '90 days' and %(t)s
          and privacy_class = any(%(allowed)s)
        order by coalesce(valid_from, created_at) desc limit 150""",
        {"labels": labels, "keys": list(keymap), "t": t, "allowed": allowed,
         "statuses": list(knowledge.LIVE) + (["superseded"] if at else [])}).fetchall()
    names = tuple(sorted(n for n in {_fold(l) for l in labels} if len(n) >= 4))
    out = []
    for r in rows:
        r = dict(r)
        if not _status_of(r["content"], names):
            continue
        r.pop("nkey")
        r["project"] = None
        r["attributes"] = {"proof": r.pop("proof"), "contested": bool(r.pop("contested")),
                           "task_id": r.pop("task_id"), "progress": [x for x in [r.pop("last_step")] if x],
                           "task_status": r.pop("task_status")}
        r["fact"] = fact_date(r["content"], r["said"])
        r["from"] = r["fact"] or r["said"]
        if r["from"] <= t:
            out.append(r)
    return out


def _status(e: dict, items: list[dict], mentions: list[dict], linked: set[frozenset], now: datetime) -> dict | None:
    """The project's own lifecycle as memory states it: the latest status statement (own subject or mention), and
    whether earlier ones say otherwise without being linked to it — then the status is « not fully reconciled » and
    the latest text is not taken for verified unless Monsieur said it or it was checked."""
    names = tuple(sorted(n for n in {_fold(l) for l in [*e["labels"], e["name"]]} if len(n) >= 4))
    said = []
    for r in items + mentions:
        if r["kind"] not in ("fact", "decision") or now - r["from"] > MENTION_WINDOW:
            continue
        f = _status_of(r["content"], names)
        if f:
            said.append((r["from"], f, r))
    if not said:
        return None
    said.sort(key=lambda x: x[0], reverse=True)
    latest = said[0]
    others = [x for x in said[1:] if x[1] != latest[1]
              and frozenset((x[2]["item_id"], latest[2]["item_id"])) not in linked]
    sure = _rank(latest[2]) <= RANK["stated_owner"]
    return {"status": latest[1], "line": _line(latest[2]), "statements": len(said),
            "reconciled": not others, "sure": sure,
            "others": [_line(x[2], status=x[1]) for x in others[:3]], "others_count": len(others)}


def _counts(conn, keymap: dict[str, str], at: datetime | None, allowed: list[str]) -> dict[str, dict]:
    """Per project: current items, open goals of the last 30 days, contested items — counted by the database."""
    rows = conn.execute(f"""select {SUBJ} nkey, count(*) n,
            count(*) filter (where kind in ('goal', 'commitment') and coalesce(stage, '') not in
                             ('executed', 'verified', 'done', 'cancelled', 'abandoned')
                             and coalesce(valid_from, created_at) > %(t)s - interval '30 days') open_goals,
            count(*) filter (where (attributes->>'contested')::boolean) contested
        from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary' and {SUBJ} = any(%(keys)s)
          and status in ('derived', 'verified') and (valid_to is null or valid_to > %(t)s)
          and coalesce(valid_from, created_at) <= %(t)s and privacy_class = any(%(allowed)s)
        group by 1""", {"keys": list(keymap), "t": at or datetime.now(timezone.utc), "allowed": allowed}).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        o = out.setdefault(keymap[r["nkey"]], {"count": 0, "open_goals": 0, "contested": 0})
        for f in o:
            o[f] += r["n" if f == "count" else f]
    return out


def _who(r: dict) -> str:
    a = r.get("attributes") or {}
    if r.get("status") == "verified" or a.get("proof") in ("checked", "verified"):
        return "vérifié"
    return WHO.get(r.get("epistemic") or "", "?")


def _rank(r: dict) -> int:
    a = r.get("attributes") or {}
    if r.get("status") == "verified" or a.get("proof") in ("checked", "verified"):
        return RANK["verified"]
    return RANK.get(r.get("epistemic") or "", 6)


def _line(r: dict, **extra) -> dict:
    a = r.get("attributes") or {}
    return {"id": r["item_id"], "text": r["content"], "kind": r["kind"], "stage": r.get("stage"), "who": _who(r),
            "said": r["said"], "fact": r["fact"], "valid_to": r.get("valid_to"), "subject": r.get("subject"),
            "contested": bool(a.get("contested")), **extra}


def _last_step(r: dict) -> dict | None:
    steps = (r.get("attributes") or {}).get("progress") or []
    return steps[-1] if steps and isinstance(steps[-1], dict) else None


@lru_cache(maxsize=50000)
def _text_weight(text: str, names: tuple = ()) -> int:
    t = SELON.sub("", text or "")
    if names:                        # the project's own name is never a technical identifier
        t = re.sub(r"(?i)(?<![\w])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w])", "X", t) \
            if any(n in _fold(t) for n in names) else t
    w = -min(len(TECH.findall(t)), 4) + (2 if GLOBAL.search(t[:130]) else 0)     # a global word in the head
    return w - (1 if len(t) > 220 else 0)


@lru_cache(maxsize=50000)
def _is_test(text: str) -> bool:
    return bool(TEST.search(text or ""))


@lru_cache(maxsize=50000)
def _announces_next(text: str) -> bool:
    return bool(NEXT.search(text or ""))


@lru_cache(maxsize=50000)
def _named(text: str, names: tuple) -> bool:
    head = _fold(SELON.sub("", text or ""))[:90]
    return any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", head) for n in names)


def weight(r: dict, names: tuple = (), now: datetime | None = None) -> int:
    """How much a line says about the project as a whole: a state, proven, said by the owner, durable, naming the
    project or one of its sub-projects at its head, in plain words (no paths, ports, identifiers, commands) weighs
    more; a task's working detail weighs less. names = the folded labels of the project and its sub-projects."""
    a = r.get("attributes") or {}
    w = {"state": 2, "result": 1, "fact": 1}.get(r.get("act") or "", 0)
    if names and _named(r.get("content") or "", names):
        w += 1
    if r.get("status") == "verified" or a.get("proof") in ("checked", "verified"):
        w += 2
    if r.get("epistemic") == "stated_owner":
        w += 1
    if r.get("scope") == "task" or r.get("dom") == "task":
        w -= 3
    if now is not None and r.get("from"):         # the current era first: a still valid old detail weighs less
        age = (now - r["from"]).days
        w -= 2 if age > 120 else 1 if age > 30 else 0
    return w + _text_weight(r.get("content") or "", names)


def effective(r: dict) -> str:
    """The state of a goal as its evidence shows it: « proven » (verified, done), « claimed » (executed: an agent or
    the Run Plane says so, or its last recorded step says it was executed — never taken for a proof), « dropped »,
    else « open ». Read only: the stored stage moves only through the write gate, with its proof rule."""
    st = r.get("stage") or ""
    if r.get("status") == "verified" or st in PROVEN:
        return "proven"
    if st in DROPPED:
        return "dropped"
    step = _last_step(r)
    if st in CLAIMED or (step and step.get("stage") in ("executed", "verified") and step.get("act") != "runplane"):
        return "claimed"
    return "open"


@lru_cache(maxsize=50000)
def _stateful(text: str) -> bool:
    return bool(STATE_WORDS.search(text))


@lru_cache(maxsize=50000)
def _anchors(text: str, subject: str) -> tuple:
    return tuple(knowledge.anchors(text, subject))


def _chains(facts: list[dict], subject: str, linked: set[frozenset]) -> dict[str, list[dict]]:
    """Unreconciled chains: several current state statements naming the same thing, not linked to each other."""
    groups: dict[str, list[dict]] = {}
    horizon = max((r["from"] for r in facts), default=None)
    for r in facts:
        if horizon and horizon - r["from"] > CHAIN_WINDOW:
            continue
        if not _stateful(r["content"] or ""):
            continue
        names = _anchors((r["content"] or "")[:240], subject)
        if names:
            groups.setdefault(names[0].lower(), []).append(r)
    out = {}
    for name, rs in groups.items():
        if len(rs) < 2:
            continue
        lineages = {r["lineage_id"] for r in rs}
        ids = [r["item_id"] for r in rs]
        pairs_linked = sum(1 for i in range(len(ids)) for j in range(i + 1, len(ids))
                           if frozenset((ids[i], ids[j])) in linked)
        span = max(r["from"] for r in rs) - min(r["from"] for r in rs)
        if len(lineages) >= 2 and pairs_linked < len(rs) - 1 and span >= CHAIN_SPAN:
            out[name] = sorted(rs, key=lambda r: r["from"], reverse=True)
    return out


def _links(conn, ids: list[str]) -> tuple[set[frozenset], dict[str, list[dict]]]:
    """Derived links among these items: the linked pairs, and each contested item's other side."""
    if not ids:
        return set(), {}
    rows = conn.execute("""select target_id a, source_id b, role from core.provenance
                           where target_table = 'derived_items' and source_type = 'derived'
                             and (target_id in (select unnest(%s::text[])) or source_id in (select unnest(%s::text[])))""",
                        (ids, ids)).fetchall()
    linked, pairs = set(), []
    s = set(ids)
    for r in rows:
        linked.add(frozenset((r["a"], r["b"])))
        if r["role"] == "contradicts":
            me, o = (r["a"], r["b"]) if r["a"] in s else (r["b"], r["a"])
            pairs.append((me, o))
    other: dict[str, list[dict]] = {}
    if pairs:
        rows = conn.execute("""select item_id::text oid, content, coalesce(valid_from, created_at) said, epistemic,
                                      attributes->>'subject' subject, status from core.derived_items
                               where item_id = any(%s::uuid[])""", ([o for _, o in pairs],)).fetchall()
        by = {r["oid"]: r for r in rows}
        for me, o in pairs:
            if o in by:
                r = by[o]
                other.setdefault(me, []).append({"id": o, "text": r["content"], "said": r["said"], "status": r["status"],
                                                 "who": WHO.get(r["epistemic"] or "", "?"), "subject": r["subject"]})
    return linked, other


def _changes(conn, keymap: dict[str, str], since: datetime, until: datetime) -> list[dict]:
    """What changed in the window on this project's items: replaced states, advanced goals, new contradictions."""
    rows = conn.execute(f"""
        with ch as materialized (
            select change_id, at, op, verdict, item_id from core.derived_changes
            where reverted_at is null and not staged and at > %s and at <= %s
              and op in ('supersede', 'advance', 'contest'))
        select ch.at, ch.op, ch.verdict, x.id, x.content, x.by_id, x.nkey,
               case when ch.op = 'supersede' and x.by_id ~ '^[0-9a-f-]{{36}}$' then
                    (select n.content from core.derived_items n where n.item_id = x.by_id::uuid) end by_text,
               case when ch.op = 'advance' then
                    (select c2.after->>'stage' from core.derived_changes c2 where c2.change_id = ch.change_id) end stage
        from ch cross join lateral (
            select d.item_id::text id, d.content, d.attributes->>'superseded_by' by_id,
                   {SUBJ.replace("attributes", "d.attributes")} nkey
            from core.derived_items d
            where d.item_id = ch.item_id and d.derived_by = 'l3.extract' and d.generation = 'g1'
              and d.kind <> 'summary') x
        where x.nkey = any(%s)
        order by ch.at desc limit 200""", (since, until, list(keymap))).fetchall()
    out, seen = [], set()
    for r in rows:
        key = (r["op"], r["id"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"at": r["at"], "op": r["op"], "id": r["id"], "text": r["content"], "by": r["by_id"],
                    "by_text": r["by_text"], "stage": r["stage"], "project": keymap[r["nkey"]]})
    return out


def _task_status(conn, items: list[dict]) -> dict[str, str]:
    ids = [(r.get("attributes") or {}).get("task_id") for r in items]
    ids = [i for i in ids if i]
    if not ids:
        return {}
    try:
        rows = conn.execute("select task_id::text t, status from runs.tasks where task_id::text = any(%s)",
                            (ids,)).fetchall()
    except Exception:  # noqa: BLE001 — the Run Plane is optional here
        return {}
    return {r["t"]: r["status"] for r in rows}


_executor = None


def _side_pool():
    global _executor
    if _executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _executor = ThreadPoolExecutor(2, thread_name_prefix="projection")
    return _executor


def _with_conn(fn):
    with connection() as c:
        return fn(c)


def _keymap(cat: dict, keys: list[str]) -> dict[str, str]:
    """{normalised subject: project key} for these projects and their aliases."""
    cfg = _config()
    out = {k: k for k in keys}
    out.update({a: v for a, v in cfg["aliases"].items() if v in out})
    out.update({a: v for a, v in cfg["subjects"].items() if v in out})
    return out


def goal_buckets(rows: list[dict], tasks: dict[str, str], names: tuple, now: datetime) -> dict:
    """Goals and commitments by what their evidence shows (effective): achieved and verified, announced done (not
    verified), really under way (an open Run Plane objective or a step in the last ACTIVE days), blocked, without
    news (a step long ago, no open objective: status unknown), taken up but not started (open), requested without
    any trace (counted). Test requests are counted only. Shared by the project and the personal projections."""
    goals = {"in_progress": [], "blocked": [], "open": [], "done": [], "claimed": [], "dropped": [], "stale": [],
             "not_followed": 0, "tests": 0, "requested": 0}
    for r in sorted(rows, key=lambda r: r["from"], reverse=True):
        if _is_test(r["content"]):
            goals["tests"] += 1
            continue
        step = _last_step(r)
        last = datetime.fromisoformat(step["at"]) if step and step.get("at") else r["from"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        task = tasks.get((r.get("attributes") or {}).get("task_id") or "")
        ln = _line(r, step=(step or {}).get("text"), step_at=last if step else None, task=task,
                   weight=weight(r, names, now), effective=effective(r))
        eff = ln["effective"]
        if eff == "proven":
            if now - last <= RECENT:
                goals["done"].append(ln)
        elif eff == "claimed":
            if now - last <= RECENT:
                goals["claimed"].append(ln)
        elif eff == "dropped":
            if now - last <= RECENT:
                goals["dropped"].append(ln)
        elif step and step.get("act") != "runplane" and BLOCKED.search(step.get("text") or "") \
                and now - last <= RECENT:
            goals["blocked"].append(ln)
        elif task in ("running", "open", "in_progress") or (step and now - last <= ACTIVE):
            goals["in_progress"].append(ln)
        elif r["stage"] == "in_progress" or step:
            goals["stale"].append(ln)
        elif r["kind"] == "commitment" or r["stage"] in ("accepted", "decided", "open"):
            goals["open"].append(ln)         # taken up, not started: a known next step
        elif now - r["from"] <= FOLLOWED:
            goals["requested"] += 1
        else:
            goals["not_followed"] += 1
    return goals


def project(key: str, *, at: datetime | str | None = None, max_privacy: str = "cloud_allowed",
            children: bool = True, conn=None, cat: dict | None = None) -> dict:
    """The state of a project now (or at `at`): structured sections of line dicts, its parent and sub-projects."""
    t0 = time.perf_counter()
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    now = at or datetime.now(timezone.utc)
    allowed = privacy.allowed_classes(max_privacy)
    own = conn is None
    stack = contextlib.ExitStack()
    if own:
        conn = stack.enter_context(connection())
    with stack:
        cat = cat if cat is not None else catalog(conn)
        k = resolve(key)
        e = cat.get(k)
        if e is None:
            return {"key": k, "error": f"aucun projet {k} (au moins {MIN_ITEMS} connaissances courantes)"}
        kids = e["children"] if children else []
        names = tuple(sorted({n for c in [k, *e["children"]] for lb in cat[c]["labels"]
                              if len(n := _fold(lb)) >= 3}))
        keymap = _keymap(cat, [k, *kids])
        kidmap = _keymap(cat, kids)

        def side(c):     # the sub-projects and the change log: on a second pooled connection when this one is ours
            return (_items(c, kidmap, at, allowed, since=now - CHILD_RECENT, notable=True) if kids else [],
                    _counts(c, kidmap, at, allowed) if kids else {}, _changes(c, keymap, now - RECENT, now))
        fut = None
        if own and kids:
            fut = _side_pool().submit(lambda: _with_conn(side))
        items = _items(conn, _keymap(cat, [k]), at, allowed)
        mentions = _mentions(conn, e, _keymap(cat, [k]), at, allowed)
        ids = [r["item_id"] for r in items]
        # links are needed only where they change what is shown: contested items, and the state statements that
        # chains and the status compare
        recentish = (at or datetime.now(timezone.utc)) - CHAIN_WINDOW
        need = [r["item_id"] for r in items if (r.get("attributes") or {}).get("contested")
                or (r["kind"] in ("fact", "decision") and r["from"] >= recentish)]
        linked, other = _links(conn, need + [r["item_id"] for r in mentions])
        tasks = _task_status(conn, items)
        recent_kids, kid_counts, allchanges = fut.result() if fut else side(conn)
        by_kind: dict[str, list[dict]] = {}
        from . import nature
        typed = nature.restitution_on()     # M3: filed by nature once known (an opinion is never a rule in force)
        for r in items:
            if typed and (r.get("attributes") or {}).get("act") in nature.NATURES:
                r = {**r, "content": nature.reader_text(r["content"], r.get("attributes"))}
                by_kind.setdefault(nature.reader_kind(r["kind"], r.get("attributes")), []).append(r)
            else:
                by_kind.setdefault(r["kind"], []).append(r)
        newest = lambda rs: sorted(rs, key=lambda r: r["from"], reverse=True)   # noqa: E731
        # objectives and tasks, by what their evidence shows (effective): achieved and verified, announced done
        # (not verified), really under way (an open Run Plane objective or a step in the last ACTIVE days), blocked,
        # without news (a step long ago, no open objective: status unknown), requested without any trace (counted)
        goals = goal_buckets(by_kind.get("goal", []) + by_kind.get("commitment", []), tasks, names, now)
        # decisions and rules in force; a proposal nobody took is counted, not shown as in force
        decisions, proposals = [], 0
        for r in by_kind.get("decision", []):
            if r["stage"] in IN_FORCE or (r["stage"] == "requested" and r["epistemic"] == "stated_owner") \
                    or r["kind"] != "decision":     # a statement filed here by its nature (M3): in force as stated
                decisions.append(r)
            elif r["stage"] not in DROPPED:
                proposals += 1
        decisions += [r for kd in RULE_KINDS for r in by_kind.get(kd, [])]
        # in force and important first: the owner's, decided, durable, in plain words; a task's working rule last
        decisions = sorted(decisions, key=lambda r: (_rank(r) > 1, -(weight(r, names, now) + (r["stage"] in IN_FORCE)
                                                                     + (r["kind"] == "decision")),
                                                     -r["from"].timestamp()))
        # the state: facts, newest in fact first, the reliable before the reported at equal weight; chains flagged
        facts = newest(by_kind.get("fact", []))
        chains = _chains(facts, e["name"], linked)
        in_chain = {r["item_id"]: name for name, rs in chains.items() for r in rs}
        state = []
        for r in facts:
            flags = []
            if r["item_id"] in in_chain:
                flags.append("incertain")
            if (r.get("attributes") or {}).get("contested"):
                flags.append("contesté")
            # a statement that announces a next step is shown there, not as the state
            state.append(_line(r, flags=flags, other=other.get(r["item_id"], []),
                               weight=weight(r, names, now) - 2 * _announces_next(r["content"])))
        # the global state first (weight), the newest at equal weight; contested lines after; every line is kept
        # (the render shows the global ones and counts the details)
        state.sort(key=lambda l: (bool(l["flags"]) and "contesté" in l["flags"], -l["weight"], -l["said"].timestamp()))
        # problems: contradictions (both sides), blocked goals, unreconciled chains, recent failures
        issues = []
        for r in items:
            if (r.get("attributes") or {}).get("contested") and other.get(r["item_id"]):
                issues.append({"type": "contradiction", **_line(r), "other": other[r["item_id"]]})
        seen_pairs = set()
        uniq = []
        for i in issues:
            pair = frozenset([i["id"], *[o["id"] for o in i["other"]]])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                uniq.append(i)
        issues = uniq
        for name, rs in chains.items():
            latest = rs[0]
            issues.append({"type": "chain", "name": name, "count": len(rs), "id": latest["item_id"],
                           "first": rs[-1]["from"], "last": latest["from"], "text": latest["content"],
                           "who": _who(latest), "ids": [r["item_id"] for r in rs]})
        issues += [{"type": "blocked", **g} for g in goals["blocked"]]
        status = _status(e, items, mentions, linked, now)
        if status and not status["reconciled"]:
            issues.insert(0, {"type": "status", "id": status["line"]["id"], **status})
        changes = [c for c in allchanges if c["project"] == k]
        # next steps: only what memory holds — commitments and goals taken up but not started, and the statements
        # that announce one (« prochaine étape », « reste à », « attend son go »), recent, never deduced
        nxt = goals["open"][:]
        seen_next = {l["id"] for l in nxt}
        for r in newest(facts + by_kind.get("decision", [])):
            if r["item_id"] not in seen_next and now - r["from"] <= FOLLOWED and _announces_next(r["content"]) \
                    and r["stage"] not in DONE | DROPPED and r["epistemic"] != "inferred" \
                    and r.get("act") != "hypothesis":
                nxt.append(_line(r, weight=weight(r, names)))
        # significant recent advances: goals achieved (verified) or announced done, and replaced states that weigh
        advances = [*goals["done"], *goals["claimed"]]
        out = {"key": k, "name": e["name"], "labels": e["labels"], "at": at, "count": len(items),
               "parent": ({"key": e["parent"], "name": cat[e["parent"]]["name"]} if e["parent"] else None),
               "status": status, "mentions": len(mentions), "mention_ids": [r["item_id"] for r in mentions],
               "sections": {"state": state, "goals": goals, "decisions": [_line(r) for r in decisions],
                            "proposals": proposals, "changes": changes, "issues": issues, "next": nxt,
                            "advances": advances},
               "children": [], "sources": ids}
        for c in kids:
            out["children"].append(_child(cat[c], kid_counts.get(c, {}), [r for r in recent_kids if r["project"] == c],
                                          [x for x in allchanges if x["project"] == c], now))
        out["watermark"] = max((r["created_at"] for r in items), default=None)
        out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out


CHILD_PRIORITY = {"bloqué": 0, "décision de Monsieur": 1, "réalisé, vérifié": 2, "annoncé terminé, non vérifié": 3,
                  "contesté": 4}


def _child(e: dict, counts: dict, items: list[dict], changes: list[dict], now) -> dict:
    """What a sub-project brings up to its parent: its counts and at most its most important recent items — a blocked
    goal, a contradiction, an owner decision, a done goal, a replaced state. Never its technical facts."""
    important = []
    for r in items:
        if now - r["from"] > CHILD_RECENT:
            continue
        a = r.get("attributes") or {}
        step = _last_step(r)
        goal = r["kind"] in ("goal", "commitment")
        if goal and _is_test(r["content"]):
            continue
        eff = effective(r) if goal else None
        if goal and eff == "open" and step and step.get("act") != "runplane" and BLOCKED.search(step.get("text") or ""):
            important.append(("bloqué", r))
        elif r["kind"] == "decision" and r["epistemic"] == "stated_owner" and r["stage"] not in DROPPED:
            important.append(("décision de Monsieur", r))
        elif eff == "proven":
            important.append(("réalisé, vérifié", r))
        elif eff == "claimed":
            important.append(("annoncé terminé, non vérifié", r))
        elif a.get("contested"):
            important.append(("contesté", r))
    important.sort(key=lambda x: (CHILD_PRIORITY[x[0]], -weight(x[1]), -x[1]["from"].timestamp()))
    changes = [c for c in changes if c["op"] == "supersede" and now - c["at"] <= CHILD_RECENT]
    return {"key": e["key"], "name": e["name"], "count": counts.get("count", 0),
            "open_goals": counts.get("open_goals", 0), "contested": counts.get("contested", 0),
            "important": [{"why": w, **_line(r)} for w, r in important[:4]], "changes": changes[:3]}


# ───────────────────────────── rendering ─────────────────────────────
def _tokens(text: str) -> int:
    return len(text) // 4 + 1


SELON = re.compile(r"^(selon|d'après) (w\.?alter|walter)\s*,\s*", re.I)


def _short(text: str, n: int = 140) -> str:
    text = SELON.sub("", re.sub(r"\s+", " ", text or "").strip())     # « rapporté par W.Alter » already says it
    text = text[:1].upper() + text[1:]
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + " …"


def _dates(l: dict) -> str:
    said, fact = l.get("said"), l.get("fact")
    s = f"dit {_d(said)}" if not fact or abs((said - fact).days) < 1 else f"fait {_d(fact)}, dit {_d(said)}"
    if l.get("valid_to"):
        s += f", valable → {_d(l['valid_to'])}"
    return s


def _fmt(l: dict, n: int = 140) -> str:
    return f"« {_short(l['text'], n)} » ({_dates(l)} · {l['who']} · {l['id'][:8]})"


# the order of the sections, and the lines each one is sure to get before any other takes more
# (owner, 19/11): the global state, the significant recent advances, the decisions in force, the work really under
# way, the blocks, the known next steps; then the sub-projects' important lines. The technical details are counted.
ORDER = ("state", "advances", "decisions", "goals", "issues", "next", "children")
FLOOR = {"state": 3, "advances": 2, "decisions": 2, "goals": 2, "issues": 1, "next": 1, "children": 1}
STATE_LINES = 5


def names_of(p: dict) -> set:
    return {_fold(x) for x in [p.get("name") or "", *(p.get("labels") or []), *[c["name"] for c in p.get("children") or []]]}


def render(p: dict, max_tokens: int = 900) -> tuple[str, list[str]]:
    """The projection as text within the budget → (text, ids of the items shown). Every section first gets one line,
    then a few (FLOOR), then the remaining budget goes to more lines in the order of ORDER; sections keep their order."""
    if p.get("error"):
        return p["error"], []
    s = p["sections"]
    g = s["goals"]
    when = f"au {_d(p['at'])}" if p.get("at") else "maintenant"
    head = [f"Projet {p['name']} (`{p['key']}`) — état {when} ({p['count']} connaissances valables ; rien d'expiré "
            f"n'est présenté comme courant)."]
    if p.get("parent"):
        head.append(f"Sous-projet de {p['parent']['name']} (`{p['parent']['key']}`).")
    blocks: dict[str, tuple[str, list[tuple[str, str | None]], list[str]]] = {}   # title, [(line, id)], always-lines

    def fmt_state(l):
        x = f"- {_fmt(l, 110)}"
        if "incertain" in l.get("flags", []):
            x += " — incertain (voir Blocages)"
        for o in (l.get("other") or [])[:1]:
            x += f"\n  ⚠ contesté par : « {_short(o['text'], 110)} » ({_d(o['said'])} · {o['who']} · {o['id'][:8]})"
        return x
    glob = [l for l in s["state"] if l.get("weight", 0) >= STATE_MIN][:STATE_LINES]
    if len(glob) < FLOOR["state"]:          # a small project: its best lines in plain words, never a technical detail
        glob += [l for l in s["state"] if 0 <= l.get("weight", 0) < STATE_MIN][:FLOOR["state"] - len(glob)]
    st_lines = [(fmt_state(l), l["id"]) for l in glob]
    sts = p.get("status")
    if sts:
        l = sts["line"]
        own = knowledge.subject_key(l.get("subject") or "") in set(_keymap({}, [p["key"]]))
        where = "" if own else f", sujet {l.get('subject')}"
        trust = ("" if sts["reconciled"] and sts["sure"] else
                 " — non vérifié" + ("" if sts["reconciled"] else ", contredit par des énoncés non reliés (voir Problèmes)"))
        st_lines.insert(0, (f"- Statut : {sts['status']} selon le dernier énoncé « {_short(l['text'], 120)} » "
                            f"({_dates(l)} · {l['who']}{where} · {l['id'][:8]}){trust}", l["id"]))
    rest = len(s["state"]) - len(glob)
    blocks["state"] = ("État global", st_lines,
                       [f"- {rest} autres faits (détails techniques ou secondaires), consultables dans la mémoire"]
                       if rest > 0 else [])

    def fmt_goal(label, l, n=95, step_text=True, task=True):
        step = ""
        if l.get("step"):
            step = (f" — dernière étape {_d(l['step_at'])} : « {_short(l['step'], 65)} »" if step_text
                    else f" — dernière étape {_d(l['step_at'])}")
        run = f" — tâche Run Plane : {l['task']}" if task and l.get("task") else ""
        return f"- [{label}] {_fmt(l, n)}{step}{run}"
    adv = [(fmt_goal("réalisé, vérifié", l, 95, False, False), l["id"])
           for l in sorted(g["done"], key=lambda l: (-l["weight"], -l["said"].timestamp()))[:4]]
    adv += [(fmt_goal("annoncé terminé, non vérifié", l, 95, False), l["id"])
            for l in sorted(g["claimed"], key=lambda l: (-l["weight"], -l["said"].timestamp()))[:6]]

    def fmt_change(c):
        by = f" → « {_short(c['by_text'], 110)} »" if c.get("by_text") else ""
        return f"- {_d(c['at'])} · état remplacé : « {_short(c['text'], 100)} »{by} [{c['id'][:8]}]"
    # a replaced state that weighs (its new version in plain words): an advance; a change line cites the version in
    # force (the replacing one), never the replaced one as current
    sup = [c for c in s["changes"] if c["op"] == "supersede" and c.get("by_text")
           and _text_weight(c["by_text"]) >= 0]
    adv += [(fmt_change(c), c.get("by")) for c in sorted(sup, key=lambda c: -c["at"].timestamp())[:4]]
    blocks["advances"] = (f"Avancées récentes ({RECENT.days} jours)", adv,
                          [f"- en tout : {len(g['done'])} réalisés et vérifiés, {len(g['claimed'])} annoncés terminés "
                           f"sans vérification"] if len(g["done"]) + len(g["claimed"]) > 10 else [])
    gl = [(fmt_goal("bloqué", l), l["id"]) for l in g["blocked"][:4]]
    gl += [(fmt_goal("en cours", l), l["id"]) for l in g["in_progress"][:6]]
    gl += [(fmt_goal(f"sans nouvelle depuis le {_d(l['step_at'] or l['said'])}, statut inconnu", l), l["id"])
           for l in g["stale"][:2]]
    tail = [f"- aussi : {len(g['stale'])} sans nouvelle, {g['requested'] + g['not_followed']} demandes sans trace "
            f"d'exécution (statut inconnu, non listées)" + (f", {g['tests']} tests ignorés" if g["tests"] else "")]
    blocks["goals"] = ("Travaux en cours", gl, tail)
    more = len(s["decisions"]) - 8
    dt = [f"- aussi : {max(more, 0)} autres en vigueur, {s['proposals']} propositions non décidées (consultables)"] \
        if more > 0 or s["proposals"] else []
    blocks["decisions"] = ("Décisions importantes en vigueur", [(f"- {_fmt(l, 105)}", l["id"]) for l in s["decisions"][:8]],
                           dt)

    def fmt_issue(i):
        if i["type"] == "contradiction":
            o = i["other"][0]
            return (f"- contradiction non tranchée : « {_short(i['text'], 95)} » ({_d(i['said'])} · {i['who']}) ↔ "
                    f"« {_short(o['text'], 95)} » ({_d(o['said'])} · {o['who']}) [{i['id'][:8]} ↔ {o['id'][:8]}]")
        if i["type"] == "chain":
            return (f"- « {i['name']} » : {i['count']} énoncés non reliés ({_d(i['first'])} → {_d(i['last'])}), "
                    f"le dernier non tenu pour vérifié : « {_short(i['text'], 85)} » [{i['id'][:8]}]")
        if i["type"] == "status":
            o = i["others"][0]
            return (f"- statut non entièrement réconcilié : le dernier énoncé dit « {i['status']} » mais "
                    f"{i['others_count']} énoncé(s) non relié(s) disent autre chose, dont « {_short(o['text'], 100)} » "
                    f"({_d(o['said'])} · {o['who']} · {o['id'][:8]})")
        return f"- objectif bloqué : {_fmt(i, 105)} — « {_short(i.get('step'), 90)} »"
    # blocks first, then what weighs most (a contradiction on the project's state before one on a detail)
    iss = sorted(s["issues"], key=lambda i: ({"status": -1, "blocked": 0, "chain": 1, "contradiction": 2}[i["type"]],
                                             -_text_weight(i.get("text") or "")))
    # an unreconciled chain on a detail (not the project, not a sub-project, nothing that weighs) is counted only
    # and so is an old contradiction between two details
    recent = (p.get("at") or datetime.now(timezone.utc)) - RECENT
    shown_iss = [i for i in iss if (i["type"] != "chain" or (_fold(i["name"]) in names_of(p)
                                                             and _text_weight(i.get("text") or "") >= 0))
                 and (i["type"] != "contradiction" or i["said"] >= recent
                      or any(o["said"] >= recent for o in i["other"]))]
    iss_tail = len(iss) - min(len(shown_iss), 8)
    blocks["issues"] = ("Blocages et points non résolus", [(fmt_issue(i), i["id"]) for i in shown_iss[:8]],
                        [f"- aussi : {iss_tail} points non résolus sur des détails (contradictions, états non "
                         f"réconciliés), consultables"] if iss_tail > 0 else [])
    blocks["next"] = ("Prochaines étapes connues (engagements et étapes annoncées, pas encore commencées ; aucune "
                      "n'est déduite)", [(f"- {_fmt(l, 120)}", l["id"]) for l in s["next"][:6]], [])
    cl = []
    for c in p.get("children") or []:
        bits = [f"{c['count']} connaissances", f"{c['open_goals']} objectifs ouverts"]
        if c["contested"]:
            bits.append(f"{c['contested']} contestées")
        line = f"- {c['name']} : {', '.join(bits)}"
        imp = c["important"][:1]
        for i in imp:
            line += f" · {i['why']} : « {_short(i['text'], 90)} » ({_d(i['said'])} · {i['who']} · {i['id'][:8]})"
        for x in ([] if imp else c["changes"][:1]):
            line += f" · état remplacé le {_d(x['at'])} → « {_short(x.get('by_text') or '', 90)} »"
        cl.append((line, imp[0]["id"] if imp else None, [i["id"] for i in imp]))
    cl.sort(key=lambda x: not x[2])               # those with something to bring up first
    blocks["children"] = ("Sous-projets (avancées importantes seulement ; leur détail : leur propre état)",
                          [(x[0], x[1]) for x in cl[:8]], [f"- {len(cl)} sous-projets en tout"] if len(cl) > 2 else [])
    child_ids = {x[0]: x[2] for x in cl}
    foot = f"État à une date : memory_view(key=\"{p['key']}\", depth=\"state\", at=\"AAAA-MM-JJ\")."
    budget = max_tokens - _tokens("\n".join(head)) - _tokens(foot)
    take = {k: 0 for k in blocks}
    # a block's title and summary lines are paid with its first line: a block that does not fit costs nothing
    cost = {k: _tokens(f"### {blocks[k][0]}") + sum(_tokens(t) for t in blocks[k][2]) for k in blocks if blocks[k][1]}
    # every section first gets one line (none is crowded out by a long one before it), then its floor, then more
    for rnd in ("one", "floor", "more"):
        for k in ORDER:
            if k not in cost:
                continue
            lines = blocks[k][1]
            stop = {"one": 1, "floor": FLOOR[k]}.get(rnd, len(lines))
            while take[k] < min(stop, len(lines)):
                t = _tokens(lines[take[k]][0]) + (cost[k] if take[k] == 0 else 0)
                if t > budget:
                    break
                budget -= t
                take[k] += 1
    out, shown = list(head), []
    for k in ORDER:
        if k not in cost or not take[k]:
            continue
        title, lines, always = blocks[k]
        out.append(f"### {title}")
        for ln, i in lines[:take[k]]:
            out.append(ln)
            if k == "children":
                shown += child_ids.get(ln, [])
            elif i:
                shown.append(i)
        out += always
    out.append(foot)
    return "\n".join(out), list(dict.fromkeys(shown))


def read(q: dict) -> dict:
    """memory_view depth="state" (MemoryViewQuery v1): {key, depth, version, content, built_at, watermark, stale,
    sources, deeper}. `at` = an ISO date for the state as it was. Keys owner / now / me: the personal and
    situational projections (personal.py, lot P2); person:<name or id>: the relational state (relation.py, P3)."""
    from . import personal, relation
    if personal.kind_of(q.get("key") or ""):
        return personal.read(q)
    if relation.kind_of(q.get("key") or ""):          # person:<name or id> (lot P3)
        return relation.read(q)
    max_privacy = "cloud_allowed" if (q.get("privacy") or "cloud_allowed") == "cloud_allowed" else q["privacy"]
    p = project(q["key"], at=q.get("at"), max_privacy=max_privacy)
    if p.get("error"):
        return {"error": p["error"]}
    text, shown = render(p, int(q.get("max_tokens") or 900))
    return {"key": p["key"], "depth": "state", "version": None, "content": text,
            "built_at": datetime.now(timezone.utc), "watermark": p["watermark"], "stale": False,
            "sources": shown, "deeper": ["history"], "at": p["at"], "ms": p["ms"],
            "children": [c["key"] for c in p["children"]], "parent": (p["parent"] or {}).get("key")}


def listing() -> dict:
    """The catalog as a tree: each project, its spellings, its parent and sub-projects (CLI `state --list`)."""
    with connection() as conn:
        cat = catalog(conn, fresh=True)
    roots = sorted((e for e in cat.values() if not e["parent"]), key=lambda e: -e["count"])
    def node(e):
        return {"key": e["key"], "name": e["name"], "count": e["count"], "labels": sorted(e["labels"]),
                **({"children": [node(cat[c]) for c in e["children"]]} if e["children"] else {})}
    return {"projects": len(cat), "tree": [node(e) for e in roots]}


def check(keys: list[str] | None = None, *, at: str | None = None, limit_ms: float = 50.0) -> dict:
    """Invariants of the projection on real data (CLI `state --check`): every item it cites holds at the date (never
    an expired or replaced one as current), a parent cites none of its sub-projects' knowledge except the important
    lines it brings up, each line keeps its own subject, and the read stays under `limit_ms` once warm."""
    out, ok = [], True
    with connection() as conn:
        cat = catalog(conn, fresh=True)
        from . import personal, relation
        people = [k for k in keys or [] if relation.kind_of(k)]
        if people:
            r = relation.check(people, limit_ms=limit_ms)
            out += r["people"]
            ok = ok and r["ok"]
            keys = [k for k in keys if k not in people]
            if not keys:
                return {"ok": ok, "at": at, "projects": out}
        mine = [k for k in keys or [] if personal.kind_of(k)]
        if mine:
            c = personal.check(at=at)
            out.append(c)
            ok = ok and c["ok"]
            keys = [k for k in keys if k not in mine]
            if not keys:
                return {"ok": ok, "at": at, "projects": out}
        keys = [resolve(k) for k in keys] if keys else \
            [k for k, _ in sorted(((k, e["count"]) for k, e in cat.items() if not e["parent"]), key=lambda x: -x[1])[:5]]
        for k in keys:
            project(k, at=at, cat=cat)                                   # warm (parsing memo, plans)
            p = project(k, at=at, cat=cat)
            if p.get("error"):
                out.append({"key": k, "ok": False, "problems": [p["error"]]})
                ok = False
                continue
            text, shown = render(p)
            problems = []
            when = p["at"] or datetime.now(timezone.utc)
            rows = conn.execute("""select item_id::text id, status, valid_to, attributes->>'subject' subject
                                   from core.derived_items where item_id = any(%s::uuid[])""", (shown,)).fetchall()
            own = set(_keymap(cat, [k]))
            kids = set(_keymap(cat, p and cat[k]["children"]))
            brought = {i["id"] for c in p["children"] for i in c["important"]}
            mentioned = set(p.get("mention_ids") or []) | {c.get("by") for c in p["sections"]["changes"] if c.get("by")}
            for r in rows:
                if r["valid_to"] and r["valid_to"] <= when:
                    problems.append(f"{r['id'][:8]} expiré le {_d(r['valid_to'])} mais cité")
                if p["at"] is None and r["status"] not in knowledge.LIVE:
                    problems.append(f"{r['id'][:8]} {r['status']} cité comme courant")
                nk = knowledge.subject_key(r["subject"] or "")
                if nk not in own and not (nk in kids and r["id"] in brought) and r["id"] not in mentioned:
                    problems.append(f"{r['id'][:8]} sujet {r['subject']} hors du projet")
            if p["ms"] > limit_ms:
                problems.append(f"latence {p['ms']} ms > {limit_ms} ms")
            ok = ok and not problems
            out.append({"key": k, "name": p["name"], "ok": not problems, "ms": p["ms"], "items": p["count"],
                        "cited": len(shown), "children": [c["key"] for c in p["children"]],
                        "parent": (p["parent"] or {}).get("key"), "issues": len(p["sections"]["issues"]),
                        "tokens": _tokens(text), "problems": problems})
    return {"ok": ok, "at": at, "projects": out}
