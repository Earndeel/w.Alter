"""The owner's privacy choice of 2026-11-03 ([privacy] cloud_context = redacted_cloud, pseudonymise = false): messaging
content enters cloud contexts as is; local_only still never does, whatever the setting says."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, llm, privacy
from walter_memory.db import connection

pytestmark = pytest.mark.owner_privacy


def test_cloud_readers_see_redacted_but_never_local_only():
    assert privacy.allowed_classes("cloud_allowed") == ["cloud_allowed", "redacted_cloud"]
    assert privacy.cloud_readable("redacted_cloud") and not privacy.cloud_readable("local_only")


def test_local_only_cannot_be_opened_by_the_setting(monkeypatch):
    from walter_memory import organic
    cur = organic.settings()
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "privacy": {"cloud_context": "local_only"}})
    assert privacy.cloud_ceiling() == "cloud_allowed" and "local_only" not in privacy.allowed_classes("cloud_allowed")


def test_working_state_carries_messaging_content_for_a_cloud_model():
    from walter_memory import working, extract2
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=1))
    t = f"op-{uuid.uuid4().hex[:6]}"
    for cls, text in (("redacted_cloud", "Rappelle-moi d'appeler Somchai pour le contrat"),
                      ("local_only", "Mon code de porte est le 4471")):
        events.record_events([{"event_type": "message.sent", "source": "hermes", "source_account": "pytest",
                               "source_id": uuid.uuid4().hex, "thread_id": t, "content": text, "privacy_class": cls,
                               "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=5)}])
    st = working.state("hermes", t, audience="cloud_model")
    assert "Somchai" in st["text"] and "4471" not in st["text"]


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
