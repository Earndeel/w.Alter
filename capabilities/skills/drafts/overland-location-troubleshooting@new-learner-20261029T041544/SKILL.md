---
name: overland-location-troubleshooting
description: Use when verifying Overland iPhone position updates in Walter Memory, diagnosing missing transmissions, or tuning stationary tracking without losing small movements.
---

## Inspect the installed integration

Load memory context and the applicable memory operations procedure. Resolve the module with `walter path memory`; inspect `docs/OVERLAND.md`, `walter_memory/overland.py`, and `tests/test_overland.py` there before changing behavior. The receiver unit is `walter-memory-overland.service`.

Check receiver state:

```bash
systemctl is-active walter-memory-overland.service
systemctl status walter-memory-overland.service --no-pager
```

An active receiver proves service availability, not automatic delivery from the iPhone.

## Verify actual position freshness

Read canonical samples through the public memory library. Avoid printing coordinates or raw payloads when timestamps suffice:

```bash
walter-python - <<'PY'
from walter_memory import events
from datetime import datetime, timezone
import json
rows = events.get_events(source='overland', event_types=['location.sample'], limit=10)
print(json.dumps({
    'checked_at_utc': datetime.now(timezone.utc).isoformat(),
    'samples': [{
        'occurred_at': str(row.get('occurred_at')),
        'ingested_at': str(row.get('ingested_at')),
        'accuracy_m': row.get('payload', {}).get('accuracy_m'),
    } for row in rows],
}, ensure_ascii=False, indent=2))
PY
```

Report the observation time, reception time when available, age, and timezone. Describe an old sample as the last received position. A stored Wi-Fi-to-home association does not independently establish current presence.

## Separate collection pauses from upload failures

Before asking Monsieur to press Send Now, ask whether he moved and obtain Tracker's Age, Queued, and Send Interval values. Preserve this evidence: a manual upload can conceal a background-delivery failure.

Interpret an increasing observation age with an empty queue as a possible collection pause. A growing queue suggests an upload problem. Confirm with receiver evidence rather than treating either clue as proof.

Explain that Send Interval governs sending available points; it does not force a fresh GPS sample at every interval. With Pause Updates Automatically enabled, stationary silence can be expected. Remaining immobile supports that explanation but does not validate automatic resumption.

Test resumption by walking with the iPhone locked, without opening Overland or pressing Send Now, then checking canonical samples again. Compare observation and reception timestamps.

## Preserve small movements and verify installed settings

Inspect the actual app settings before prescribing controls. The upstream source examined in this session contained Discard points while stationary, but Monsieur's installed version did not expose it. Do not claim that a setting exists merely because it appears on the repository's current branch. That upstream behavior also retained an hourly checkpoint; it was not a guarantee of zero overnight transmissions.

For the condo baseline used in this session: retain requested accuracy of 10 m, Tracking Mode Both, Visit Tracking On, and Min Distance Between Points Off. The existing pause and resume settings were Yes and 100 m, with a 30 s send interval and All Data. Treat these as a baseline requiring a real background-resumption test, not a proven solution.

Do not introduce a 100 m point-discard filter to save battery when Monsieur needs short movements. A requested accuracy of 10 m is not a guaranteed measurement accuracy.

A 100 m resume geofence may miss movement between floors of the same building. GPS accuracy alone cannot identify the floor. Overland WiFi Zone substitutes configured fixed coordinates while connected to the network; it does not establish that GPS stops or that overnight uploads cease. Distinct Wi-Fi networks may help identify places only if the integration receives a usable distinguishing signal. The same network across floors cannot distinguish them by itself.

## Validate changes before declaring success

Server-side settings prepared for return to Overland require another successful app exchange before claiming delivery. Verify receipt and subsequent behavior.

Before code changes, back up the affected files. Run the relevant Overland tests and inspect the receiver after restart. After changes to memory services, run `systemctl start memory-autopilot` and inspect `/root/.hermes/logs/memory-autopilot/latest.json`.

Distinguish successful initial ingestion, ongoing automatic delivery, and successful resumption after a pause. Claim each only when observed.
