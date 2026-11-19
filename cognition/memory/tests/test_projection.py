"""Current-state projections (PROJECTIONS.md, lot P1), test database: a projection is a read of versioned knowledge —
a sub-project keeps its own state and brings up to its parent only its important lines, with their attribution; an
expired or replaced item is never served as current, and `at=` finds the state as it was; contradictions and
unreconciled status statements are shown as such, never settled by their date; Context gets an « État courant »
section carved out of the knowledge budget, without repeating the project in free knowledge; no model is called."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import context, events, knowledge, llm, projection, search
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


def tag() -> str:
    return uuid.uuid4().hex[:6]


@pytest.fixture
def projects(monkeypatch):
    """A parent, a sub-project declared in the instance's [parents], no model anywhere."""
    x = tag()
    parent, child = f"Zeph{x}", f"Zeph{x} Core"
    norm = lambda s: knowledge.subject_key(projection.PREFIX + s)   # noqa: E731
    monkeypatch.setattr(projection, "_config", lambda: {"aliases": {}, "parents": {norm(child): norm(parent)},
                                                         "subjects": {}})
    projection._catalog_memo.clear()

    def no_model(*a, **k):
        raise AssertionError("a projection never calls a model")
    monkeypatch.setattr(llm, "chat", no_model)
    monkeypatch.setattr(llm, "decide", no_model)
    yield {"parent": parent, "child": child, "pkey": norm(parent), "ckey": norm(child), "x": x}
    projection._catalog_memo.clear()


def item(text, subject, at, *, kind="fact", stage="stated", epistemic="agent_reported", status="derived",
         valid_to=None, attrs=None):
    ev = events.record_events([{"event_type": "message.sent", "source": "claude_code", "source_account": "pytest",
                                "source_id": uuid.uuid4().hex, "thread_id": f"proj-{tag()}", "occurred_at": at,
                                "content": text, "privacy_class": "cloud_allowed"}])["event_ids"][0]
    with connection() as conn:
        r = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                processor_version, source_event_ids, source_refs, valid_from, valid_to, privacy_class,
                                generation, epistemic, stage)
                            values (%s, %s, %s, %s, 'l3.extract', '1', %s::uuid[], %s, %s, %s, 'cloud_allowed', 'g1',
                                    %s, %s) returning item_id::text""",
                         (kind, text, json.dumps({"subject": "project:" + subject, "state": "stated", **(attrs or {})}),
                          status, [ev], json.dumps({"ref": f"proj:{uuid.uuid4().hex}"}), at, valid_to, epistemic,
                          stage)).fetchone()["item_id"]
        conn.execute("update core.derived_items set lineage_id = item_id where item_id = %s", (r,))
    return r


def link(a, b, role):
    with connection() as conn:
        conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                        values ('derived_items', %s, 'derived', %s, %s) on conflict do nothing""", (a, b, role))


def filler(subject, n, days=2):
    return [item(f"Le composant n°{i} de {subject} utilise la bibliothèque b{i}", subject, NOW - timedelta(days=days, hours=i))
            for i in range(n)]


def test_sub_project_keeps_its_state_and_brings_up_only_important_lines_to_its_parent(projects):
    p, c = projects["parent"], projects["child"]
    filler(p, 5)
    technical = filler(c, 5)
    decided = item(f"Monsieur décide que {c} garde un journal par jour", c, NOW - timedelta(days=1), kind="decision",
                   stage="decided", epistemic="stated_owner")

    child = projection.project(c)
    assert child["parent"] == {"key": projects["pkey"], "name": p}
    assert set(technical) <= set(child["sources"]) and decided in child["sources"]
    text, _ = projection.render(child)
    assert f"Sous-projet de {p}" in text and f"{c} utilise" in text

    parent = projection.project(p)
    kids = {k["key"]: k for k in parent["children"]}
    assert set(kids) == {projects["ckey"]}
    k = kids[projects["ckey"]]
    assert k["count"] == 6 and [i["id"] for i in k["important"]] == [decided]
    assert k["important"][0]["why"] == "décision de Monsieur" and k["important"][0]["who"] == "Monsieur"
    # the parent's own reading holds none of the child's knowledge; the child's technical facts never come up
    assert not (set(technical) | {decided}) & set(parent["sources"])
    text, shown = projection.render(parent)
    assert "journal par jour" in text and not set(technical) & set(shown)
    assert f"{c} utilise" not in text and f"{p} utilise" in text
    chk = projection.check([p, c], limit_ms=5000)
    assert chk["ok"], chk


def test_expired_and_replaced_items_are_never_current_and_at_finds_the_former_state(projects):
    p = projects["parent"]
    filler(p, 5, days=1)
    old = item(f"{p} écoute sur le port 8080", p, NOW - timedelta(days=10), status="superseded",
               valid_to=NOW - timedelta(days=3))
    new = item(f"{p} écoute sur le port 9090", p, NOW - timedelta(days=3))
    link(new, old, "supersedes")
    expired = item(f"Pendant la migration, {p} reste en lecture seule", p, NOW - timedelta(days=6),
                   kind="constraint", valid_to=NOW - timedelta(hours=6))

    now = projection.project(p)
    assert new in now["sources"] and old not in now["sources"] and expired not in now["sources"]
    text, _ = projection.render(now)
    assert "9090" in text and "8080" not in text and "lecture seule" not in text

    then = projection.project(p, at=(NOW - timedelta(days=5)).isoformat())
    assert old in then["sources"] and expired in then["sources"] and new not in then["sources"]
    text, _ = projection.render(then)
    assert "8080" in text and "9090" not in text and "état au " in text
    assert projection.check([p], at=(NOW - timedelta(days=5)).isoformat(), limit_ms=5000)["ok"]

    # the MCP / contract read: memory_view depth="state" with at=
    from walter_memory import views
    v = views.read({"depth": "state", "key": "project:" + p, "at": (NOW - timedelta(days=5)).isoformat()})
    assert v["depth"] == "state" and old in v["sources"] and "8080" in v["content"]


