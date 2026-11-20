"""The owner's conversations with his contacts go through the organic extraction (E2E 20/11, owner: « l'extraction doit
aussi traiter les messages entrants et sortants de mes contacts, y compris les transcriptions audio … sans créer un
nouveau système d'extraction relationnelle concurrent »), on the test database with a scripted model: a contact's newer
word replaces his older one (history kept), a received proposal stays a proposal with an awaited confirmation, the
person card and the relation state read that one canonical knowledge, a voice note is read through its transcript (and
waited for), a group is not read, a replay adds nothing, and nothing is sent or scheduled."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, extract2, relation, social
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)
MARK = "Messages à analyser (numérotés, seuls citables ; une note vocale ou un document est donné par sa transcription) :"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from walter_memory import search
    monkeypatch.setattr(search, "embed", lambda texts: (_ for _ in ()).throw(RuntimeError("no embedder in tests")))
    extract2.set_v1_start(NOW - timedelta(days=2))
    extract2.set_contacts_start(NOW - timedelta(days=2))
    yield


class Model:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, messages, **kw):
        prompt = messages[0]["content"]
        self.calls.append(prompt)
        part = prompt.split(MARK, 1)[1].split("\n\nRends un JSON", 1)[0]
        lines = [l for l in part.strip().splitlines() if re.match(r"^\d+\. \[", l)]
        known = dict(re.findall(r"^(K\d+)\. \[[^\]]+\] (.*)$", prompt, re.M))
        return {"content": json.dumps(self.answer(lines, known)), "cost_usd": 0.0, "model": "scripted",
                "usage": {"prompt_tokens": len(prompt) // 4}}


def contact(name=None):
    name = name or f"Testeur {uuid.uuid4().hex[:6]}"
    with connection() as conn:
        eid = conn.execute("""insert into core.entities (entity_type, canonical_name, aliases)
                              values ('person', %s, %s) returning entity_id::text""", (name, [name.lower()])).fetchone()["entity_id"]
        iid = events.upsert_identity(conn, "beeper", {"external_id": f"@{uuid.uuid4().hex[:8]}:pytest",
                                                       "account": "pytest", "display_name": name})
        conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method)
                        values (%s, %s, 'confirmed', 1.0, 'pytest')""", (iid, eid))
    return {"name": name, "entity": eid, "identity": iid}


def say(c, chat, who, text, *, at, chat_type="single", **extra):
    e = {"event_type": "message.sent" if who == "owner" else "message.received", "source": "beeper",
         "source_account": "pytest", "source_id": uuid.uuid4().hex, "thread_id": chat, "occurred_at": at,
         "content": text, "privacy_class": "cloud_allowed",
         "payload": {"chat": {"type": chat_type, "title": c["name"], "network": "whatsapp"}, **extra.pop("payload", {})},
         **extra}
    if who != "owner":
        e["actor_identity_id"] = c["identity"]
    return events.record_events([e])["event_ids"][0]


def lyon_then_paris(lines, known):
    items = []
    for i, l in enumerate(lines, 1):
        if "installé à Lyon" in l:
            items.append({"type": "fait", "author": "contact", "who": "contact", "domain": "relation",
                          "text": "Le contact vit à Lyon (Croix-Rousse).", "msgs": [i],
                          "quote": "je suis bien installé à Lyon"})
        if "quitté Lyon" in l:
            lyon = next((k for k, v in known.items() if "Lyon" in v), None)
            items += [{"type": "fait", "author": "contact", "who": "contact", "domain": "relation",
                       "text": "Le contact vit maintenant à Paris (il a quitté Lyon).", "msgs": [i],
                       "quote": "J'ai finalement quitté Lyon, je vis à Paris maintenant",
                       **({"supersedes": [lyon], "about": lyon} if lyon else {})},
                      {"type": "proposition", "author": "contact", "who": "contact", "domain": "relation",
                       "text": "Le contact propose à Monsieur de prendre un café le 12 décembre à Bangkok.", "msgs": [i],
                       "quote": "Ça te dit qu'on prenne un café le 12"},
                      {"type": "action", "author": "contact", "who": "contact", "domain": "relation", "stage": "annoncee",
                       "text": "Le contact doit confirmer à Monsieur le café du 12 décembre.", "msgs": [i],
                       "quote": "Je te confirmerai"}]
    return {"summary": "Nouvelles du contact.", "items": items}


def obj(text, at):
    sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with connection() as conn:
        return conn.execute("""insert into core.objects (sha256, size_bytes, mime, kind, storage_key, original_name,
                                   captured_at, source, privacy_class, derived_kind, derived_text)
                               values (%s, 1000, 'audio/ogg', 'audio', %s, 'PTT.ogg', %s, 'beeper', 'cloud_allowed',
                                       %s, %s) returning id::text""",
                            (sha, f"t/{sha}", at, "transcript" if text is not None else None, text)).fetchone()["id"]


