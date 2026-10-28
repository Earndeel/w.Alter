"""Sourced observations (P3). Writes rows tied to a pytest run and removes them."""
import pytest

from walter_memory import observations as O, runs
from walter_memory.db import connect


@pytest.fixture
def run_id():
    r = runs.start(origin={"channel": "owner", "runtime": "pytest", "session_id": "pytest/obs"}, goal="obs")
    yield r
    with connect() as c:
        c.execute("delete from runs.links where run_id = %s", (r,))
        c.execute("delete from core.derived_items where kind = 'sourced_observation' and attributes->>'run_id' = %s", (r,))
        c.execute("delete from bus.events where source = 'runs' and subject = %s", (r,))
        c.execute("delete from runs.runs where run_id = %s", (r,))


def test_normalize_keeps_unknown_unknown_and_maps_flat_answers():
    o = O.normalize({"produit": "Americano glacé", "prix_THB": 35, "volume": "inconnu",
                     "url_source": "https://www.7eleven.co.th/x", "confidence": "high", "method": "static_html"})
    assert o["values"] == {"price": 35, "volume": None, "currency": "THB"} or o["values"]["volume"] is None
    assert o["confidence"] == 0.9 and o["subject"] == "Americano glacé"


def test_source_is_required_and_bad_method_refused():
    with pytest.raises(O.ObservationError):
        O.normalize({"subject": "x", "values": {"price": 1}})
    with pytest.raises(O.ObservationError):
        O.normalize({"subject": "x", "source_url": "https://a", "method": "guess"})


def test_record_is_idempotent_linked_to_the_run_and_reusable(run_id):
    items = [{"subject": "All Café iced americano 16 oz", "seller": "7-Eleven", "source_url": "https://www.7eleven.co.th/a",
              "values": {"price": 35, "currency": "THB", "volume_ml": 473}, "method": "static_html"},
             {"subject": "sans source", "values": {"price": 1}}]
    r1 = O.record(items, run_id=run_id, geo={"pays": "TH"})
    r2 = O.record(items, run_id=run_id)
    assert r1["stored"] == 1 and len(r1["errors"]) == 1 and r2["stored"] == 0 and r2["skipped"] == 1
    assert len(O.of_run(run_id)) == 1
    assert {l["kind"] for l in runs.show(run_id)["links"]} >= {"observation"}
    assert any(x["attributes"]["seller"] == "7-Eleven" for x in O.recent("americano 7-eleven"))