def test_contradictions_and_unreconciled_status_are_shown_never_settled_by_date(projects):
    p = projects["parent"]
    filler(p, 5)
    a = item(f"Les sauvegardes de {p} partent chaque nuit", p, NOW - timedelta(days=2), attrs={"contested": True})
    b = item(f"Les sauvegardes de {p} partent chaque semaine", p, NOW - timedelta(days=1), attrs={"contested": True})
    link(b, a, "contradicts")
    stop = item(f"{p} est arrêté depuis le {(NOW - timedelta(days=6)).day} {knowledge_month(NOW - timedelta(days=6))}",
                p, NOW - timedelta(days=5))
    run = item(f"{p} est de nouveau actif", p, NOW - timedelta(days=1))

    r = projection.project(p)
    issues = r["sections"]["issues"]
    contra = [i for i in issues if i["type"] == "contradiction"]
    assert len(contra) == 1 and {contra[0]["id"], *[o["id"] for o in contra[0]["other"]]} == {a, b}
    st = r["status"]
    assert st["status"] == "actif" and st["line"]["id"] == run and not st["reconciled"] and not st["sure"]
    assert issues[0]["type"] == "status"
    text, _ = projection.render(r)
    assert "non vérifié" in text and "contredit par des énoncés non reliés" in text
    assert "chaque nuit" in text and "chaque semaine" in text
    # the fact date of the stop is the one the text gives, not the day it was said
    stop_line = next(l for l in r["sections"]["state"] if l["id"] == stop)
    assert stop_line["fact"] is not None and stop_line["fact"] < stop_line["said"]

    link(run, stop, "supersedes")            # once the evolution is linked, the status is reconciled
    assert projection.project(p)["status"]["reconciled"]


def knowledge_month(d):
    return list(projection.MONTHS)[d.month - 1]


def test_fact_date_and_lifecycle_phrases():
    said = datetime(2026, 11, 18, tzinfo=timezone.utc)
    assert projection.fact_date("Hermes est arrêté depuis le 10 novembre", said) == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert projection.fact_date("retiré le 16/11", said) == datetime(2026, 11, 16, tzinfo=timezone.utc)
    assert projection.fact_date("la livraison est prévue le 25 novembre", said) is None      # a plan
    assert projection.fact_date("migré le 20 décembre", datetime(2026, 1, 5, tzinfo=timezone.utc)) == \
        datetime(2025, 12, 20, tzinfo=timezone.utc)
    assert projection.fact_date("sans date", said) is None
    n = ("hermes",)
    assert projection._status_of("Hermes est arrêté", n) == "arrêté"
    assert projection._status_of("Hermes n'est plus utilisé en production", n) == "arrêté"
    assert projection._status_of("Après l'arrêt d'Hermes, le moteur natif sert tout", n) == "arrêté"
    assert projection._status_of("Hermes est de nouveau actif", n) == "actif"
    assert projection._status_of("L'outil ask_hermes a été retiré", n) is None          # an identifier
    m = ("memory",)
    assert projection._status_of("La purge Memory a retiré 121 doublons", m) is None   # the agent of an action
    assert projection._status_of("L'extraction Memory fonctionne", m) is None          # after a noun
    assert projection._status_of("L'extraction continue de Walter Memory est active", ("walter memory",)) is None
    assert projection._status_of("W.Alter tourne sur DSH installé tel quel", ("w.alter",)) is None   # runs on
    assert projection._status_of("Le service W.Alter tourne", ("w.alter",)) == "actif"


def test_context_serves_the_state_section_carved_from_knowledge_without_repeating_the_project(projects, monkeypatch):
    monkeypatch.setattr(search, "_rerank", lambda q, results, limit, timeout=8: results[:limit])
    p = projects["parent"]
    ids = filler(p, 5) + [item(f"{p} tourne sur le serveur Orme{projects['x']}", p, NOW - timedelta(hours=5))]
    search.index_pending()
    budget = {"knowledge": 600, "views": 200, "records": 0, "evidence": 0, "people": 0, "tasks": 0,
              "experience": 0, "working": 0, "rules": 0}
    out = context.get_context(f"Où en est {p} ?", budget=budget, include_profile=False)
    plan = out["trace"]["state_plan"]
    assert plan["key"] == projects["pkey"] and plan["budget"] == int(600 * context.STATE_SHARE) + 200
    sec = out["trace"]["sections"]["state"]
    assert "state" in out["sections"] and 0 < sec["tokens"] <= plan["budget"]
    assert out["text"].index("État courant") < (out["text"].index("Connaissances") if "Connaissances" in out["text"]
                                                 else len(out["text"]))
    # free knowledge does not repeat the projected project
    free = out["sections"].get("knowledge") or ""
    assert f"Orme{projects['x']}" not in free and f"{p} utilise" not in free
    # a question that names no project, or asks no state, gets no section and keeps its whole budget
    other = context.get_context("Quel temps fera-t-il demain ?", budget=budget, include_profile=False)
    assert "state" not in other["sections"] and "state_plan" not in other["trace"]
