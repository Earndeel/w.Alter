"""Which project a statement belongs to (owner, 2026-11-19: « une connaissance ne doit pas être attribuée à w.Alter
simplement parce qu'elle provient d'une session technique ou mentionne Walter »).

Everything is said to the assistant, so the extraction model tends to file under the assistant's own project
(`[attribution] assistant` in the instance's projects.toml) whatever a technical conversation is about: the owner's
television, his mailbox, another project. A statement stays under that project only when its text names it or one
of its sub-projects. Otherwise, deterministically and only when it is manifest:
  - it names another known project (and none of the assistant's) → that project;
  - it is about one of the owner's own things (« sa télévision », « sa boîte Gmail ») → no project (`other`);
  - in the same thread, it names the same thing as a statement moved by one of the rules above → moved with it.
Nothing else moves: a statement that names nothing keeps the model's choice (unknown is not wrong).

Used by the extraction before it writes (extract2), and by `fix()` over the knowledge already recorded: a change
`attribute` per item in core.derived_changes (tagged, undone by knowledge.revert), sources and history untouched."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache

from . import knowledge, projection
from .db import connection

log = logging.getLogger("walter_memory.attribution")

# One of the owner's own things, as a possession (« sa télévision », « ses abonnements », « sa boîte de réception »).
OWNER_THING = re.compile(
    r"(?<![a-z])(?:sa|son|ses)\s+(?:propre\s+|nouvelle?\s+)?(?:television|tele|tv|box|freebox|boite(?:\s+(?:mail|gmail|de reception))?|"
    r"messagerie|e-?mails?|mails|courriels?|voiture|appartement|maison|banque|compte bancaire|"
    r"telephone|iphone|smartphone|famille|parents|enfants|vacances|sante|medecin|impots|courses|"
    r"recherche d'emploi|candidatures?|cv)(?![a-z])")
HEAD = 110                           # where a statement says what it is about (« Le service X … », « Pour X, … »)
# Words that name something (a product, a device, a brand): carried by a moved statement to its thread neighbours
THING = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*[A-Z0-9][A-Za-z0-9]*|[A-Z][a-z]{2,}[A-Za-z0-9-]*)\b")
STOP_THINGS = {"monsieur", "pour", "dans", "avec", "selon", "elle", "il", "les", "des", "une", "aucun", "aucune",
               "cette", "apres", "avant", "depuis", "lors", "sans", "mais", "puis", "ensuite", "oui", "non", "walter",
               "alter", "le", "la", "un", "si", "au", "aux", "ce", "ces", "son", "sa", "ses", "on", "en", "et", "ou"}


def _fold(s: str) -> str:
    return projection._fold(s or "").replace("’", "'")


# The assistant as the speaker or the addressee of a statement is not its subject: « Selon W.Alter, … », « Monsieur
# demande à W.Alter de … », « W.Alter indique que … », « si W.Alter a accès à … ». Removed before the name check.
_A = r"(?:w\.?\s?alter|walter)"
_SPEAKER = re.compile(
    rf"(?:\b(?:selon|d'apres)\s+{_A}\s*,?|"
    rf"\b(?:demande|demandent|propose|autorise|permet|interdit|confie|charge|laisse|dit|explique|signale|repond)\s+"
    rf"(?:a|au|aux)\s+{_A}\b|"
    rf"\bsi\s+{_A}\s+(?:a|aura|peut|pourra|dispose)\b|"
    rf"\b{_A}\s+(?:n'|ne\s+)?(?:indique|explique|signale|propose|rapporte|precise|confirme|affirme|estime|"
    rf"recommande|suggere|annonce|constate|a constate)\b)")


def _topic(text: str) -> str:
    """The text without the assistant as speaker or addressee (folded)."""
    return _SPEAKER.sub(" ", _fold(text))


def family(cat: dict, root: str) -> set[str]:
    """The project and every sub-project under it (the catalog's hierarchy)."""
    out, todo = set(), [root]
    while todo:
        k = todo.pop()
        if k in out or k not in cat:
            continue
        out.add(k)
        todo += cat[k]["children"]
    return out


@lru_cache(maxsize=8)
def _names_rx(names: tuple) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(n) for n in names) + r")(?![a-z0-9])")


def _family_rx(cat: dict, fam: set[str]) -> re.Pattern:
    cfg = projection._config()
    names = {_fold(l) for k in fam for l in cat[k]["labels"]} | {_fold(cat[k]["name"]) for k in fam}
    names |= {_fold(a[len(projection.PREFIX):]) for a, v in cfg["aliases"].items() if v in fam}
    names |= {n.replace(".", "") for n in names} | {n.replace(".", " ") for n in names}
    return _names_rx(tuple(sorted((n for n in names if len(n) >= 3), key=len, reverse=True)))


