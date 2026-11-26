"""Nature × portée (owner 2026-11-25, M1–M5): one vocabulary for extraction, the write door, re-typing and
restitution (walter_memory.nature). A real consigne is not necessarily universal; only the consignes applicable to the
message are presented as instructions; preferences come apart, only when related; opinions and facts only through the
relevant memory; nothing is deleted, re-typing is reversible."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import extract2, nature, working

NOW = datetime.now(timezone.utc)


# ───────────────────────────── vocabulary and door (pure) ─────────────────────────────
def test_prompt_words_and_aliases_map_to_one_vocabulary():
    assert nature.norm_nature("consigne") == "instruction"
    assert nature.norm_nature("Préférence") == "preference"
    assert nature.norm_nature("fait") == "fact" and nature.norm_nature("objectif") == "goal"
    assert nature.norm_nature("avis") == "opinion"
    assert nature.norm_nature("n'importe quoi") is None
    assert nature.norm_reach("tâche") == "task" and nature.norm_reach("universelle") == "universal"
    assert nature.norm_reach("projet") == "project" and nature.norm_reach("personne") == "person"


def test_kind_and_domain_follow_nature_and_portee():
    assert nature.KIND_OF["instruction"] == "constraint" and nature.KIND_OF["opinion"] == "fact"
    assert nature.DOMAIN_OF["project"] == "project" and nature.DOMAIN_OF["person"] == "relation"
    assert nature.DOMAIN_OF["task"] == "task" and nature.DOMAIN_OF["universal"] == "personal"


def test_a_contact_conversation_never_yields_a_consigne():
    n, r, note = nature.door("instruction", "universal", channel="contact")
    assert n == "preference" and r == "universal" and note
    assert nature.door("instruction", "project", channel="agent")[:2] == ("instruction", "project")


def test_monsieur_himself_is_not_a_person_portee_but_universal():
    """What holds for Monsieur holds for every message (Walter always talks to him): a « personne : Monsieur »
    portée is universal, at the write door, for extraction and re-typing alike."""
    assert nature.door("instruction", "person", channel="agent", on="Monsieur")[1] == "universal"
    assert nature.door("instruction", "person", channel="agent", on="Monsieur lui-même")[1] == "universal"
    assert nature.door("instruction", "person", channel="agent", on="Paul")[1] == "person"
    assert nature.door("instruction", "person", channel="agent", on="la sœur de Monsieur")[1] == "person"
    new, ok = nature.typed_attributes(_row("constraint"), {"nature": "instruction", "reach": "person",
                                                           "reach_on": "Monsieur"}, "t")
    assert ok and new["reach"] == "universal" and "reach_on" not in new


def test_the_contact_guide_has_no_consigne():
    assert "consigne :" in nature.guide()
    assert "- consigne :" not in nature.guide(contact=True)


# ───────────────────────────── applicability (pure) ─────────────────────────────
def test_universal_consigne_always_applies_task_never():
    assert nature.applicable({"reach": "universal"}, "n'importe quoi", sim=None, threshold=0.35)
    assert not nature.applicable({"reach": "task", "reach_on": "x"}, "x", sim=0.99, threshold=0.35)


def test_project_consigne_applies_when_the_message_is_about_that_project():
    c = {"reach": "project", "reach_on": "walter-router"}
    assert nature.applicable(c, "on avance ?", sim=0.1, threshold=0.35, projects=["project:walterrouter"])
    assert nature.applicable(c, "et pour Walter Router ?", sim=0.1, threshold=0.35)        # named
    assert not nature.applicable(c, "fais un mail à mon comptable", sim=0.1, threshold=0.35, projects=["project:sagora"])
    assert nature.applicable(c, "fais un mail", sim=0.6, threshold=0.35)                  # close to the consigne


def test_domain_person_situation_apply_only_when_named_or_close():
    c = {"reach": "domain", "reach_on": "sous-titres vidéo"}
    assert not nature.applicable(c, "ajoute des sous-titres au podcast", sim=0.0, threshold=0.35)
    assert nature.applicable(c, "les sous-titres de la video", sim=0.0, threshold=0.35)       # accents folded
    assert not nature.applicable({"reach": "person", "reach_on": "Paul"}, "écris à Marie", sim=0.1, threshold=0.35)
    assert nature.applicable({"reach": "person", "reach_on": "Paul"}, "écris à Paul", sim=0.1, threshold=0.35)


def test_mentions_needs_every_significant_word():
    assert nature.mentions("Walter Browse", "un souci dans walter browse")
    assert not nature.mentions("Walter Browse", "un souci dans le navigateur")
    assert not nature.mentions(None, "x") and not nature.mentions("", "x")


def test_readers_file_by_nature_once_known():
    assert nature.reader_kind("constraint", {"act": "opinion"}) == "fact"
    assert nature.reader_kind("constraint", {"act": "instruction"}) == "constraint"
    assert nature.reader_kind("preference", {"act": "decision"}) == "decision"
    assert nature.reader_kind("constraint", {"act": "rule"}) == "constraint"          # not typed yet: as stored
    assert nature.reader_text("c'est nul", {"act": "opinion"}) == "(avis) c'est nul"
    assert nature.reader_text("x", {"act": "fact"}) == "x"


# ───────────────────────────── re-typing attributes (pure, one function for write and what-if) ─────────────────────────────
def _row(kind, act=None, channel=None):
    a = {"subject": "owner", "domain": "personal", "quote": "q"}
    if act is not None:
        a["act"] = act
    if channel:
        a["channel"] = channel
    return {"item_id": str(uuid.uuid4()), "kind": kind, "attributes": a}


def test_retype_keeps_everything_and_adds_nature_and_portee():
    r = _row("constraint", "rule")
    new, ok = nature.typed_attributes(r, {"nature": "instruction", "reach": "project", "reach_on": "sagora"}, "t")
    assert ok and new["act"] == "instruction" and new["reach"] == "project" and new["reach_on"] == "sagora"
    assert new["typing"]["from"] == {"act": "rule"} and new["typing"]["version"] == nature.VERSION
    assert {k: new[k] for k in ("subject", "domain", "quote")} == {"subject": "owner", "domain": "personal", "quote": "q"}


def test_retype_never_overrides_a_typed_act_but_refines_a_fact_into_an_opinion():
    new, _ = nature.typed_attributes(_row("decision", "proposal"), {"nature": "instruction", "reach": "universal",
                                                                    "reach_on": None}, "t")
    assert new["act"] == "proposal"
    new, _ = nature.typed_attributes(_row("fact", "fact"), {"nature": "opinion", "reach": "universal", "reach_on": None}, "t")
    assert new["act"] == "opinion"
    new, _ = nature.typed_attributes(_row("goal"), {"nature": "instruction", "reach": "task", "reach_on": None}, "t")
    assert new["act"] == "goal"                                   # untyped goal keeps the act its kind gave it


def test_retype_door_and_unclear_and_corrections():
    new, ok = nature.typed_attributes(_row("constraint", "", "contact"), {"nature": "instruction", "reach": "person",
                                                                           "reach_on": "Paul"}, "t")
    assert ok and new["act"] == "preference" and new["typing"]["note"]
    new, ok = nature.typed_attributes(_row("constraint"), {"nature": None, "reach": None, "reach_on": None}, "t")
    assert not ok and new["typing"]["status"] == "unclear" and "act" not in new
    new, ok = nature.typed_attributes(_row("correction", "correction"), {"nature": "fact", "reach": "universal",
                                                                         "reach_on": None}, "t")
    assert ok and new["act"] == "fact" and new["corrects"] is True


# ───────────────────────────── extraction v4 (pure validate) ─────────────────────────────
def _seg(text, chan_received=False):
    return [{"content": text, "event_type": "message.received" if chan_received else "message.sent",
             "speaker_id": "e1" if chan_received else None, "speaker": "Paul" if chan_received else None}]


def test_v4_consigne_with_portee_is_an_instruction_filed_by_its_portee():
    t = "Pour les sous-titres vidéo, jamais de ponctuation."
    it, why = extract2.validate({"type": "consigne", "text": t, "msgs": [1], "quote": t, "portee": "domaine",
                                 "sur": "sous-titres vidéo"}, _seg(t), {})
    assert why is None and it["kind"] == "constraint" and it["act"] == "instruction"
    assert it["reach"] == "domain" and it["reach_on"] == "sous-titres vidéo" and it["domain"] == "personal"


def test_v4_opinion_is_a_fact_kind_with_opinion_act_never_a_rule():
    t = "Franchement ce thème sombre est moche."
    it, why = extract2.validate({"type": "opinion", "text": t, "msgs": [1], "quote": t, "portee": "universelle"},
                                _seg(t), {})
    assert why is None and it["kind"] == "fact" and it["act"] == "opinion"


def test_v4_test_portee_never_becomes_knowledge():
    t = "Ceci est un message de test du pipeline."
    assert extract2.validate({"type": "fait", "text": t, "msgs": [1], "quote": t, "portee": "test"}, _seg(t), {}) \
        == (None, "test")


def test_v4_consigne_from_a_contact_is_kept_as_a_preference():
    t = "Envoie-moi toujours les photos en haute définition."
    it, why = extract2.validate({"type": "consigne", "text": t, "msgs": [1], "quote": t, "portee": "universelle",
                                 "author": "monsieur"}, _seg(t), {}, chan="contact")
    assert why is None and it["act"] == "preference" and it["kind"] == "preference" and it["nature_note"]


def test_v3_items_keep_their_former_reading():
    t = "Ne jamais redémarrer le moteur sans vérifier les tours actifs."
    it, why = extract2.validate({"type": "contrainte", "text": t, "msgs": [1], "quote": t, "domain": "personnel"},
                                _seg(t), {})
    assert why is None and it["kind"] == "constraint" and it["act"] == "rule"


def test_switches_default_to_the_behaviour_before():
    from walter_memory import organic
    assert organic.DEFAULTS["nature"] == {"extraction": "v3", "restitution": "rules"}
    assert "retype" in organic.STAGES


# ───────────────────────────── restitution (database) ─────────────────────────────
def _store(tag, items, chan_text):
    from walter_memory import events, generations
    extract2.set_v1_start(NOW - timedelta(days=10))
    generations.rollback(confirm=True)
    thread = f"nat-{uuid.uuid4().hex[:8]}"
    events.record_events([{"event_type": "message.sent", "source": "codex", "source_account": "pytest",
                           "source_id": uuid.uuid4().hex, "thread_id": thread, "content": chan_text,
                           "occurred_at": NOW - timedelta(hours=1), "privacy_class": "cloud_allowed"}])
    extract2.process_thread("codex", thread, force=True, chat=lambda messages, **kw: {
        "content": json.dumps({"summary": "", "items": items}), "cost_usd": 0, "model": "scripted",
        "usage": {"prompt_tokens": 10}})


@pytest.fixture
def stored():
    tag = uuid.uuid4().hex[:6]
    s = {"univ": f"Réponds à Monsieur en phrases courtes {tag}.",
         "proj": f"Dans le projet zorg{tag}, lance les tests avant chaque commit.",
         "opin": f"Le thème de l'outil {tag} est franchement moche.",
         "pref": f"Monsieur aime les tableaux compacts {tag}.",
         "upref": f"Monsieur préfère des réponses sans emoji {tag}."}
    items = [{"type": "consigne", "text": s["univ"], "msgs": [1], "quote": s["univ"], "portee": "universelle"},
             {"type": "consigne", "text": s["proj"], "msgs": [1], "quote": s["proj"], "portee": "projet",
              "sur": f"zorg{tag}"},
             {"type": "opinion", "text": s["opin"], "msgs": [1], "quote": s["opin"], "portee": "universelle"},
             {"type": "preference", "text": s["pref"], "msgs": [1], "quote": s["pref"], "portee": "domaine",
              "sur": f"tableaux {tag}"},
             {"type": "preference", "text": s["upref"], "msgs": [1], "quote": s["upref"], "portee": "universelle"}]
    _store(tag, items, " ".join(s.values()))
    return tag, s


def _mode(monkeypatch, restitution):
    monkeypatch.setattr(nature, "settings", lambda: {"extraction": "v3", "restitution": restitution})


def test_applicable_mode_presents_only_applicable_consignes(monkeypatch, stored):
    tag, s = stored
    _mode(monkeypatch, "applicable")
    r = working.owner_rules("quel temps fera-t-il demain ?", budget=5000)
    assert s["univ"] in r["text"]
    assert s["proj"] not in r["text"] and s["opin"] not in r["text"]
    assert s["pref"] not in r["preferences"]["text"]                    # not related to the message
    assert s["upref"] in r["preferences"]["text"] and s["upref"] not in r["text"]   # universal: always, apart
    r = working.owner_rules(f"on avance sur le projet zorg{tag}", budget=5000)
    assert s["proj"] in r["text"] and "[projet : " in r["text"]
    r = working.owner_rules(f"refais les tableaux {tag} du rapport", budget=5000)
    assert s["pref"] in r["preferences"]["text"] and s["pref"] not in r["text"]
    assert all(s["opin"] not in x for x in (r["text"], r["preferences"]["text"]))


def test_rules_mode_is_unchanged(monkeypatch, stored):
    tag, s = stored
    _mode(monkeypatch, "rules")
    r = working.owner_rules("quel temps fera-t-il demain ?", budget=5000)
    assert "preferences" not in r and "mode" not in r
    assert s["opin"] not in r["text"]                                    # an opinion is a fact kind either way


def test_context_titles_the_consignes_as_the_only_instructions(monkeypatch, stored):
    from walter_memory import context
    tag, s = stored
    _mode(monkeypatch, "applicable")
    out = context.get_context(f"refais les tableaux {tag} du rapport", include_profile=False)
    assert "## Consignes de Monsieur à Walter applicables à ce message" in out["text"]
    assert "sauf la section « Consignes »" in out["text"].split("\n", 1)[0]
    assert "## Préférences et énoncés durables de Monsieur liés à ce message" in out["text"]
    _mode(monkeypatch, "rules")
    out = context.get_context(f"refais les tableaux {tag} du rapport", include_profile=False)
    assert "Consignes de Monsieur" not in out["text"] and "sauf la section" not in out["text"]
