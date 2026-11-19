"""V3 — environmental input triage (2026-10-04).

Every new INCOMING event (a Beeper message from someone else, a received e-mail, a calendar event) gets one decision:
  ignore · remember (stored, that's all) · notify (tell Monsieur) · prepare_reply (draft something for him)
with urgency (now / today / later), category and needs_reply.

1. Context Lite, privacy-safe: thread kind (1:1 / group), network, how active and reciprocal the thread is (from
   core.events), whether Monsieur already answered, whether he is mentioned, the last few messages of the thread
   (pseudonymised by walter_memory.llm for redacted_cloud; text dropped entirely for local_only).
2. Decision model through walter_memory.llm.decide: the Router's decision chain. Since 17/11 (Walter Decision 2.0)
   asked by occasion `incoming`: the questions are Memory's declared signals (manifest/decisions.json: action,
   urgency, category, needs_reply; and, when the message carries a date or an amount, the deadline and the amount
   it sets, read on a model that has an extraction route, in parallel). The values read are kept in
   payload.observations (ISO day, amount: never the text); a deadline within a day raises urgency `later` to
   `today`, a finance item with an amount is never ignored.
3. Monsieur's deterministic rules (config/triage_rules.json): muted / VIP threads and people, groups only when
   mentioned or urgent, silence hours (Asia/Bangkok), e-mail categories never notified, hourly cap. Muted threads and
   silent groups (networks in silent_group_networks where Monsieur neither writes nor is mentioned) are settled
   before any model call (2026-11-05).
One decision per thread per run (the latest incoming message); every other incoming event of the burst is
'remember'. SHADOW by default: decisions are recorded in triage.decisions, nothing is sent.

A failed decision is never final (socle M2, 2026-11-11: during the 11-11 outage 135 decisions were stored with
payload.error and the fallback 'remember', and `on conflict do nothing` made them final). When the decision model
fails, nothing is stored for that event: the next pass re-selects it (events without a decision ingested within
RETRY_WINDOW are taken again even behind the checkpoint). Only once the window is over is the fallback stored, error
kept, so an event is never lost. `redecide_errors()` (`walter-memory tasks triage-redecide`) re-decides rows already
stored with payload.error; the new decision replaces the row and keeps the old one in payload.previous.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import events, ingestion, llm
from .db import connection

RULES = Path(__file__).resolve().parent.parent / "config" / "triage_rules.json"
CONNECTOR = "triage"
KINDS = {("beeper", "message.received"), ("gmail", "email.received"), ("calendar", "calendar.event")}
THREAD_WINDOW = 6
TEXT_CAP = 400
RETRY_WINDOW = timedelta(hours=48)     # a failed decision is retried this long, then the fallback is stored

MANIFEST = Path(__file__).resolve().parent.parent / "manifest" / "decisions.json"
FOUND_MIN = 0.5                        # a value read with less certainty is not kept


def signals(occasion: str) -> dict:
    """Memory's declared decision signals for one occasion (manifest/decisions.json, Walter Decision 2.0): the only
    place the triage questions are written."""
    doc = json.loads(MANIFEST.read_text())
    return {n: s for n, s in doc["signals"].items() if occasion in s["occasions"]}


# Asked of every incoming event (the judgements); the readings (deadline, amount) are added by Walter Decision when
# the message carries a date or an amount (their `when`). The decision is asked by occasion: Walter Decision composes
# these with any other module's incoming signals.
QUESTIONS = {n: s["question"] for n, s in signals("incoming").items() if not s.get("when")}


def observed(sig: dict) -> dict:
    """The values read in the latest message, as values only (an ISO day, an amount), never its text."""
    out = {}
    dl = sig.get("memory.deadline") or {}
    if isinstance(dl.get("date"), str) and (dl.get("found") is None or dl["found"] >= FOUND_MIN):
        try:
            # a period (« cette semaine », 18/11) is due by its last day
            out["deadline"] = datetime.fromisoformat((dl.get("end") or dl["date"])[:10]).date().isoformat()
        except ValueError:
            pass
    am = sig.get("memory.amount") or {}
    if isinstance(am.get("number"), (int, float)) and (am.get("found") is None or am["found"] >= FOUND_MIN):
        out["amount"] = {"value": am["number"], "unit": am.get("unit") or "EUR"}
    return out


def rules() -> dict:
    return json.loads(RULES.read_text())


def _thread_context(conn, ev: dict, self_names: list[str]) -> dict:
    """Context Lite of one incoming event's thread (no raw identity, text capped)."""
    rows = list(conn.execute("""select event_id, source, source_id, object_refs, event_type, occurred_at, content, payload,
                                       privacy_class from core.events
                                where source = %s and thread_id = %s and occurred_at <= %s
                                  and event_type in ('message.received', 'message.sent', 'email.received', 'email.sent')
                                order by occurred_at desc limit %s""",
                             (ev["source"], ev["thread_id"], ev["occurred_at"], THREAD_WINDOW)))
    stats = conn.execute("""select count(*) filter (where event_type like '%%sent') as mine,
                                   count(*) filter (where event_type like '%%received') as theirs,
                                   max(occurred_at) filter (where event_type like '%%sent') as last_mine
                            from core.events where source = %s and thread_id = %s
                              and occurred_at > now() - interval '30 days'""",
                         (ev["source"], ev["thread_id"])).fetchone()
    p = ev["payload"] or {}
    chat = p.get("chat") or {}
    # a voice note or a document carries its words in its file's derived text (transcript, extract), read here as
    # every reader does (events.attachments); the incoming event itself is always among the rows
    atts = events.attachments([r for r in rows if r["privacy_class"] != "local_only"], max_privacy="redacted_cloud",
                              chars=TEXT_CAP, conn=conn)

    def said(r) -> str:
        parts = [r["content"] or ""] + [f"[{a.get('kind') or 'fichier'} : {a['text']}]"
                                        for a in atts.get(str(r["event_id"]), []) if a.get("text")]
        return " ".join(x for x in parts if x).strip()
    own = next((r for r in rows if r["event_id"] == ev["event_id"]), None)
    text = said(own) if own else (ev["content"] or "")
    mentioned = any(n.lower() in text.lower() for n in self_names) or bool(p.get("mentions"))
    local = ev["privacy_class"] == "local_only"
    msgs = [] if local else [
        {"from": "Monsieur" if r["event_type"].endswith("sent") else "other",
         "minutes_ago": int((ev["occurred_at"] - r["occurred_at"]).total_seconds() // 60),
         "text": said(r)[:TEXT_CAP], "type": (r["payload"] or {}).get("message_type")}
        for r in reversed(rows) if r["privacy_class"] != "local_only"]
    return {"source": ev["source"], "network": chat.get("network") or ev["source"],
            "thread_kind": chat.get("type") or ("email" if ev["source"] == "gmail" else "event"),
            "monsieur_messages_30d": stats["mine"], "their_messages_30d": stats["theirs"],
            "monsieur_answered_after": bool(stats["last_mine"] and stats["last_mine"] > ev["occurred_at"]),
            "monsieur_mentioned": mentioned, "subject": None if local else p.get("subject"),
            "labels": p.get("labels"), "attachments": len(p.get("attachments") or []),
            "messages": msgs, "content_withheld": local}


def _without_model(r: dict, ev: dict, ctx: dict) -> tuple[str, str] | None:
    """Decisions Monsieur's rules settle before any model call (2026-11-05: Line groups cost 125 decision calls a
    week, 123 of them 'ignore')."""
    thread, people = ev["thread_id"] or "", (ev["payload"] or {}).get("sender_name") or ""
    if thread in r["muted_threads"]:
        return "remember", "muted thread"
    if thread in r["vip_threads"] or people in r["vip_people"]:
        return None
    if (ctx["thread_kind"] == "group" and (ctx["network"] or "").lower() in r.get("silent_group_networks", [])
            and not ctx["monsieur_messages_30d"] and not ctx["monsieur_mentioned"]):
        return "ignore", "silent group: Monsieur does not write there and is not mentioned"
    return None


def _apply_rules(r: dict, ev: dict, ctx: dict, d: dict, now_local: datetime, sent_last_hour: int) -> tuple[str, str]:
    action, rule = d["action"], ""
    if d.get("deadline") and d.get("urgency") == "later":       # a day set for tomorrow is not « whenever »
        days = (datetime.fromisoformat(d["deadline"]).date() - now_local.date()).days
        if 0 <= days <= 1:
            d["urgency"], rule = "today", "deadline within a day"
    if action == "ignore" and d.get("amount") and d.get("category") == "finance":
        action, rule = "remember", "amount to pay or receive: kept"
    thread, people = ev["thread_id"] or "", (ev["payload"] or {}).get("sender_name") or ""
    if thread in r["vip_threads"] or people in r["vip_people"]:
        if action in ("ignore", "remember"):
            action, rule = "notify", "VIP"
    if ctx["monsieur_answered_after"] and action in ("notify", "prepare_reply"):
        return "remember", "already answered"
    if ctx["thread_kind"] == "group" and action in ("notify", "prepare_reply") and not (
            ctx["monsieur_mentioned"] or d["urgency"] == "now"):
        return "remember", "group without mention"
    if ev["source"] == "gmail" and d["category"] in r["email_categories_never_notified"] and action != "ignore":
        return "remember" if action != "ignore" else action, "e-mail category"
    start, end = r["silence_hours"]
    silent = now_local.hour >= start or now_local.hour < end
    if silent and action in ("notify", "prepare_reply") and d["urgency"] != "now":
        rule = (rule + "; " if rule else "") + "silence hours: deferred to morning"
    if action in ("notify", "prepare_reply") and sent_last_hour >= r["max_notifications_per_hour"] and d["urgency"] != "now":
        rule = (rule + "; " if rule else "") + "hourly cap: deferred"
    return action, rule


def _self_names() -> list[str]:
    from_bench = Path(__file__).resolve().parent.parent / "bench" / "media_triage_jev.py"
    if from_bench.exists():  # Monsieur's names (single list already used by the media triage bench)
        import re
        m = re.search(r"SELF_NAMES = (\[.*?\])", from_bench.read_text())
        return json.loads(m.group(1)) if m else []
    return []


EVENT_COLUMNS = """e.event_id, e.event_type, e.source, e.source_id, e.object_refs, e.thread_id, e.occurred_at,
                   e.ingested_at, e.content, e.payload, e.privacy_class"""


def run(limit: int = 200, dry: bool = False) -> dict:
    cur = ingestion.get_checkpoint(CONNECTOR, "events")
    since = cur.get("ingested_at") or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with connection() as conn:
        # new events after the checkpoint, and events behind it still without a decision (a failed decision is
        # stored nowhere, so it is taken again here until RETRY_WINDOW is over)
        evs = list(conn.execute(f"""select {EVENT_COLUMNS}
                                   from core.events e
                                   where e.ingested_at > least(%s::timestamptz, now() - %s)
                                     and (e.source, e.event_type) in
                                         (('beeper','message.received'), ('gmail','email.received'),
                                          ('calendar','calendar.event'))
                                     and not exists (select 1 from triage.decisions d where d.event_id = e.event_id)
                                   order by e.ingested_at limit %s""", (since, RETRY_WINDOW, limit)))
    if not evs:
        return {"decided": 0}
    out = _decide(evs, dry=dry)
    if not dry:
        last = max(evs, key=lambda e: e["ingested_at"])
        if last["ingested_at"] > datetime.fromisoformat(since):
            with connection() as conn:
                ingestion.set_checkpoint(CONNECTOR, "events", {"ingested_at": last["ingested_at"].isoformat()},
                                         last_item_at=last["occurred_at"], conn=conn)
    return out


AWAIT_TEXT = timedelta(minutes=10)      # an incoming file without derived text yet is waited for this long


def _awaiting_text(conn, ev: dict, now: datetime) -> bool:
    """The incoming message's own file (a voice note…) has no derived text yet and was received recently: its
    transcript lands within seconds (media.derive) and re-marks the triage, so the decision waits for its words."""
    if now - ev["ingested_at"] > AWAIT_TEXT or not (ev.get("payload") or {}).get("attachments"):
        return False
    row = {"event_id": ev["event_id"], "source": ev["source"], "source_id": ev.get("source_id"),
           "object_refs": ev.get("object_refs")}
    files = events.attachments([row], max_privacy="local_only", conn=conn).get(str(ev["event_id"]), [])
    if not files:            # the file itself is not stored yet (download queued)
        return any((a or {}).get("isVoiceNote") or str((a or {}).get("type")) in ("audio", "AUDIO")
                   for a in (ev.get("payload") or {}).get("attachments") or [])
    return any(f.get("text") is None and f.get("kind") in ("audio", "document") for f in files)


def _decide(evs: list[dict], *, dry: bool = False, replace_errors: bool = False) -> dict:
    """One decision per event (the latest of each thread decided, the rest of the burst 'remember'). A failed model
    call stores nothing (retried by the next pass) unless the event is past RETRY_WINDOW. replace_errors: rows already
    stored with payload.error are overwritten (previous row kept in payload.previous); other rows never change."""
    r = rules()
    self_names = _self_names()
    latest: dict[tuple, dict] = {}
    for ev in evs:  # one decision per thread per run: the latest incoming event
        key = (ev["source"], ev["thread_id"] or str(ev["event_id"]))
        if key not in latest or ev["occurred_at"] > latest[key]["occurred_at"]:
            latest[key] = ev
    tz = ZoneInfo(r["timezone"])
    out = {"decided": 0, "by_action": {}, "errors": 0, "retry_later": 0}
    now = datetime.now(timezone.utc)
    with connection() as conn:
        sent_last_hour = conn.execute("""select count(*) as n from triage.decisions where delivered_at > now() - interval '1 hour'
                                         """).fetchone()["n"]
        for ev in evs:
            key = (ev["source"], ev["thread_id"] or str(ev["event_id"]))
            if latest[key]["event_id"] != ev["event_id"]:
                rec = {"action": "remember", "rule": "same burst: decided on the latest message", "d": {}}
            else:
                ctx = _thread_context(conn, ev, self_names)
                if _awaiting_text(conn, ev, now):
                    out["retry_later"] += 1      # its file's text is on its way: decided when it lands (or later)
                    continue
                settled = _without_model(r, ev, ctx)
                if settled:  # Monsieur's rules decide alone: no model call
                    out["without_model"] = out.get("without_model", 0) + 1
                    d = {}
                    action, rule = settled
                else:
                    try:
                        # asked by occasion (Walter Decision 2.0): the questions are this module's declared
                        # signals; dates in words are read against the day the message was received
                        res = llm.decide(ctx, None, processor="triage", privacy_class=ev["privacy_class"]
                                         if ev["privacy_class"] != "local_only" else "redacted_cloud",
                                         names=self_names, purpose="environmental triage", occasion="incoming",
                                         focus="messages", now=ev["occurred_at"].astimezone(tz).date().isoformat())
                        sig = res.get("signals") or {}
                        a = {k.split(".", 1)[1]: v for k, v in sig.items() if k.startswith("memory.") and v}
                        d = {"action": a["action"]["choice"], "urgency": (a.get("urgency") or {}).get("choice"),
                             "category": (a.get("category") or {}).get("choice"),
                             "needs_reply": (a["needs_reply"].get("noul") or 0) >= 0.5   # noul = probability of yes
                             if a.get("needs_reply") else None,
                             "confidence": a["action"]["confidence"], "model": res["model"], **observed(sig),
                             **({"unavailable": sorted(res["trace"]["unavailable"])}
                                if (res.get("trace") or {}).get("unavailable") else {})}
                    except Exception as exc:  # noqa: BLE001
                        out["errors"] += 1
                        if now - ev["ingested_at"] < RETRY_WINDOW:
                            out["retry_later"] += 1          # not stored: the next pass decides it again
                            continue
                        # past the retry window: never lose the event — remembered, the error kept
                        d = {"action": "remember", "urgency": "later", "category": None, "needs_reply": None,
                             "confidence": None, "model": None, "error": f"{type(exc).__name__}: {exc}"[:200]}
                    action, rule = _apply_rules(r, ev, ctx, d, datetime.now(tz), sent_last_hour)
                rec = {"action": action, "rule": rule, "d": d,
                       "ctx": {k: ctx[k] for k in ("network", "thread_kind", "monsieur_mentioned",
                                                   "monsieur_answered_after", "monsieur_messages_30d",
                                                   "their_messages_30d", "attachments", "content_withheld")}}
            d = rec["d"]
            if not dry:
                conflict = ("""on conflict (event_id) do update set decided_at = now(), model_action = excluded.model_action,
                                   action = excluded.action, urgency = excluded.urgency, category = excluded.category,
                                   needs_reply = excluded.needs_reply, confidence = excluded.confidence,
                                   model = excluded.model, rule = excluded.rule,
                                   payload = excluded.payload || jsonb_build_object('previous', jsonb_build_object(
                                       'decided_at', triage.decisions.decided_at, 'action', triage.decisions.action,
                                       'error', triage.decisions.payload->>'error'))
                                where triage.decisions.payload->>'error' is not null
                                  and triage.decisions.delivered_at is null""" if replace_errors
                            else "on conflict (event_id) do nothing")
                conn.execute(f"""insert into triage.decisions (event_id, occurred_at, source, thread_id, model_action,
                                    action, urgency, category, needs_reply, confidence, model, rule, shadow, payload)
                                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) {conflict}""",
                             (ev["event_id"], ev["occurred_at"], ev["source"], ev["thread_id"], d.get("action"),
                              rec["action"], d.get("urgency"), d.get("category"), d.get("needs_reply"),
                              d.get("confidence"), d.get("model"), rec["rule"] or None, r["shadow"],
                              json.dumps({"context": rec.get("ctx"), "error": d.get("error"),
                                          **({"observations": {k: d[k] for k in ("deadline", "amount") if k in d}}
                                             if "deadline" in d or "amount" in d else {}),
                                          **({"unavailable": d["unavailable"]} if d.get("unavailable") else {})},
                                         default=str)))
            out["decided"] += 1
            out["by_action"][rec["action"]] = out["by_action"].get(rec["action"], 0) + 1
    return out


def redecide_errors(since: str | None = None, limit: int = 200, dry: bool = True) -> dict:
    """Re-decide events whose stored decision failed (payload.error, never delivered). Dry by default: reports the
    rows and what would be decided without writing. A new failure leaves the row as it was."""
    with connection() as conn:
        evs = list(conn.execute(f"""select {EVENT_COLUMNS} from triage.decisions d
                                   join core.events e on e.event_id = d.event_id and e.occurred_at = d.occurred_at
                                   where d.payload->>'error' is not null and d.delivered_at is null
                                     and (%s::timestamptz is null or d.decided_at >= %s::timestamptz)
                                   order by e.ingested_at limit %s""", (since, since, limit)))
        stored = conn.execute("""select count(*) n from triage.decisions where payload->>'error' is not null
                                 and delivered_at is null""").fetchone()["n"]
    if not evs:
        return {"stored_with_error": stored, "selected": 0}
    # a re-decision must not fall back to a final 'remember' again: past-window failures are skipped, not stored
    for ev in evs:
        ev["ingested_at"] = datetime.now(timezone.utc)
    res = _decide(evs, dry=dry, replace_errors=True)
    return {"stored_with_error": stored, "selected": len(evs), "dry": dry, **res}
