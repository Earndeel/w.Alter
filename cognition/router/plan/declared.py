"""The owner's plans (subscriptions), editable from anywhere (owner, 2026-10-22: « les plans peuvent être ajoutés dans
la discussion si j'indique des changements, par events en analysant les mails, ou modifiés dans l'interface »).
One writer for the instance's subscriptions.json: the CLI (`walter-router plans …`), the plan-change alerts adopted
on Telegram, and the library page's form all go through `upsert` / `retire`. Every write keeps the previous file in
the instance's history (config/router/history/)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance

EDITABLE = {"vendor": str, "plan": str, "price_usd_month": float, "execution": str, "route_provider": str,
            "models": list, "note": str, "currency_note": str, "since": str, "until": str, "list_price_usd_month": float}


def _path() -> Path:
    return instance.config_path("subscriptions.json")


def read() -> dict:
    return json.loads(_path().read_text())


def _write(doc: dict, why: str) -> Path:
    target = instance.own_file("subscriptions.json")   # the instance's own copy, never the shipped default
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        hist = target.parent / "history"
        hist.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")   # several edits in one second each keep theirs
        (hist / f"subscriptions-{stamp}.json").write_text(target.read_text())
    doc.setdefault("changes", []).append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "why": why})
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    instance.config_path.cache_clear()
    return target


def upsert(sub_id: str, fields: dict, why: str, source: str = "owner") -> dict:
    """Create or change one plan. Unknown fields are refused; a new plan needs vendor, plan and price."""
    bad = sorted(set(fields) - set(EDITABLE))
    if bad:
        raise ValueError(f"not editable: {bad} (editable: {sorted(EDITABLE)})")
    clean = {k: (EDITABLE[k](v) if EDITABLE[k] is not list else [str(x) for x in v]) for k, v in fields.items() if v is not None}
    doc = read()
    subs = doc.setdefault("subscriptions", [])
    cur = next((s for s in subs if s["id"] == sub_id), None)
    if cur is None:
        missing = [k for k in ("vendor", "plan", "price_usd_month") if k not in clean]
        if missing:
            raise ValueError(f"new plan {sub_id!r} needs {missing}")
        cur = {"id": sub_id, "declared": datetime.now(timezone.utc).date().isoformat(), "meter": {"source": "none"},
               "usage_sources": []}
        subs.append(cur)
    before = {k: cur.get(k) for k in clean}
    cur.update(clean)
    cur["updated"] = datetime.now(timezone.utc).date().isoformat()
    cur["updated_by"] = source
    _write(doc, f"{source}: {sub_id} {json.dumps(before, ensure_ascii=False)} -> {json.dumps(clean, ensure_ascii=False)} ({why})")
    return {"id": sub_id, "before": before, "after": clean}


def retire(sub_id: str, why: str, source: str = "owner") -> dict:
    """A cancelled plan leaves the active list but stays in `retired` with its date."""
    doc = read()
    subs = doc.get("subscriptions", [])
    cur = next((s for s in subs if s["id"] == sub_id), None)
    if cur is None:
        raise KeyError(f"unknown plan {sub_id!r}")
    doc["subscriptions"] = [s for s in subs if s["id"] != sub_id]
    doc.setdefault("retired", []).append({**cur, "retired": datetime.now(timezone.utc).date().isoformat(), "why": why})
    _write(doc, f"{source}: retired {sub_id} ({why})")
    return {"retired": sub_id}


def bind_claude_meter(sub_id: str, why: str) -> dict:
    """One-writer activation of the real Claude quota and bridge usage, preserving plan/price/history."""
    document = read()
    sub = next((s for s in document["subscriptions"] if s["id"] == sub_id), None)
    if sub is None:
        raise KeyError("subscription must already be declared by its owner")
    sub["meter"] = {"source": "claude_usage_api", "note": "Live five-hour and weekly subscription windows via Walter Secrets grant."}
    sources = sub.setdefault("usage_sources", [])
    if "walter_claude" not in sources:
        sources.append("walter_claude")
    _write(document, why)
    return {"id": sub_id, "meter_source": "claude_usage_api", "usage_sources": sources}


def expiring(conn, days: int = 30) -> list[str]:
    """A dated offer (`until`, e.g. Google AI Pro 15 months) ending within `days` becomes one Telegram notice."""
    from datetime import date
    from walter_router.analysis import alerts
    out = []
    for sub in read().get("subscriptions", []):
        until = sub.get("until")
        try:
            left = (date.fromisoformat(until) - date.today()).days if until else None
        except ValueError:
            continue
        if left is not None and 0 <= left <= days:
            ev = {"action": "none", "sub_id": sub["id"], "vendor": sub.get("vendor"), "plan": sub.get("plan"),
                  "mail_date": until, "text": f"l'offre {sub.get('plan')} se termine le {until} (dans {left} jours)",
                  "quote": sub.get("note") or ""}
            if alerts.record(conn, "plan_change", "", f"{sub['id']}:ends:{until}", ev, "open"):
                out.append(sub["id"])
    return out
