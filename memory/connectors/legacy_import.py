#!/usr/bin/env python3
"""One-shot (idempotent) import of pre-Walter-Memory history (P2.4).

  kardex.messages (observed messages collected by the old Kardex pipelines) → core.events, source kardex_legacy
  Hindsight memory_units + documents (derived)                              → core.derived_items, legacy_derived (A2)
  user_model.* (profile compiler output, derived)                            → core.derived_items, legacy_derived (A2)

Derived rows keep their provenance (hindsight ids, state.db session/message → hermes events) and can never be
promoted automatically (trigger core.guard_legacy_promotion).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import events, ingestion, privacy  # noqa: E402
from walter_memory.db import connection  # noqa: E402

CONFLICT = "on conflict (derived_by, (source_refs->>'ref')) where source_refs ? 'ref' do nothing"
SENS = """case when lower(coalesce({col}::text,'')) in ('high','sensitive','highly_sensitive','private','intimate') then 'local_only'
               when lower(coalesce({col}::text,'')) in ('medium','personal') then 'redacted_cloud' else 'cloud_allowed' end"""


def import_kardex_messages() -> dict:
    with connection() as conn:
        rows = conn.execute("""select m.id, m.contact_id, m.source, m.sender, m.text, m.timestamp, m.has_attachments,
                                      m.attachment_types, m.source_message_id, c.canonical_name, c.handles
                               from kardex.messages m left join kardex.contacts c on c.id = m.contact_id
                               order by m.id""").fetchall()
    batch, inserted = [], 0
    for r in rows:
        is_self = r["sender"] == "lucas"
        actor = ({"account": r["source"], "external_id": "lucas", "display_name": "Monsieur", "is_self": True} if is_self else
                 {"account": r["source"], "external_id": f"kardex_contact:{r['contact_id']}", "display_name": r["canonical_name"],
                  "handles": r["handles"] or {}})
        batch.append({"event_type": "message.sent" if is_self else "message.received", "source": "kardex_legacy",
                      "source_account": r["source"], "source_id": f"{r['source']}|{r['source_message_id'] or r['id']}",
                      "occurred_at": r["timestamp"], "content": r["text"] or None, "actor": actor,
                      "thread_id": f"kardex_contact:{r['contact_id']}",
                      "payload": {"chat": {"id": f"kardex_contact:{r['contact_id']}", "title": r["canonical_name"],
                                           "type": "single", "network": r["source"]},
                                  "attachments": [{"type": t} for t in (r["attachment_types"] or [])],
                                  "kardex_message_id": r["id"]}})
        if len(batch) == 2000:
            inserted += events.record_events(batch)["inserted"]; batch = []
    if batch:
        inserted += events.record_events(batch)["inserted"]
    return {"kardex_messages": len(rows), "events_inserted": inserted}


def import_hindsight() -> dict:
    with connection() as conn:
        u = conn.execute(f"""
            insert into core.derived_items (kind, content, attributes, status, derived_by, source_refs, valid_from,
                                            created_at, privacy_class)
            select case when m.fact_type = 'observation' then 'observation' else 'memory' end, m.text,
                   jsonb_strip_nulls(jsonb_build_object('fact_type', m.fact_type, 'tags', m.tags, 'context', m.context,
                       'proof_count', m.proof_count, 'usefulness', l.label,
                       'quarantined', 'quarantine:noise' = any(m.tags))),
                   'legacy_derived', 'hindsight',
                   jsonb_strip_nulls(jsonb_build_object('ref', 'hindsight_unit:' || m.id, 'bank', m.bank_id,
                       'document_id', m.document_id,
                       'session', (select substr(t, 9) from unnest(m.tags) t where t like 'session:%' limit 1))),
                   coalesce(m.occurred_start, m.mentioned_at), m.created_at, 'cloud_allowed'
            from public.memory_units m left join walter_audit.memory_labels l on l.unit_id = m.id
            {CONFLICT}""").rowcount
        d = conn.execute(f"""
            insert into core.derived_items (kind, content, attributes, status, derived_by, source_refs, created_at,
                                            privacy_class)
            select 'document', d.original_text, jsonb_build_object('tags', d.tags, 'metadata', d.metadata),
                   'legacy_derived', 'hindsight',
                   jsonb_strip_nulls(jsonb_build_object('ref', 'hindsight_document:' || d.id, 'bank', d.bank_id,
                       'session', (select substr(t, 9) from unnest(d.tags) t where t like 'session:%' limit 1))),
                   d.created_at, 'cloud_allowed'
            from public.documents d where d.original_text is not null {CONFLICT}""").rowcount
        # provenance: Hindsight rows tagged with a Hermes session → that conversation's events
        linked = conn.execute("""
            update core.derived_items di set source_event_ids = array[e.event_id]
            from core.event_keys e
            where di.derived_by = 'hindsight' and di.source_refs ? 'session' and di.source_event_ids = '{}'
              and e.source = 'hermes' and e.event_type = 'conversation.started'
              and e.source_id = 'session:' || (di.source_refs->>'session') || ':start'""").rowcount
    return {"hindsight_units": u, "hindsight_documents": d, "linked_to_sessions": linked}


USER_MODEL = {  # table → (kind, content sql, ref key sql, sensitivity column, observed time)
    "profile_state": ("profile", "key || ': ' || current_value::text", "key", "sensitivity", "last_seen_at"),
    "preference_history": ("preference", "preference_key || ' = ' || value::text", "id::text", "sensitivity", "valid_from"),
    "decision_events": ("decision", "decision_summary", "id::text", "sensitivity", "observed_at"),
    "psychological_profile": ("psych_hypothesis", "trait_key || ': ' || coalesce(current_assessment::text, hypothesis::text)", "trait_key", "sensitivity", "last_seen_at"),
    "life_signals": ("life_signal", "signal_type || ': ' || value::text", "id::text", "sensitivity", "observed_at"),
    "outcomes": ("outcome", "outcome_summary", "id::text", "sensitivity", "observed_at"),
    "bias_hypotheses": ("bias_hypothesis", "hypothesis", "key", "sensitivity", "last_seen_at"),
    "proactive_advice_rules": ("advice_rule", "rule", "key", "sensitivity", "updated_at"),
    "signal_candidates": ("signal_candidate", "claim", "id::text", "sensitivity", "observed_at"),
}


def import_user_model() -> dict:
    out = {}
    with connection() as conn:
        for table, (kind, content, ref, sens, when) in USER_MODEL.items():
            out[table] = conn.execute(f"""
                insert into core.derived_items (kind, content, attributes, status, derived_by, source_refs, valid_from,
                                                privacy_class)
                select '{kind}', {content}, to_jsonb(t) - 'embedding', 'legacy_derived', 'user_model_compiler',
                       jsonb_build_object('ref', '{table}:' || {ref}), {when}, {SENS.format(col=sens)}
                from user_model.{table} t where {content} is not null {CONFLICT}""").rowcount
        # provenance: candidates carry their state.db session/message → the hermes message event
        out["linked_to_messages"] = conn.execute("""
            update core.derived_items di set source_event_ids = array[k.event_id]
            from core.event_keys k
            where di.derived_by = 'user_model_compiler' and di.kind in ('signal_candidate', 'decision')
              and di.source_event_ids = '{}' and di.attributes ? 'message_id'
              and k.source = 'hermes' and k.event_type in ('message.sent', 'message.received')
              and k.source_id = 'msg:' || (di.attributes->>'message_id')""").rowcount
    return out


def classify_derived() -> dict:
    """Secrets/sensitive content in legacy derived text → stricter privacy class."""
    changed = 0
    with connection() as conn:
        rows = conn.execute("""select item_id, content, privacy_class from core.derived_items
                               where status = 'legacy_derived' and privacy_class <> 'local_only'""").fetchall()
        for r in rows:
            det = privacy.detect(r["content"])
            if not det:
                continue
            cls, _ = privacy.classify(conn, {"source": "hindsight_legacy", "categories": {c for c, _ in det}})
            cls = privacy.strictest(cls, r["privacy_class"])
            if cls != r["privacy_class"]:
                conn.execute("update core.derived_items set privacy_class = %s where item_id = %s", (cls, r["item_id"]))
                changed += 1
            for cat, rule in dict.fromkeys(det):
                conn.execute("""insert into privacy.detections (target_type, target_ref, category, rule, action)
                                values ('derived', %s, %s, %s, %s)""",
                             (str(r["item_id"]), cat, rule, "flagged_for_purge" if cat == "secret" else "classified_" + cls))
    return {"reclassified": changed}


def main() -> None:
    ingestion.register_connector("legacy_import", "hindsight_legacy", "import",
                                 "One-shot import of Kardex messages, Hindsight and user_model history")
    res = {**import_kardex_messages(), **import_hindsight(), "user_model": import_user_model(), **classify_derived()}
    ingestion.mark_success("legacy_import")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