def items_of(chat, status=("derived",)):
    with connection() as conn:
        return conn.execute("""select item_id::text, kind, content, status, stage, epistemic, attributes, subject_entity_ids
                               from core.derived_items where derived_by = 'l3.extract' and source_refs->>'thread' = %s
                                 and kind <> 'summary' and status = any(%s) order by created_at""",
                            (chat, list(status))).fetchall()


def test_a_contacts_voice_note_updates_his_knowledge_and_his_proposal_stays_a_proposal():
    c, chat = contact(), f"!pytest-{uuid.uuid4().hex[:8]}:beeper.local"
    model = Model(lyon_then_paris)
    say(c, chat, "contact", "Ça y est, je suis bien installé à Lyon ! L'appart est top.", at=NOW - timedelta(hours=5))
    say(c, chat, "owner", "Génial, profite bien !", at=NOW - timedelta(hours=5) + timedelta(minutes=3))
    r1 = extract2.process_thread("beeper", chat, chat=model, force=True)
    assert r1["segments"] == 1 and "et son contact" in model.calls[0] and c["name"] in model.calls[0]
    lyon = [i for i in items_of(chat) if "Lyon" in i["content"]]
    assert len(lyon) == 1 and lyon[0]["epistemic"] == "stated_third_party"
    assert lyon[0]["subject_entity_ids"] and str(lyon[0]["subject_entity_ids"][0]) == c["entity"]   # by entity, not name

    # the voice note: no text in the message, its words are the transcript of its file
    oid = obj("Salut ! J'ai finalement quitté Lyon, je vis à Paris maintenant. Je pense passer à Bangkok du 10 au "
              "14 décembre. Ça te dit qu'on prenne un café le 12 ? Je te confirmerai.", NOW - timedelta(hours=1))
    say(c, chat, "contact", None, at=NOW - timedelta(hours=1), object_refs=[oid],
        payload={"attachments": [{"type": "audio", "isVoiceNote": True}]})
    r2 = extract2.process_thread("beeper", chat, chat=model, force=True)
    assert r2["segments"] == 1 and "quitté Lyon" in model.calls[1]
    now_items = items_of(chat)
    paris = [i for i in now_items if "Paris" in i["content"]]
    assert len(paris) == 1 and str(paris[0]["subject_entity_ids"][0]) == c["entity"]
    assert not [i for i in now_items if "vit à Lyon" in i["content"]]                     # no longer current
    assert [i for i in items_of(chat, ("superseded",)) if "Lyon" in i["content"]]         # kept in history
    café = next(i for i in now_items if "café" in i["content"] and i["kind"] == "decision")
    assert café["stage"] == "proposed" and café["attributes"]["act"] == "proposal"         # never an accepted meeting
    attendu = next(i for i in now_items if i["kind"] == "commitment")
    assert attendu["stage"] == "open" and attendu["attributes"]["holder"] == "contact"     # a confirmation awaited

    # the relation state (P3) and the person card read that same knowledge, with its history
    s = relation.state(c["entity"], max_privacy="local_only")
    texts = [x["text"] for x in s["items"]["statements"] + s["items"]["plans"]]
    assert any("Paris" in t for t in texts) and not any("vit à Lyon" in t for t in texts)
    assert any("Lyon" in x["text"] and x["how"] == "remplacé" for x in s["items"]["history"])
    card = social.person_card(c["entity"])
    assert any("Paris" in x["text"] for x in card["knowledge"]["current"])
    assert any("Lyon" in x["text"] for x in card["knowledge"]["history"])

    # nothing sent, nothing scheduled; a replay adds nothing
    with connection() as conn:
        sent = conn.execute("select count(*) n from core.events where thread_id = %s and event_type = 'message.sent'",
                            (chat,)).fetchone()["n"]
    assert sent == 1
    before = len(items_of(chat, ("derived", "superseded")))
    r3 = extract2.process_thread("beeper", chat, chat=model, force=True)
    assert r3["segments"] == 0 and len(model.calls) == 2 and len(items_of(chat, ("derived", "superseded"))) == before


def test_a_voice_note_without_its_transcript_is_waited_for_and_a_group_is_not_read():
    c, chat = contact(), f"!pytest-{uuid.uuid4().hex[:8]}:beeper.local"
    oid = obj(None, NOW)
    say(c, chat, "contact", None, at=NOW - timedelta(minutes=1), object_refs=[oid],
        payload={"attachments": [{"type": "audio", "isVoiceNote": True}]})
    model = Model(lambda lines, known: {"summary": "", "items": []})
    r = extract2.process_thread("beeper", chat, chat=model, force=True)
    assert r["segments"] == 0 and r["waiting"] == 1 and not model.calls      # held, not covered
    group = f"!pytest-g-{uuid.uuid4().hex[:8]}:beeper.local"
    say(c, group, "contact", "On se fait un café le 12 ?", at=NOW - timedelta(hours=1), chat_type="group")
    assert extract2.process_thread("beeper", group, chat=model, force=True)["segments"] == 0 and not model.calls


