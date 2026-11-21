"""Where the owner is — the last position sample and the places Memory knows (Memory V1 flows). Read-only, no model.

    current(max_privacy="cloud_allowed") → {
        "status": "recent" | "old" | "absent",   # recent = the last sample is under `recent_s` old
        "at": ISO time of the last sample, "age_s": seconds, "accuracy_m",
        "lat", "lng",                            # rounded to 3 decimals (~110 m): enough to search around, no more
        "place": {"name", "home", "distance_m"} | None,   # the known place the sample falls in (flows.PLACE_RADIUS_M)
        "home":  {"name", "lat", "lng", "distance_m"} | None}   # the probable home (flows.mark_home), if known

Position samples (`location.sample`, source overland) and places are `local_only`: they are read only when the
reader may read that class — a cloud reader up to privacy.cloud_ceiling() (organic.toml [privacy] cloud_context;
« oui tout », 2026-11-03). Otherwise → {"status": "withheld"}. Consumer: walter-context's position block (a turn
whose plan says the answer depends on where the owner is: « une pizza autour de moi »), 2026-11-18.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import privacy
from .db import connection
from .flows import PLACE_RADIUS_M, _m

RECENT_S = 7200           # a position older than this is said as old (the owner may have moved)
CLASS = "local_only"      # position samples and places


def _place_view(row, here) -> dict:
    a = row["attributes"] or {}
    d = round(_m((a["lat"], a["lng"]), here)) if here else None
    return {"name": row["canonical_name"], "home": bool(a.get("home")), "lat": round(a["lat"], 3),
            "lng": round(a["lng"], 3), "distance_m": d}


def current(max_privacy: str = "cloud_allowed", recent_s: float = RECENT_S, conn=None) -> dict:
    if CLASS not in privacy.allowed_classes(max_privacy):
        return {"status": "withheld"}

    def read(c) -> dict:
        last = c.execute("""select occurred_at, (payload->>'lat')::float lat, (payload->>'lng')::float lng,
                                   (payload->>'accuracy_m')::float accuracy
                            from core.events where event_type = 'location.sample'
                              and payload ? 'lat' and payload ? 'lng'
                            order by occurred_at desc limit 1""").fetchone()
        places = c.execute("""select canonical_name, attributes from core.entities where entity_type = 'place'
                              and status = 'active' and attributes ? 'lat' and attributes ? 'lng'""").fetchall()
        home = next((p for p in places if (p["attributes"] or {}).get("home")), None)
        if not last or last["lat"] is None or last["lng"] is None:
            return {"status": "absent", "home": ({k: v for k, v in _place_view(home, None).items() if k != "home"}
                                                 if home else None)}
        here = (last["lat"], last["lng"])
        age = (datetime.now(timezone.utc) - last["occurred_at"]).total_seconds()
        near = min(((_m((p["attributes"]["lat"], p["attributes"]["lng"]), here), p) for p in places),
                   key=lambda x: x[0], default=(None, None))
        place = _place_view(near[1], here) if near[1] is not None and near[0] <= PLACE_RADIUS_M else None
        return {"status": "recent" if age <= recent_s else "old",
                "at": last["occurred_at"].isoformat(timespec="minutes"), "age_s": round(age),
                "accuracy_m": round(last["accuracy"]) if last["accuracy"] is not None else None,
                "lat": round(here[0], 3), "lng": round(here[1], 3),
                "place": {k: place[k] for k in ("name", "home", "distance_m")} if place else None,
                "home": ({k: v for k, v in _place_view(home, here).items() if k != "home"} if home else None)}
    if conn is not None:
        return read(conn)
    with connection() as c:
        return read(c)
