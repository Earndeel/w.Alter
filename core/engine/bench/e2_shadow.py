"""Lot E2 shadow report: what the engine's intake and events plugins observed, against what walter_hook.py did.

Read-only. Sources (instance state, private): the plugins' observations (state/core/engine/intake/observations-*.jsonl,
shadow rows only) and the preflight rows the hook's context pack records for DSH (state/context/shadow/preflight-*.jsonl,
runtime dsh, mode inject); the bus (turn.ended from source dsh) for the events side. Joined by session and owner-text
hash, nearest in time.

Adoption criteria (03-MIGRATION § E2): zero intent gap over the week, latency equal or better (04-BASELINE § 2).
An intent gap only counts against the intake when the owner text differs (message_sha): with the same text the
request is the same and a different plan comes from the decision model's sampling, reported apart as `model_noise`.

    walter-python core/engine/bench/e2_shadow.py [--since 2026-11-11] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

INTENT = ("act", "level", "task")
WINDOW_S = 120


def instance() -> Path:
    return Path(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True).stdout.strip())


def _rows(folder: Path, pattern: str, since: datetime):
    for f in sorted(folder.glob(pattern)):
        for line in f.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            at = datetime.fromisoformat(str(r.get("at", "")).replace("Z", "+00:00")) if r.get("at") else None
            if at and at >= since:
                r["_at"] = at
                yield r


def plan_of(p: dict | None) -> dict | None:
    if not p:
        return None
    return {"act": p.get("act"), "level": p.get("level"), "task": (p.get("model_profile") or {}).get("task", p.get("task"))}


def report(since: datetime) -> dict:
    root = instance()
    obs = [r for r in _rows(root / "state/core/engine/intake", "observations-*.jsonl", since) if r.get("observation")]
    hook = [r for r in _rows(root / "state/context/shadow", "preflight-*.jsonl", since)
            if r.get("runtime") == "dsh" and r.get("mode") == "inject" and r.get("run_id")]
    shadow_turns = [r for r in obs if r.get("kind") == "intake"]
    used, pairs, unmatched_shadow = set(), [], []
    for s in shadow_turns:
        best = None
        for i, h in enumerate(hook):
            if i in used or h.get("session_id") != s.get("session"):
                continue
            dt = abs((h["_at"] - s["_at"]).total_seconds())
            if dt <= WINDOW_S and (best is None or dt < best[0]):
                best = (dt, i)
        if best is None:
            unmatched_shadow.append(s)
            continue
        used.add(best[1])
        pairs.append((s, hook[best[1]]))
    gaps, noise, same_text = [], [], 0
    for s, h in pairs:
        a, b = s.get("plan"), plan_of(h.get("plan"))
        text_equal = s.get("message_sha") == h.get("message_sha")
        same_text += text_equal
        if a is None or b is None:
            continue
        diff = [k for k in INTENT if a.get(k) != b.get(k)]
        if diff:
            (noise if text_equal else gaps).append({"session": s.get("session"), "fields": diff,
                                                    "shadow": {k: a.get(k) for k in diff}, "hook": {k: b.get(k) for k in diff}})
    unseen_by_shadow = [h for i, h in enumerate(hook) if i not in used]
    events = [r for r in obs if r.get("kind") == "event"]
    shadow_ends = sum(1 for r in events if r.get("type") == "turn.ended")
    bus_ends = None
    try:
        from walter_memory.db import connect
        with connect() as c:
            bus_ends = c.execute("""select count(*) n from bus.events where type = 'turn.ended' and source = 'dsh'
                                    and at >= %s""", (since,)).fetchone()["n"]
    except Exception as e:  # noqa: BLE001 — the report still says what it can
        bus_ends = f"unavailable: {type(e).__name__}"
    ms = sorted(r["native_ms"] for r in shadow_turns if isinstance(r.get("native_ms"), int))
    pct = lambda q: ms[min(len(ms) - 1, int(q * len(ms)))] if ms else None  # noqa: E731
    return {
        "since": since.isoformat(), "shadow_turns": len(shadow_turns), "hook_plans": len(hook), "paired": len(pairs),
        "owner_text_identical": same_text, "intent_gaps": gaps, "model_noise": noise,
        "shadow_without_hook_plan": len(unmatched_shadow), "hook_plan_without_shadow": len(unseen_by_shadow),
        "skipped_local_only": sum(1 for r in shadow_turns if r.get("skipped") == "local_only"),
        "errors": sum(1 for r in shadow_turns if r.get("error")),
        "preflight_path_ms": {"p50": pct(0.5), "p90": pct(0.9), "n": len(ms)},
        "events": {"shadow_turn_ended": shadow_ends, "bus_turn_ended_dsh": bus_ends,
                   "shadow_session_ended": {k: sum(1 for r in events if r.get("type") == "session.ended" and r.get("reason") == k)
                                            for k in ("archived", "disposed")}},
        "adoption": {"zero_intent_gap": not gaps and not unmatched_shadow and not unseen_by_shadow and len(pairs) > 0},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date (UTC); default: 7 days ago")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    since = (datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc) if a.since
             else datetime.now(timezone.utc) - timedelta(days=7))
    print(json.dumps(report(since), ensure_ascii=False, indent=None if a.json else 1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