def test_a_contact_never_replaces_what_another_person_said():
    from walter_memory import knowledge
    st = {"by_owner": False, "by_contact": True, "speaker_ids": ["a"], "text": "x", "kind": "fact", "act": "fact"}
    target = {"epistemic": "stated_third_party", "attributes": {"speaker_id": "b"}, "kind": "fact", "status": "derived"}
    assert knowledge.guard(st, "replaces", target, 0.95, 0.6) == ("contradicts", "other_speaker")
    target["attributes"]["speaker_id"] = "a"
    assert knowledge.guard(st, "replaces", target, 0.95, 0.6)[0] == "replaces"


def test_the_bus_marks_only_one_to_one_contact_conversations():
    c = contact()
    single, group = (f"!pytest-{k}-{uuid.uuid4().hex[:8]}:beeper.local" for k in ("s", "g"))
    e1 = say(c, single, "contact", "Salut", at=NOW)
    e2 = say(c, group, "contact", "Salut à tous", at=NOW, chat_type="group")
    evs = [{"subject": e, "payload": {"source": "beeper", "event_type": "message.received", "thread_id": t,
                                      "occurred_at": NOW.isoformat()}} for e, t in ((e1, single), (e2, group))]
    assert extract2.on_bus_events(evs) == 1
    with connection() as conn:
        marked = {r["thread_id"] for r in conn.execute(
            "select thread_id from extraction.threads where thread_id = any(%s)", ([single, group],)).fetchall()}
    assert marked == {single}


def test_a_contacts_proposal_without_any_reply_is_a_plan_whose_agreement_is_not_established():
    """The plans of a one-to-one burst where only the contact wrote are read too (« on pourrait prendre un café le 12,
    je te confirmerai »): stored « accord non établi » even if the model said accepted, never a reminder or a send."""
    from walter_memory import episodic, flows
    c, chat = contact(), f"!pytest-p-{uuid.uuid4().hex[:8]}:beeper.local"
    at = NOW - timedelta(hours=3)
    say(c, chat, "contact", "On pourrait prendre un café le 12 décembre à 15h, je te confirmerai.", at=at)
    flows.conversations(at - timedelta(minutes=5), thread=("beeper", chat))
    with connection() as conn:
        burst = conn.execute("""select item_id::text, attributes from core.derived_items where derived_by = 'flows.conversations'
                                and status = 'derived' and source_refs->>'ref' like %s""", (f"conv:beeper:{chat}:%",)).fetchone()
    assert burst and int(burst["attributes"].get("owner_messages") or 0) == 0 and burst["attributes"]["chat_type"] == "single"
    asked = []

    def model(messages, **kw):
        asked.append(messages[0]["content"])
        return {"content": json.dumps({"plans": [{"what": "Café avec le contact", "start": "2026-12-12T15:00",
                                                  "agreed": "yes", "msgs": [1], "quote": "café le 12"}]}),
                "model": "scripted"}
    r = episodic.plan_burst(burst["item_id"], chat=model)
    assert r["outcome"] == "read" and r["plans"] == 1 and len(asked) == 1
    with connection() as conn:
        p = conn.execute("""select content, attributes, epistemic from core.derived_items where derived_by = 'episodic.plans'
                            and attributes->>'burst' = %s and status = 'derived'""", (burst["item_id"],)).fetchone()
        sent = conn.execute("select count(*) n from core.events where thread_id = %s and event_type = 'message.sent'",
                            (chat,)).fetchone()["n"]
        queued = conn.execute("select count(*) n from processing.queue where processor = 'runs.reminder'").fetchone()["n"]
    assert p["attributes"]["agreed"] == "unclear" and "accord non établi" in p["content"]
    assert p["epistemic"] == "stated_third_party" and sent == 0 and queued == 0
    # the same messages are never read twice
    assert episodic.plan_burst(burst["item_id"], chat=model)["reused"] and len(asked) == 1
    # a group where the owner said nothing is not his plan
    group = f"!pytest-pg-{uuid.uuid4().hex[:8]}:beeper.local"
    say(c, group, "contact", "Café le 12 décembre à 15h tout le monde ?", at=at, chat_type="group")
    flows.conversations(at - timedelta(minutes=5), thread=("beeper", group))
    with connection() as conn:
        g = conn.execute("""select item_id::text from core.derived_items where derived_by = 'flows.conversations'
                            and status = 'derived' and source_refs->>'ref' like %s""", (f"conv:beeper:{group}:%",)).fetchone()
    assert episodic.plan_burst(g["item_id"], chat=model)["outcome"] == "no_owner_message" and len(asked) == 1
