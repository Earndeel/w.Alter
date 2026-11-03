"""P1.3-P1.6 on the test database: entities and relations, deterministic flows (GPS stays, bursts, appointments),
multi-source episodes (hypotheses never become certainties without the owner; the cloud projection holds no local
evidence), period syntheses and the targeted rebuild after a correction."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from walter_memory import consolidate, entities, episodic, events, extract2, flows, generations, periods
from walter_memory.db import connection

Z = flows.tz()
DAY = (datetime.now(timezone.utc) - timedelta(days=3)).astimezone(Z).date()


def at(h, m=0, day=None):
    return datetime.combine(day or DAY, datetime.min.time(), Z).replace(hour=h, minute=m).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def setup():
    extract2.set_v1_start(datetime.now(timezone.utc) - timedelta(days=30))
    generations.rollback(confirm=True)


def ev(**kw):
    base = {"source_account": "pytest", "source_id": uuid.uuid4().hex, "privacy_class": "cloud_allowed"}
    return events.record_events([{**base, **kw}])["event_ids"][0]


def gps(lat, lng, t, wifi=None):
    return ev(event_type="location.sample", source="overland", occurred_at=t, privacy_class="local_only",
              payload={"lat": lat, "lng": lng, "accuracy_m": 10, "raw": {"properties": {"wifi": wifi, "motion": ["stationary"]}}})


def test_stays_need_ten_minutes_within_the_radius_or_one_wifi():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pts = [{"id": str(k), "at": t0 + timedelta(minutes=2 * k), "lat": 13.7 + (0.0001 if k % 2 else 0), "lng": 100.5,
            "accuracy": 10, "wifi": None} for k in range(8)]                       # 14 min, a few metres apart
    pts += [{"id": "far", "at": t0 + timedelta(minutes=20), "lat": 13.8, "lng": 100.6, "accuracy": 10, "wifi": None}]
    pts += [{"id": f"w{k}", "at": t0 + timedelta(minutes=30 + 3 * k), "lat": 13.9 + 0.002 * k, "lng": 100.7,
             "accuracy": 10, "wifi": "Cafe"} for k in range(5)]                     # moves 800 m but one Wi-Fi
    s = flows.stays(pts)
    assert len(s) == 2 and s[0]["end"] - s[0]["start"] >= timedelta(minutes=10) and s[1]["wifi"] == "Cafe"


def test_project_mentions_resolve_by_alias_and_phases_are_not_projects():
    with connection() as conn:
        eid = entities.ensure(conn, "project", "Walter Memory", aliases=["organic memory", "memory v1"])
    entities._aliases.cache_clear()
    assert entities.resolve_project("Walter Memory V1") == eid
    assert entities.resolve_project("Organic Memory") == eid
    assert entities.resolve_project("P1.2") is None


def _episode_world(tag):
    """A cinema evening: a calendar appointment (cloud), a GPS stay that overlaps it (local), home stays at night."""
    home = (13.7300 + hash(tag) % 100 * 1e-6, 100.5800)
    for k in range(10):                                        # home, 01:00-03:00 → probable home
        gps(*home, at(1, 0) + timedelta(minutes=12 * k), wifi=f"Home-{tag}")
    for k in range(12):                                        # the cinema area 21:50-00:00
        gps(13.7460, 100.5340, at(21, 50) + timedelta(minutes=10 * k), wifi=f"Mall-{tag}")
    cal = ev(event_type="calendar.event", source="calendar", occurred_at=at(22, 0),
             content=f"Cinéma Dune {tag}", payload={"event_id": f"ev-{tag}", "calendar_id": "owner@example.invalid",
                                                    "start": {"dateTime": at(22, 0).astimezone(Z).isoformat()},
                                                    "end": {"dateTime": at(23, 59).astimezone(Z).isoformat()},
                                                    "location": "Major Cineplex", "attendees": []})
    since = at(0, 0)
    flows.visits(since, since + timedelta(days=1, hours=2))
    flows.appointments(since - timedelta(days=1), since + timedelta(days=2))
    return cal


def test_episode_from_calendar_and_gps_is_probable_never_confirmed_and_the_cloud_view_has_no_local_evidence(monkeypatch):
    monkeypatch.setattr(episodic, "settings", lambda: {"plans_per_run": 0, "attest": False})
    tag = uuid.uuid4().hex[:6]
    _episode_world(tag)
    episodic.build(at(0, 0) - timedelta(days=1), at(0, 0) + timedelta(days=2))
    with connection() as conn:
        rows = {r["view_key"]: r for r in conn.execute(
            "select view_key, epistemic, privacy_class, title, attributes from views.view where kind = 'episode' and title like %s",
            (f"%Dune {tag}%",))}
        local = next(v for k, v in rows.items() if k.endswith(":local"))
        cloud = next(v for k, v in rows.items() if not k.endswith(":local"))
        ev_cloud = conn.execute("select distinct privacy_class from views.evidence where view_key = %s",
                                (next(k for k in rows if not k.endswith(":local")),)).fetchall()
    assert local["epistemic"] == "probable" and local["privacy_class"] == "local_only"        # planned + measured
    assert cloud["epistemic"] == "candidate" and cloud["privacy_class"] == "cloud_allowed"    # planned only
    assert {r["privacy_class"] for r in ev_cloud} == {"cloud_allowed"}
    assert "probablement" in local["title"] and "confirm" not in local["title"].replace("non confirm", "")
    assert all(v != "confirmed" for v in local["attributes"]["facets"].values())


def test_owner_attestation_confirms_and_a_correction_rejects(monkeypatch):
    monkeypatch.setattr(episodic, "settings", lambda: {"plans_per_run": 0, "attest": True})
    g = [{"kind": "appointment", "start": at(22), "end": at(23), "attributes": {"title": "Cinéma"}, "entities": [],
          "content": "Rendez-vous prévu « Cinéma »", "id": "a", "privacy_class": "cloud_allowed"},
         {"kind": "visit", "start": at(21, 50), "end": at(23, 50), "attributes": {}, "entities": [],
          "content": "Présence", "id": "v", "privacy_class": "local_only"}]
    assert episodic.status_of(episodic.facets(g)) == "probable"
    assert episodic.status_of(episodic.facets(g, {"verdict": "confirms"})) == "confirmed"
    assert episodic.status_of(episodic.facets(g, {"verdict": "contradicts"})) == "rejected"
    assert episodic.status_of(episodic.facets(g[:1])) == "candidate"


def test_day_and_week_rebuild_after_a_correction_and_only_their_path(monkeypatch):
    t = f"p-{uuid.uuid4().hex[:8]}"
    e1 = ev(event_type="message.sent", source="codex", thread_id=t, occurred_at=at(10), content="on garde Redis pour le cache")
    with connection() as conn:
        old = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids, source_refs,
                                  valid_from, privacy_class, generation, epistemic, stage, scope)
                              values ('decision', 'Le cache utilise Redis', 'derived', 'l3.extract', %s::uuid[], %s, %s,
                                      'cloud_allowed', 'g1', 'stated_owner', 'decided', 'durable') returning item_id::text""",
                           ([e1], json.dumps({"source": "codex", "thread": t, "ref": f"{t}:1"}), at(10))).fetchone()["item_id"]
        conn.execute("update core.derived_items set content = content || ' ' || %s where item_id = %s", (t, old))
    line = f"Le cache utilise Redis {t}"
    d = periods.build("day", DAY)
    w = periods.build("week", DAY)
    other = periods.build("day", DAY - timedelta(days=9))
    day_key, week_key = d["cloud"]["key"], w["cloud"]["key"]
    read = lambda k: consolidate_read(k)                        # noqa: E731
    mine = lambda k: next(l for l in read(k).splitlines() if line in l)      # noqa: E731
    assert "remplacé" not in mine(day_key)
    with connection() as conn:   # the owner corrects it the next day (as extract2 records a supersession)
        conn.execute("update core.derived_items set status = 'superseded', attributes = attributes || %s where item_id = %s",
                     (json.dumps({"superseded_by": "0" * 8}), old))
    n = consolidate.invalidate(item_ids=[old])
    assert n >= 2                                                # the day and, through it, the week (and month)
    with connection() as conn:
        stale = set(periods.stale_keys(conn))
    assert day_key in stale and week_key in stale and other["cloud"]["key"] not in stale
    periods.tick(days=0)
    assert "remplacé" in mine(day_key)
    with connection() as conn:
        assert not set(periods.stale_keys(conn)) & {day_key, week_key}


def consolidate_read(key):
    from walter_memory import views
    return views.read({"depth": "details", "key": key, "max_tokens": 6000})["content"]
