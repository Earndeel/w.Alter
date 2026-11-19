"""Attribution of knowledge (owner, 19/11: « une connaissance ne doit pas être attribuée à w.Alter simplement parce
qu'elle provient d'une session technique ou mentionne Walter »): the assistant as speaker or addressee is not a
subject; a statement whose head names another project, or one of the owner's own things, leaves the assistant's
project; its thread neighbours that name the same thing follow it; the assistant's own tools stay. Existing items
are moved through the write gate (op attribute), sources untouched, reversible by tag. No model is called."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import attribution, events, knowledge, llm, projection
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


def tag() -> str:
    return uuid.uuid4().hex[:6]


def entry(key, name, parent=None, children=()):
    return {"key": key, "name": name, "labels": {name: 10}, "count": 10, "parent": parent, "children": list(children)}


@pytest.fixture
def rules(monkeypatch):
    cat = {"project:walter": entry("project:walter", "W.Alter", children=["project:waltermemory"]),
           "project:waltermemory": entry("project:waltermemory", "Walter Memory", parent="project:walter"),
           "project:vela": entry("project:vela", "Vela"),
           "project:outilx": entry("project:outilx", "OutilX")}
    monkeypatch.setattr(projection, "_config", lambda: {"aliases": {}, "parents": {}, "subjects": {},
                                                         "assistant": "project:walter"})
    return attribution.Rules(cat)


def test_the_assistant_as_speaker_or_addressee_is_not_the_subject(rules):
    # said to W.Alter, about the owner's television: not W.Alter's knowledge
    assert rules.judge("Monsieur demande à W.Alter pourquoi sa télévision ne capte plus la TNT") == ("other", "owner_thing")
    assert rules.judge("Selon W.Alter, sa boîte mail reçoit trop de publicités") == ("other", "owner_thing")
    # about W.Alter itself or one of its modules: stays, even when W.Alter reports it
    assert rules.judge("Selon W.Alter, le service W.Alter redémarre en deux secondes") is None
    assert rules.judge("Walter Memory garde sa boîte de réception en lecture seule") is None
    # another project named at the head: its own subject
    assert rules.judge("Le projet Vela expose une API de réservation, selon W.Alter") == ("project:Vela",
                                                                                          "names_other_project")
    # a project named far from the head is an incidental mention, not the topic
    assert rules.judge("Monsieur veut un tableau de bord sobre sur fond noir avec des cartes claires et des "
                       "boutons larges, et des couleurs comme celles que l'on trouve dans Vela") is None


def test_the_assistants_own_tools_stay_and_thread_neighbours_follow_a_move(rules):
    rules.integrated = {"project:outilx"}      # a tool W.Alter's own knowledge names often (Hermes, Claude Code…)
    assert rules.judge("OutilX lance les sous-agents de W.Alter en parallèle") is None
    items = [{"text": "Monsieur demande à W.Alter de régler sa télévision Orionpix qui ne s'allume plus",
              "subject": "project:walter"},
             {"text": "Orionpix redémarre en boucle après la mise à jour", "subject": "project:walter"},
             {"text": "W.Alter journalise chaque appel d'outil", "subject": "project:walter"},
             {"text": "Le même Orionpix affiche un écran noir", "subject": "project:vela"}]      # not the assistant's
    moved = attribution.assign(rules, items)
    assert moved == {0: ("other", "owner_thing"), 1: ("other", "same_thing_in_thread")}


def item(text, subject, thread, at):
    ev = events.record_events([{"event_type": "message.sent", "source": "claude_code", "source_account": "pytest",
                                "source_id": uuid.uuid4().hex, "thread_id": thread, "occurred_at": at,
                                "content": text, "privacy_class": "cloud_allowed"}])["event_ids"][0]
    with connection() as conn:
        r = conn.execute("""insert into core.derived_items (kind, content, attributes, status, derived_by,
                                processor_version, source_event_ids, source_refs, valid_from, privacy_class,
                                generation, epistemic, stage)
                            values ('fact', %s, %s, 'derived', 'l3.extract', '1', %s::uuid[], %s, %s, 'cloud_allowed',
                                    'g1', 'agent_reported', 'stated') returning item_id::text""",
                         (text, json.dumps({"subject": subject, "project": subject.split(":")[-1].lower(),
                                            "domain": "project"}),
                          [ev], json.dumps({"ref": f"attr:{uuid.uuid4().hex}", "thread": thread, "source": "claude_code"}),
                          at)).fetchone()["item_id"]
        conn.execute("update core.derived_items set lineage_id = item_id where item_id = %s", (r,))
    return r


def test_recorded_misattributions_are_moved_with_their_sources_and_reverted_by_tag(monkeypatch):
    x = tag()
    me, other = f"Zeph{x}", f"Vela{x}"
    monkeypatch.setattr(projection, "_config", lambda: {"aliases": {}, "parents": {}, "subjects": {},
                                                         "assistant": knowledge.subject_key("project:" + me)})
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model")))
    projection._catalog_memo.clear()
    attribution._common_memo.clear()
    th = f"attr-{x}"
    for i in range(5):
        item(f"{me} journalise le composant c{i}", "project:" + me, f"fill-{x}", NOW - timedelta(days=2))
        item(f"{other} publie la page p{i}", "project:" + other, f"fill-{x}", NOW - timedelta(days=2))
    tv = item(f"Le projet {other} affiche Orion{x} en page d'accueil", "project:" + me, th, NOW - timedelta(hours=3))
    follow = item(f"Orion{x} charge en quatre secondes", "project:" + me, th, NOW - timedelta(hours=2))
    mail = item("Monsieur veut que sa boîte mail soit triée chaque matin", "project:" + me, th, NOW - timedelta(hours=1))
    own = item(f"{me} redémarre en deux secondes", "project:" + me, th, NOW)
    with connection() as conn:
        before = {r["item_id"]: r["source_event_ids"] for r in conn.execute(
            "select item_id::text, source_event_ids from core.derived_items where item_id = any(%s::uuid[])",
            ([tv, follow, mail, own],))}

    dry = attribution.fix()
    assert dry["moves"] == 3 and not dry["applied"]
    done = attribution.fix(apply=True)
    assert done["applied"] == 3 and attribution.fix()["moves"] == 0          # idempotent
    with connection() as conn:
        rows = {r["item_id"]: r for r in conn.execute(
            """select item_id::text, attributes, source_event_ids, status from core.derived_items
               where item_id = any(%s::uuid[])""", ([tv, follow, mail, own],))}
    assert rows[tv]["attributes"]["subject"] == "project:" + other
    assert rows[tv]["attributes"]["attribution"]["from"] == "project:" + me
    assert rows[tv]["attributes"]["attribution"]["rule"] == "names_other_project"
    assert rows[follow]["attributes"]["subject"] == "project:" + other
    assert rows[follow]["attributes"]["attribution"]["rule"] == "same_thing_in_thread"
    assert rows[mail]["attributes"]["subject"] == "other" and rows[mail]["attributes"]["domain"] == "personal"
    assert rows[own]["attributes"]["subject"] == "project:" + me and "attribution" not in rows[own]["attributes"]
    assert all(rows[i]["source_event_ids"] == before[i] and rows[i]["status"] == "derived" for i in rows)
    ops = [c["op"] for c in knowledge.history(tv)["changes"]]
    assert ops[-1] == "attribute"

    knowledge.revert(done["tag"], confirm=True)
    with connection() as conn:
        subj = {r["item_id"]: r["s"] for r in conn.execute(
            "select item_id::text, attributes->>'subject' s from core.derived_items where item_id = any(%s::uuid[])",
            ([tv, follow, mail],))}
    assert set(subj.values()) == {"project:" + me}
    projection._catalog_memo.clear()