class Rules:
    """The assistant's family and its names, read once per catalog."""

    def __init__(self, cat: dict, conn=None):
        self.cat = cat
        root = projection._config().get("assistant") or ""
        self.root = root if root in cat else None
        self.fam = family(cat, self.root) if self.root else set()
        self.rx = _family_rx(cat, self.fam) if self.fam else None
        bare = projection._config()["subjects"]
        self.keys = set(self.fam) | {k for k, v in bare.items() if v in self.fam}
        self.common, self.integrated = _common(conn, self) if conn is not None and self.rx else (set(), set())

    def carries(self, word: str) -> bool:
        """A thing a moved statement may carry to its thread: never one the assistant's own knowledge uses (Gmail,
        Beeper, Telegram are also connectors of the assistant)."""
        return word not in self.common

    def owns(self, subject: str | None) -> bool:
        """The subject is the assistant's project or one of its sub-projects (the bare subject included)."""
        if not self.root:
            return False
        k = knowledge.subject_key(subject or "")
        return k in self.keys or projection.resolve(subject or "") in self.fam

    def judge(self, text: str) -> tuple[str, str] | None:
        """(new subject, rule) when a statement filed under the assistant's project manifestly belongs elsewhere."""
        if not self.rx:
            return None
        t = _topic(text)
        if self.rx.search(t):
            return None
        head = projection.SELON.sub("", (text or "").strip())[:HEAD]     # the topic, not an incidental mention
        foreign = [k for k in projection.find_projects(head, cat=self.cat, limit=3)
                   if k not in self.fam and k not in self.integrated]
        if foreign:
            return projection.PREFIX + self.cat[foreign[0]]["name"], "names_other_project"
        if OWNER_THING.search(t):
            return "other", "owner_thing"
        return None


_common_memo: dict = {}


def _common(conn, rules: "Rules") -> tuple[set[str], set[str]]:
    """The assistant's own vocabulary, from the current statements that name it (kept 10 min): the things at least
    two of them name, and the other projects at least three of them name too (its tools and runtimes — Hermes,
    Claude Code — are part of its own work, not another home)."""
    import time
    m = _common_memo.get(rules.root)
    if m and time.monotonic() - m[0] < 600:
        return m[1]
    rows = conn.execute(f"""select content from core.derived_items where derived_by = 'l3.extract' and generation = 'g1'
        and kind <> 'summary' and status = any(%s) and {projection.SUBJ} = any(%s)""",
                        (list(knowledge.LIVE), sorted(rules.keys))).fetchall()
    n: dict[str, int] = {}
    co: dict[str, int] = {}
    for r in rows:
        if rules.rx.search(_topic(r["content"])):
            for w in things(r["content"]):
                n[w] = n.get(w, 0) + 1
            for k in projection.find_projects(r["content"], cat=rules.cat, limit=4):
                if k not in rules.fam:
                    co[k] = co.get(k, 0) + 1
    out = ({w for w, c in n.items() if c >= 2}, {k for k, c in co.items() if c >= 3})
    _common_memo[rules.root] = (time.monotonic(), out)
    return out


def things(text: str) -> set[str]:
    return {w.lower() for w in THING.findall(text or "") if w.lower() not in STOP_THINGS and len(w) >= 3}


def assign(rules: Rules, items: list[dict]) -> dict[int, tuple[str, str]]:
    """{index: (subject, rule)} for the items of ONE thread (dicts with "text", "subject") that move. The thread rule:
    a statement that names none of the assistant's names but names the same thing as a moved one follows it."""
    moved: dict[int, tuple[str, str]] = {}
    for i, it in enumerate(items):
        if rules.owns(it.get("subject")):
            got = rules.judge(it.get("text") or "")
            if got:
                moved[i] = got
    if not moved:
        return moved
    carried: dict[str, str] = {}
    for i, (subj, _) in moved.items():
        for w in things(items[i].get("text") or ""):
            if rules.carries(w):
                carried.setdefault(w, subj)
    for _ in range(2):                    # a thing named by a follower carries one step further
        for i, it in enumerate(items):
            if i in moved or not rules.owns(it.get("subject")) or rules.rx.search(_topic(it.get("text") or "")):
                continue
            shared = [carried[w] for w in things(it.get("text") or "") if w in carried]
            if shared:
                moved[i] = (shared[0], "same_thing_in_thread")
                for w in things(it.get("text") or ""):
                    if rules.carries(w):
                        carried.setdefault(w, shared[0])
    return moved


