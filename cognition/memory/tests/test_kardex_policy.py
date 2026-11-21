"""Kardex disclosure policy (read_policy, 2026-11-02): one decision point; person cards for a cloud model never carry
superseded, expired, sensitive, restricted or never_reference knowledge, masked phones, no current location."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from walter_memory import read_policy, social
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)
BASE = {"status": "active", "valid_to": None, "sensitivity": "normal", "mention_policy": "free",
        "disclosure_state": "explicitly_told_me", "knowledge_origin": "direct_statement", "evidence_sensitivity": None}


def vis(audience, **kw):
    return read_policy.kardex_claim_visible({**BASE, **kw}, audience)


def test_policy_matrix():
    assert vis("cloud_model") == (True, None)
    assert vis("cloud_model", status="superseded") == (False, "not_current")
    assert vis("owner_local", status="retracted") == (False, "not_current")
    assert vis("cloud_model", valid_to=NOW - timedelta(days=1)) == (False, "expired")
    assert vis("cloud_model", valid_to=NOW + timedelta(days=1))[0]
    assert vis("owner_local", mention_policy="never_reference") == (False, "never_reference")
    assert vis("cloud_model", sensitivity="sensitive") == (False, "sensitivity")
    assert vis("owner_local", sensitivity="highly_sensitive")[0]
    assert vis("cloud_model", evidence_sensitivity="highly_sensitive") == (False, "sensitivity")
    assert vis("cloud_model", mention_policy="indirect_only") == (False, "mention_policy")
    assert vis("owner_local", mention_policy="indirect_only")[0]
    assert vis("cloud_model", disclosure_state="restricted") == (False, "disclosure_state")
    assert vis("cloud_model", knowledge_origin="private_osint") == (False, "knowledge_origin")
    assert vis("third_party") == (False, "disclosure_state")           # told in confidence: not for others
    assert vis("third_party", disclosure_state="mutually_known")[0]
    assert vis("third_party", disclosure_state="mutually_known", sensitivity="personal") == (False, "sensitivity")
    assert read_policy.mask_phone("+33 6 12 34 56 78") == "•" * 9 + "78"


def _person():
    tag = uuid.uuid4().hex[:8]
    with connection() as conn:
        cid = conn.execute("""insert into kardex.contacts (canonical_name, relationship_type, occupation, location_current)
                              values (%s, 'friend', 'architecte', 'Lyon, rue X') returning id""", (f"Alix {tag}",)).fetchone()["id"]
        claims = {
            "ok": ("Aime l'escalade", {}),
            "unconfirmed": ("Prépare un marathon", {"status": "proposed"}),
            "old": ("Habite à Paris", {"status": "superseded"}),
            "expired": ("En congé jusqu'en mai", {"valid_to": NOW - timedelta(days=3)}),
            "never": ("Diagnostic médical X", {"mention_policy": "never_reference", "sensitivity": "highly_sensitive"}),
            "sensitive": ("Difficultés financières", {"sensitivity": "sensitive"}),
            "indirect": ("Semble fatigué", {"mention_policy": "indirect_only", "disclosure_state": "inferred_only"}),
            "osint": ("Profil trouvé en ligne", {"knowledge_origin": "private_osint"}),
            "evidence": ("Détail anodin d'une source sensible", {}),
        }
        ids = {}
        for k, (text, kw) in claims.items():
            row = {**BASE, **kw}
            ids[k] = conn.execute("""insert into kardex.claims (contact_id, claim_type, claim, status, valid_to, sensitivity,
                                         mention_policy, disclosure_state, knowledge_origin, confidence)
                                     values (%s, 'fact', %s, %s, %s, %s, %s, %s, %s, 0.8) returning id""",
                                  (cid, text, row["status"], row["valid_to"], row["sensitivity"], row["mention_policy"],
                                   row["disclosure_state"], row["knowledge_origin"])).fetchone()["id"]
        ev = conn.execute("""insert into kardex.evidence (contact_id, source, quote, sensitivity) values (%s, 'pytest', 'q',
                             'highly_sensitive') returning id""", (cid,)).fetchone()["id"]
        conn.execute("insert into kardex.claim_evidence (claim_id, evidence_id) values (%s, %s)", (ids["evidence"], ev))
        eid = conn.execute("""insert into core.entities (entity_type, canonical_name, kardex_contact_id)
                              values ('person', %s, %s) returning entity_id""", (f"Alix {tag}", cid)).fetchone()["entity_id"]
        iid = conn.execute("""insert into core.source_identities (source, external_id, account, phones)
                              values ('beeper', %s, 'whatsapp', %s) returning identity_id""",
                           (f"ext-{tag}", ["+33612345678"])).fetchone()["identity_id"]
        conn.execute("insert into core.identity_links (identity_id, entity_id, method, status) values (%s, %s, 'pytest', 'confirmed')",
                     (iid, eid))
    return str(eid)


def test_cloud_card_carries_only_current_disclosable_knowledge():
    eid = _person()
    cloud = social.person_card(eid, "cloud_allowed")
    texts = {c["claim"]: c["confirmed"] for c in cloud["kardex"]["claims"]}
    assert texts == {"Aime l'escalade": True, "Prépare un marathon": False}
    assert "location_current" not in cloud["kardex"]["contact"]
    assert all(p.endswith("78") and "612345" not in p for a in cloud["accounts"] for p in a["phones"])
    assert cloud["audience"] == "cloud_model"
    local = social.person_card(eid, "local_only")
    ltexts = {c["claim"] for c in local["kardex"]["claims"]}
    assert {"Difficultés financières", "Semble fatigué", "Profil trouvé en ligne",
            "Détail anodin d'une source sensible"} <= ltexts
    assert not ltexts & {"Habite à Paris", "En congé jusqu'en mai", "Diagnostic médical X"}
    assert local["kardex"]["contact"]["location_current"] == "Lyon, rue X"
    assert local["accounts"][0]["phones"] == ["+33612345678"]
