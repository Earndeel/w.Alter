"""The owner's privacy choice of 2026-11-03 (« oui tout »: [privacy] cloud_context = local_only, pseudonymise = false,
kardex_cloud = full): Walter has no local model, so everything may be read by the cloud models it reasons with;
credentials are masked in place (never dropped messages); what goes to a PERSON stays checked (disclosure)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, llm, privacy
from walter_memory.db import connection

pytestmark = pytest.mark.owner_privacy


def test_cloud_readers_and_model_calls_may_read_everything():
    assert privacy.allowed_classes("cloud_allowed") == ["cloud_allowed", "redacted_cloud", "local_only"]
    assert privacy.model_may_receive("local_only") and privacy.cloud_readable("local_only")


def test_working_state_carries_everything_with_credentials_masked():
    from walter_memory import working, extract2
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=1))
    t = f"op-{uuid.uuid4().hex[:6]}"
    for cls, text in (("redacted_cloud", "Rappelle-moi d'appeler Somchai pour le contrat"),
                      ("local_only", "Le rendez-vous chez le dermatologue est jeudi"),
                      ("local_only", "Pour le wifi de la villa, le mot de passe : Tamarin2026!")):
        events.record_events([{"event_type": "message.sent", "source": "hermes", "source_account": "pytest",
                               "source_id": uuid.uuid4().hex, "thread_id": t, "content": text, "privacy_class": cls,
                               "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=5)}])
    from walter_memory import context
    r = context.get_context("on appelle Somchai ?", session=("hermes", t), include_profile=False,
                            budget={"records": 0, "knowledge": 0, "evidence": 0, "views": 0, "people": 0})
    text = r["sections"]["working"]
    assert "Somchai" in text and "dermatologue" in text           # nothing dropped
    assert "villa" in text and "Tamarin2026" not in text         # the message stays, the credential is masked


def test_kardex_full_for_reasoning_with_mention_tags():
    from walter_memory import read_policy
    claim = {"status": "proposed", "sensitivity": "highly_sensitive", "mention_policy": "never_reference",
             "disclosure_state": "restricted", "knowledge_origin": "direct_statement"}
    assert read_policy.kardex_claim_visible(claim, "cloud_model")[0]          # the model may know it
    assert not read_policy.kardex_claim_visible(claim, "third_party")[0]      # a third party never


def test_no_pseudonymisation_before_a_cloud_call(monkeypatch):
    seen = {}

    class R:
        status_code, headers = 200, {}
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: seen.setdefault("body", kw["json"]) and R())
    monkeypatch.setattr(llm, "_gateway_token", lambda: "x")
    llm.chat([{"role": "user", "content": "Somchai arrive à 20h"}], poste="memory_extraction", processor="pytest",
             privacy_class="redacted_cloud", names=["Somchai"])
    assert "Somchai" in seen["body"]["messages"][0]["content"]