def project_id(subject: str) -> str | None:
    from .extract2 import project_id as pid
    return pid(subject[len(projection.PREFIX):]) if subject.lower().startswith(projection.PREFIX) else None


def fix(*, apply: bool = False, limit: int = 100000) -> dict:
    """The knowledge already recorded: current g1 items filed under the assistant's project that the rules move.
    Dry run unless apply. Each move = one change `attribute` (tag attribution-AAAA-MM-JJ), the former attribution
    kept in attributes.attribution; sources, lineage and history are untouched."""
    with connection() as conn:
        cat = projection.catalog(conn, fresh=True)
        rules = Rules(cat, conn)
        if not rules.root:
            return {"error": "aucun projet [attribution] assistant dans projects.toml"}
        rows = conn.execute(f"""select item_id::text id, content, attributes, source_refs->>'thread' thread
            from core.derived_items where derived_by = 'l3.extract' and generation = 'g1' and kind <> 'summary'
              and status = any(%s) and {projection.SUBJ} = any(%s) order by created_at limit %s""",
                            (list(knowledge.LIVE), sorted(rules.keys), limit)).fetchall()
    by_thread: dict[str, list[dict]] = {}
    for r in rows:
        by_thread.setdefault(r["thread"] or r["id"], []).append(
            {"id": r["id"], "text": r["content"], "subject": (r["attributes"] or {}).get("subject"),
             "attributes": r["attributes"] or {}})
    moves = []
    for th, its in by_thread.items():
        for i, (subj, rule) in assign(rules, its).items():
            moves.append((its[i], subj, rule, th))
    out = {"items": len(rows), "threads": len(by_thread), "moves": len(moves), "rules": {}, "to": {}, "applied": 0,
           "executed": apply}
    for _, subj, rule, _ in moves:
        out["rules"][rule] = out["rules"].get(rule, 0) + 1
        out["to"][subj] = out["to"].get(subj, 0) + 1
    out["to"] = dict(sorted(out["to"].items(), key=lambda x: -x[1])[:20])
    if not apply:
        out["sample"] = [{"id": it["id"][:8], "rule": rule, "to": subj} for it, subj, rule, _ in moves[:12]]
        return out
    tag = f"attribution-{datetime.now(timezone.utc):%Y-%m-%d}"
    changed = []
    with connection() as conn:
        gate = knowledge.Gate(conn, generation="g1", tag=tag, segment=None, where=None)
        for it, subj, rule, _ in moves:
            a = dict(it["attributes"])
            a["attribution"] = {"from": a.get("subject"), "from_project": a.get("project"), "rule": rule,
                                "at": datetime.now(timezone.utc).isoformat()}
            a["subject"] = subj
            pid = project_id(subj)
            if pid:
                a["project"], a["projects"] = pid, [pid]
            else:
                a.pop("project", None)
                a["projects"] = []
            if subj == "other" and a.get("domain") == "project":
                a["domain"] = "personal" if rule == "owner_thing" else a.get("domain")
            res = gate.change(it["id"], {"attributes": a}, op="attribute", key=f"attribution:{it['id']}:{subj}",
                              decided_by=f"deterministic:{rule}", reason=f"{a['attribution']['from']} → {subj}")
            if res == "applied":
                changed.append(it["id"])
    out["applied"] = len(changed)
    out["tag"] = tag
    if changed:
        try:
            from . import search
            search.reindex_derived(changed)
        except Exception as e:  # noqa: BLE001 — derived: the index catches up
            log.warning("reindex after attribution failed: %s", e)
    projection._catalog_memo.clear()
    return out


def for_segment(items: list[dict], conn) -> int:
    """The extraction's statements of one segment, before they are written (extract2): moved in place (subject,
    project, attributes.attribution). Returns how many moved."""
    try:
        rules = Rules(projection.catalog(conn), conn)
    except Exception as e:  # noqa: BLE001 — never lose an extraction for its attribution
        log.warning("attribution rules unavailable: %s", e)
        return 0
    if not rules.root:
        return 0
    moved = assign(rules, [{"text": it["text"], "subject": it["subject"]} for it in items])
    for i, (subj, rule) in moved.items():
        it = items[i]
        it["attribution"] = {"from": it["subject"], "from_project": it.get("project"), "rule": rule}
        it["subject"], it["project"] = subj, project_id(subj)
    return len(moved)


__all__ = ["Rules", "assign", "fix", "for_segment", "family", "json"]
