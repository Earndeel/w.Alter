"""Restricted Overland ingress. Run separately from the general memory gateway."""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import time
from collections import deque
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from . import events, ingestion
from .db import connection

app = FastAPI(title="Walter Overland", docs_url=None, redoc_url=None, openapi_url=None)
TOKEN = os.environ.get("WALTER_OVERLAND_TOKEN", "")
DEVICE = os.environ.get("WALTER_OVERLAND_DEVICE", "iphone")
MAX_BYTES = 2 * 1024 * 1024
_requests = deque()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp required")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt < datetime(2000, 1, 1, tzinfo=timezone.utc):
        raise ValueError("invalid timestamp")
    if dt > datetime.now(timezone.utc) + timedelta(days=1):
        raise ValueError("future timestamp")
    return dt.astimezone(timezone.utc)


def normalize(body):
    if not isinstance(body, dict) or not isinstance(body.get("locations"), list):
        raise ValueError("locations array required")
    if len(body["locations"]) > 1000:
        raise ValueError("too many locations")
    features = list(body["locations"])
    if body.get("current") is not None:
        features.append(body["current"])
    trip = body.get("trip")
    if trip is not None:
        if not isinstance(trip, dict):
            raise ValueError("invalid trip")
        if trip.get("current_location") is not None:
            features.append(trip["current_location"])
    result = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("GeoJSON Feature required")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise ValueError("properties required")
        dt = timestamp(props.get("timestamp"))
        # The dedicated credential identifies the device; its editable display label
        # is preserved in raw properties and must not reject otherwise valid samples.
        geo = feature.get("geometry")
        payload = {"device_id": DEVICE, "raw": feature}
        kind = "location.telemetry"
        if isinstance(geo, dict) and geo.get("type") == "Point":
            coords = geo.get("coordinates")
            if (not isinstance(coords, list) or len(coords) < 2 or
                    not all(number(v) for v in coords[:2]) or
                    not -180 <= coords[0] <= 180 or not -90 <= coords[1] <= 90):
                raise ValueError("invalid coordinates")
            accuracy = props.get("horizontal_accuracy")
            payload.update(lat=coords[1], lng=coords[0],
                           accuracy_m=accuracy if number(accuracy) else None)
            kind = "location.sample"
        # Transport metadata may change when the same point is resent in another batch.
        identity = [DEVICE, dt.isoformat(), geo, props.get("type"), props.get("action")]
        if kind == "location.telemetry":
            identity.append(props)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
        result.append(dict(event_type=kind, source="overland", source_id=key,
                           source_account=DEVICE, occurred_at=dt, payload=payload,
                           privacy_class="local_only",
                           actor={"external_id": DEVICE, "is_self": True}))
    return result


def settings_for(batch, now=None):
    """Never choose a profile from an old backlog, or infer movement from packet order."""
    now = now or datetime.now(timezone.utc)
    points = [e for e in batch if e["event_type"] == "location.sample"
              and e["payload"]["accuracy_m"] is not None
              and 0 <= e["payload"]["accuracy_m"] <= 200
              and timedelta(minutes=-1) <= now - e["occurred_at"] <= timedelta(minutes=10)]
    if not points:
        return {}
    latest = max(points, key=lambda e: e["occurred_at"])
    props = latest["payload"]["raw"]["properties"]
    speed = props.get("speed")
    motion = props.get("motion") or []
    moving = (number(speed) and speed > 0.8) or any(m in motion for m in ("walking", "running", "cycling", "driving"))
    battery = props.get("battery_level")
    low = number(battery) and 0 <= battery < 0.2 and props.get("battery_state") not in ("charging", "full")
    return {"send_interval": "5m" if low else "30s" if moving else "2m",
            "main": {"tracking_mode": "both", "desired_accuracy": "100m" if low else "10m",
                     "activity_type": "other", "pause_automatically": True,
                     "resume_with_geofence": "100m", "background_indicator": True,
                     "logging_mode": "all", "batch_size": 200,
                     "min_distance": "100m" if low else "50m", "min_time": "30s",
                     "discard_stationary": False, "discard_without_gps": False}}


def store(batch):
    with connection() as conn:
        result = events.record_events(batch, conn=conn)
        conn.execute("update ingestion.connectors set last_success_at=now() where connector='overland'")
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/overland")
async def ingest(request: Request):
    authorization = request.headers.get("authorization", "")
    if not TOKEN or not secrets.compare_digest(authorization.encode(), ("Bearer " + TOKEN).encode()):
        raise HTTPException(401, "unauthorized")
    now = time.monotonic()
    while _requests and _requests[0] < now - 60:
        _requests.popleft()
    if len(_requests) >= 120:
        raise HTTPException(429, "retry later")
    _requests.append(now)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "batch too large")
    try:
        body = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        batch = normalize(body)
        # Reject unhandled top-level extensions rather than silently acknowledge/discard them.
        if set(body) - {"locations", "current", "trip"}:
            raise ValueError("unsupported fields")
        if body.get("trip"):
            trip = body["trip"]
            dt = timestamp(trip.get("start"))
            key = hashlib.sha256(json.dumps(trip, sort_keys=True).encode()).hexdigest()
            batch.append(dict(event_type="location.telemetry", source="overland", source_account=DEVICE,
                              source_id="trip:" + key, occurred_at=dt, privacy_class="local_only",
                              payload={"device_id": DEVICE, "trip": trip}))
        settings = settings_for(batch)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(422, "invalid Overland batch") from None
    try:
        result = await run_in_threadpool(store, batch)
    except Exception:
        # No payload/coordinates/token in errors; the phone retains the batch on every failure.
        raise HTTPException(503, "storage unavailable; retry later") from None
    return {"result": "ok", "inserted": result["inserted"], "duplicates": result["duplicates"], "set": settings}


def register():
    from . import types
    types.register("location.telemetry", "Original Overland device/trip telemetry (local_only).",
                   {"type": "object", "required": ["device_id"]}, version=1)
    with connection() as conn:
        conn.execute("""insert into core.sources(source,kind,description,privacy_default)
                        values ('overland','location','Overland iPhone GPS','local_only')
                        on conflict(source) do nothing""")
    ingestion.register_connector("overland", "overland", "push", "iPhone GPS; private authenticated ingress")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["register"]:
        register()
    else:
        raise SystemExit("Usage: walter-python -m walter_memory.overland register")
