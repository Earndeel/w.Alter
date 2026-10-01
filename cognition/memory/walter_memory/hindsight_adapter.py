"""Hindsight adapter (P5, §12/§32): Hindsight is a replaceable cognitive layer fed ONLY by the router.

Retains Walter Memory derived knowledge (conversation summaries, decisions, preferences, facts) into a Hindsight bank,
with document_id = derived item ref and metadata pointing back to the canonical events (provenance survives inside
Hindsight). Shadow mode: bank `walter-shadow` until the P7 cutover; the live bank `walter` keeps Hermes' per-turn retain.
"""
from __future__ import annotations

import json

import httpx

from . import ingestion
from .db import connection

URL = "http://127.0.0.1:8888/v1/default/banks"
KINDS = ("summary", "decision", "preference", "fact")
RETAIN_MISSION = ("Mémoire personnelle de Monsieur, utilisateur unique de W.Alter. RETENIR : faits durables sur Monsieur, "
                  "ses proches, ses projets et entreprises, ses décisions et leurs raisons, ses préférences et règles pour "
                  "W.Alter. IGNORER : détails techniques internes, comptes rendus d'exécution. Écrire en français.")


def ensure_bank(bank: str) -> None:
    r = httpx.get(f"{URL}/{bank}/profile", timeout=30)
    if r.status_code == 404 or (r.status_code == 200 and not r.json()):
        httpx.put(f"{URL}/{bank}", json={"name": bank, "retain_mission": RETAIN_MISSION,
                                         "mission": "Mémoire de W.Alter alimentée par le routeur Walter Memory."}, timeout=30).raise_for_status()


def push(bank: str = "walter-shadow", limit: int = 500) -> dict:
    """Retain derived items not yet sent to this bank (cursor = created_at)."""
    ensure_bank(bank)
    connector = f"hindsight_adapter:{bank}"
    with connection() as conn:
        conn.execute("""insert into ingestion.connectors (connector, source, mode, description) values (%s, 'walter', 'push', %s)
                        on conflict do nothing""", (connector, f"router → Hindsight bank {bank}"))
    cp = ingestion.get_checkpoint(connector)
    with connection() as conn:
        rows = conn.execute("""select item_id::text, kind, content, attributes, source_event_ids, source_refs, valid_from, created_at
                               from core.derived_items
                               where derived_by = 'l3.conversation_summary' and status = 'derived' and kind = any(%s)
                                 and privacy_class = 'cloud_allowed' and created_at > %s
                               order by created_at limit %s""",
                            (list(KINDS), cp.get("created_at", "1970-01-01"), limit)).fetchall()
    if not rows:
        return {"retained": 0}
    items = [{"content": r["content"] if r["kind"] == "summary" else f"[{r['kind']}] {r['content']}",
              "timestamp": r["valid_from"].isoformat() if r["valid_from"] else None,
              "context": f"Walter Memory {r['kind']} (session {r['source_refs'].get('session')})",
              "document_id": f"wm:{r['source_refs'].get('ref') or r['item_id']}",
              "metadata": {"walter_item_id": r["item_id"], "kind": r["kind"],
                           "source_event_ids": json.dumps([str(e) for e in r["source_event_ids"][:50]])},
              "tags": [f"wm:{r['kind']}", f"session:{r['source_refs'].get('session')}"]} for r in rows]
    for i in range(0, len(items), 50):
        httpx.post(f"{URL}/{bank}/memories", json={"items": items[i:i + 50], "async": True}, timeout=120).raise_for_status()
    ingestion.set_checkpoint(connector, "", {"created_at": rows[-1]["created_at"].isoformat()})
    ingestion.mark_success(connector)
    return {"retained": len(items), "bank": bank}
