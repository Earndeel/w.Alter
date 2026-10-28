# Overland iPhone → Walter Memory

Private GPS ingress owned by Memory, run as `walter-memory-overland.service`. This is a separate HTTP app: the public reverse proxy cannot reach the general memory gateway, read events, or upload files. It accepts only `POST /overland` with the dedicated Bearer token. `GET /health` contains no personal information. TLS terminates at the existing Cloudflare tunnel; the app binds loopback :3010. It does not log requests, coordinates, tokens, or request bodies.

The phone's endpoint is `https://loc.walter-ai.cloud/overland`. The canonical device ID is `iphone`; the editable iPhone label (for example `iPhone 13 Pro`) is accepted and preserved in the original feature. The dedicated credential establishes identity. Credentials live in `@instance/bootstrap/overland.env` (0600), separate from the general ingestion key. Never include the token in a setup link, command argument, model prompt, screenshot or log. For setup, transfer the value directly from the private file to the Mac clipboard over SSH stdin; paste into Overland's Access Token field using Universal Clipboard, or let Monsieur handle the local value directly. Apple installation and Location Always/Precise and Motion permissions require interaction on the phone with the currently available tools. A connected USB device alone does not establish that the app is installed/configured.

## Data and acknowledgement

Raw GeoJSON Points become `location.sample`, preserving the original feature under `payload.raw`; nonpoint device records and active trip telemetry become `location.telemetry`. Source `overland`, account `iphone`, confidentiality `local_only`. A whole batch is validated before a single transaction writes it through `walter_memory.events`. Retries dedupe by device/time/geometry/type/action, independently of `locations_in_payload`. Changed telemetry remains a separate observation. `current` and `trip.current_location` are also ingested so a backlog does not hide a recent position.

Only after the transaction commits does the phone receive `{"result":"ok"}`. Authentication failure, malformed/oversized input, rate limits and storage failures never acknowledge data. Limits: 2 MiB body, 1,000 batch records, 120 authenticated requests/minute, 8 concurrent requests. Storage errors are generic; the phone retains its queue. Synthetic integration probes must be rolled back, never saved as observed location.

## Managed battery/movement profile

The response centrally applies a managed profile, including on retries, so a lost HTTP response cannot permanently lose configuration. It uses the newest valid point within 10 minutes, accuracy 0–200 m; older backlog does not change settings.

- Walking, cycling, running or driving (or speed >0.8 m/s): send about every 30 seconds.
- Otherwise: send about every 2 minutes.
- Battery <20%, unplugged: send about every 5 minutes, desired accuracy 100 m and distance filter 100 m.
- Normal: desired accuracy 10 m, distance filter 50 m; minimum logging time 30 s.
- Standard + significant change tracking, automatic pause, resume geofence 100 m, background indicator, all data queued (batch 200).

The interval is a request to iOS, never a guarantee; automatic pause/geofence can delay resumption. These thresholds need field validation during a real walk before claiming production tracking quality. This connector does not yet cluster stays, reverse-geocode, notify on movement or send coordinates to an external model. Raw GPS remains excluded from cloud-safe recall under the existing privacy policy. Explicit local-only reads must stay inside a local processing context.

## Operations and verification

- Resolve source root with `walter path memory`; Python via `walter-python`.
- `systemctl status walter-memory-overland` and HTTPS `/health` show service health only.
- Connector `overland` has `last_success_at`; canonical `location.sample` events show actual receipt. Check `occurred_at` and accuracy, not only ingest time, before asserting current position.
- Re-register source/type/connector (idempotent): `walter-python -m walter_memory.overland register`.
- Tests: `walter-python -m pytest -q tests/test_overland.py`.
- After phone setup: grant Location Always + Precise, Motion, enable tracking; set initial Send Interval to 1 minute; tap Send Now. Verify a real recent canonical sample exists and the phone's queue clears. Test again after locking the screen and moving.
- After memory changes: run memory-autopilot; an unrelated pre-existing `beeper_media` dead-job warning may remain.

Rollback: stop/disable this one systemd unit, quarantine its installed source/unit and credential file. Leave canonical observations intact. This does not restart or alter the general memory gateway, Hermes, or the Cloudflare configuration. The route `loc.walter-ai.cloud → localhost:3010` already existed before this work.
