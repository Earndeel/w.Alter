"""A5 media derivation (2026-11-11): every Raw Vault object gets a derived text found from its message.
Model calls are mocked; objects are rows of the throwaway database (no S3: bytes come from a local fixture)."""
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

import pytest

from walter_memory import assimilation, events, media, objects, processing
from walter_memory.db import connection

RUN = uuid.uuid4().hex[:8]
OLD = datetime(1990, 1, 1, tzinfo=timezone.utc)      # before anything else in the test database: oldest-first picks ours


@pytest.fixture
def cfg(monkeypatch):
    s = {**media.DEFAULTS, "audio": "on", "document": "on", "image": "off", "video": "off", "est_usd_audio": 0.0003}
    monkeypatch.setattr(media, "settings", lambda: s)
    monkeypatch.setattr(media, "_estimate", lambda g: 0.0003 if g == "audio" else 0.0)
    return s


@pytest.fixture
def made():
    ids = []
    yield ids
    with connection() as conn:
        for i in ids:
            conn.execute("delete from search.chunks where kind = 'object' and ref_id = %s::uuid", (i,))
            conn.execute("delete from processing.queue where processor = %s and key = %s", (media.PROCESSOR, i))
            conn.execute("delete from core.objects where id = %s::uuid", (i,))


def _obj(made, kind="audio", mime="audio/ogg", name="voice.ogg", cls="cloud_allowed", size=1000, at=OLD):
    sha = hashlib.sha256(f"{RUN}{uuid.uuid4()}".encode()).hexdigest()
    with connection() as conn:
        oid = conn.execute("""insert into core.objects (sha256, size_bytes, mime, kind, storage_key, original_name,
                                  captured_at, source, privacy_class) values (%s,%s,%s,%s,%s,%s,%s,'beeper',%s)
                              returning id::text""", (sha, size, mime, kind, f"t/{sha}", name, at, cls)).fetchone()["id"]
    made.append(oid)
    return oid


def _fixture_file(tmp_path, monkeypatch, data=b"OggS fake audio", suffix=".ogg"):
    f = tmp_path / f"f{suffix}"
    f.write_bytes(data)
    monkeypatch.setattr(media, "_fetch", lambda oid, d: f)
    return f


class Chat:
    def __init__(self, answer="Bonjour, rendez-vous demain à 10 h", cost=0.0002, fail=None):
        self.answer, self.cost, self.fail, self.calls = answer, cost, fail, []

    def __call__(self, messages, **kw):
        self.calls.append((messages, kw))
        if self.fail:
            raise self.fail
        return {"content": self.answer, "cost_usd": self.cost, "model": "fake-stt", "provider": "fake"}


def _row(oid):
    with connection() as conn:
        return conn.execute("select * from core.objects where id = %s::uuid", (oid,)).fetchone()


def test_new_object_is_published_for_derivation_and_routed(made, cfg):
    oid = _obj(made)
    with connection() as conn:
        ev = conn.execute("""select payload from bus.events where type = 'memory.object' and subject = %s
                             order by id desc limit 1""", (oid,)).fetchone()
    assert ev and ev["payload"]["text"] is False and ev["payload"]["kind"] == "audio"
    assert assimilation.route([{"type": "memory.object", "subject": oid, "payload": ev["payload"]}]) == 1
    assert any(r["key"] == oid for r in processing.due(media.PROCESSOR, datetime(2100, 1, 1, tzinfo=timezone.utc)))
    cfg["audio"] = "off"     # a kind switched off is not queued
    other = _obj(made)
    assert media.route(None, other, {"kind": "audio", "text": False}) == 0


def test_derive_audio_through_stt_poste(made, cfg, tmp_path, monkeypatch):
    oid = _obj(made)
    _fixture_file(tmp_path, monkeypatch)
    chat = Chat()
    r = media.derive(oid, chat=chat)
    assert r["status"] == "derived" and r["derived_kind"] == "transcript" and r["called"] and r["cost_usd"] == 0.0002
    msgs, kw = chat.calls[0]
    assert kw["poste"] == "stt" and "model" not in kw and kw["processor"] == "media.stt"
    part = msgs[0]["content"][0]
    assert part["type"] == "input_audio" and part["input_audio"]["format"] == "ogg" and part["input_audio"]["data"]
    row = _row(oid)
    assert row["derived_text"].startswith("Bonjour") and row["derived_processor"] == "media/v1"
    assert row["derived_model"] == "fake-stt" and row["derived_at"] and row["status"] == "derived"
    with connection() as conn:   # the change is published: the search index follows
        ev = conn.execute("""select payload from bus.events where type = 'memory.object' and subject = %s
                             order by id desc limit 1""", (oid,)).fetchone()
    assert ev["payload"]["text"] is True
    assert media.derive(oid, chat=chat)["status"] == "done" and len(chat.calls) == 1   # idempotent


def test_empty_speech_is_final_not_retried(made, cfg, tmp_path, monkeypatch):
    oid = _obj(made)
    _fixture_file(tmp_path, monkeypatch)
    chat = Chat(answer="[silence]")
    r = media.derive(oid, chat=chat)
    assert r["status"] == "derived" and r["chars"] == 0 and r["reason"] == "no_speech"
    row = _row(oid)
    assert row["derived_text"] == "" and row["meta"]["media"]["reason"] == "no_speech"
    assert media.derive(oid, chat=chat)["status"] == "done" and len(chat.calls) == 1
    assert not objects.search(kind="audio", derived=False, limit=1000) or \
        oid not in [r["id"] for r in objects.search(kind="audio", derived=False, limit=1000)]


def test_failure_is_counted_and_retried_with_backoff_never_memoised(made, cfg, tmp_path, monkeypatch):
    oid = _obj(made)
    _fixture_file(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError):
        media.derive(oid, chat=Chat(fail=RuntimeError("HTTP 502")))
    assert _row(oid)["derived_at"] is None
    # the worker path: the key fails → backoff, error counted; a later attempt succeeds
    with connection() as conn:
        processing.mark(conn, media.PROCESSOR, oid, settle=0)
    row = next(r for r in processing.due(media.PROCESSOR) if r["key"] == oid)
    monkeypatch.setattr(media, "derive", lambda key, **kw: (_ for _ in ()).throw(RuntimeError("HTTP 502")))
    with pytest.raises(RuntimeError):
        assimilation._run_one(media.PROCESSOR, row)
    processing.failed(row, RuntimeError("HTTP 502"))
    with connection() as conn:
        q = conn.execute("select attempts, last_error, due_at > now() later from processing.queue where processor = %s"
                         " and key = %s", (media.PROCESSOR, oid)).fetchone()
    assert q["attempts"] == 1 and "502" in q["last_error"] and q["later"]
    assert _row(oid)["derived_at"] is None


def test_an_input_every_route_refuses_becomes_a_recorded_final_state(made, cfg, tmp_path, monkeypatch):
    """One unreadable voice note must not stay « failing » for ever (12/11: 1 of 1 425), nor be dropped silently."""
    oid = _obj(made)
    _fixture_file(tmp_path, monkeypatch)
    bad = RuntimeError("HTTP 502: {'message': 'every route failed', 'attempts': ['p/m: BadRequestError']}")
    with connection() as conn:
        processing.mark(conn, media.PROCESSOR, oid, settle=0)
    for n in range(media.REJECTED_AFTER - 1):                # refused, retried with backoff like any failure
        with pytest.raises(RuntimeError):
            media.derive(oid, chat=Chat(fail=bad))
        with connection() as conn:
            row = conn.execute("select processor, key, attempts, rev from processing.queue where processor = %s"
                               " and key = %s", (media.PROCESSOR, oid)).fetchone()
        processing.failed(row, bad)
    r = media.derive(oid, chat=Chat(fail=bad))               # the same refusal again: final, with its reason
    assert r["status"] == "derived" and r["chars"] == 0 and r["reason"] == "rejected_by_model"
    assert _row(oid)["meta"]["media"]["reason"] == "rejected_by_model"
    other = _obj(made, name="voice2.ogg")                    # an outage is never final, however often it repeats
    with connection() as conn:
        processing.mark(conn, media.PROCESSOR, other, settle=0)
        conn.execute("update processing.queue set attempts = 9 where processor = %s and key = %s", (media.PROCESSOR, other))
    with pytest.raises(RuntimeError):
        media.derive(other, chat=Chat(fail=RuntimeError("HTTP 502: every route failed ['p/m: APITimeoutError']")))
    assert _row(other)["derived_at"] is None


def test_backfill_failure_is_queued_and_skipped_during_backoff(made, cfg, tmp_path, monkeypatch):
    oid = _obj(made)
    _fixture_file(tmp_path, monkeypatch)
    r = media.backfill("audio", limit=1, apply=True, chat=Chat(fail=RuntimeError("timeout")))
    assert r["errors"] == 1 and r["spent_usd"] == 0
    with connection() as conn:
        q = conn.execute("select attempts from processing.queue where processor = %s and key = %s",
                         (media.PROCESSOR, oid)).fetchone()
        st = conn.execute("""select sum(errors) e from processing.stats where processor = %s
                             and hour >= date_trunc('hour', now())""", (media.PROCESSOR,)).fetchone()
    assert q["attempts"] == 1 and st["e"] >= 1 and _row(oid)["derived_at"] is None
    dry = media.backfill("audio", limit=500)
    assert dry["dry_run"]
    with connection() as conn:   # not a candidate while its backoff runs
        assert not conn.execute("""select 1 from core.objects o where o.id = %s::uuid and not exists (select 1 from
                                   processing.queue q where q.processor = %s and q.key = o.id::text and q.attempts > 0
                                   and q.due_at > now())""", (oid, media.PROCESSOR)).fetchone()
    s = media.status()
    audio = next(k for k in s["kinds"] if k["kind"] == "audio")
    assert audio["failing"] >= 1 and audio["pending"] >= 1


def test_backfill_dry_run_then_budget_stop(made, cfg, tmp_path, monkeypatch):
    ids = [_obj(made, at=datetime(1980, 1, 1 + i, tzinfo=timezone.utc)) for i in range(3)]
    _fixture_file(tmp_path, monkeypatch)
    chat = Chat(cost=0.0003)
    dry = media.backfill("audio", limit=3, chat=chat)
    assert dry["dry_run"] and dry["candidates"] == 3 and dry["est_usd"] == pytest.approx(0.0009) and not chat.calls
    r = media.backfill("audio", limit=3, max_usd=0.0005, apply=True, chat=chat)
    assert r["stopped"] == "budget" and r["results"] == {"derived": 1} and len(chat.calls) == 1
    assert _row(ids[0])["derived_at"] and _row(ids[1])["derived_at"] is None      # oldest first
    r2 = media.backfill("audio", limit=3, apply=True, chat=chat)                   # resumable
    assert r2["results"] == {"derived": 2} and all(_row(i)["derived_at"] for i in ids)


def test_privacy_refusal_sends_nothing(made, cfg, tmp_path, monkeypatch):
    _fixture_file(tmp_path, monkeypatch)
    chat = Chat()
    local = _obj(made, cls="local_only")
    red = _obj(made, cls="redacted_cloud")          # strict test policy: pseudonymisation on, bytes cannot be
    for oid in (local, red):
        r = media.derive(oid, chat=chat)
        assert r["status"] == "refused" and _row(oid)["derived_at"] is None
    assert not chat.calls


@pytest.mark.owner_privacy
def test_owner_policy_lets_redacted_audio_reach_stt(made, cfg, tmp_path, monkeypatch):
    _fixture_file(tmp_path, monkeypatch)
    oid = _obj(made, cls="redacted_cloud")
    assert media.derive(oid, chat=Chat())["status"] == "derived"


def _docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
                                        f'<w:p><w:r><w:t>second &amp; line</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def _pdf(text):
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    objs[3] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return out.encode()


def test_document_extraction_is_local(tmp_path):
    for data, mime, name, want in ((b"plain note " + RUN.encode(), "text/plain", "a.txt", "plain note"),
                                   (_docx("Contrat de location"), media.DOCX, "c.docx", "Contrat de location"),
                                   (b"<html><style>x{}</style><p>Facture &eacute;t&eacute;</p></html>", "text/html",
                                    "f.html", "Facture été"),
                                   (_pdf("Releve mensuel"), "application/pdf", "r.pdf", "Releve mensuel")):
        f = tmp_path / name
        f.write_bytes(data)
        text, how = media.extract_document(f, mime, name, 20000)
        assert want in text, (name, how)
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01")
    assert media.extract_document(f, "application/octet-stream", "x.bin", 100) == (None, "unsupported")


def test_derive_document_and_unsupported(made, cfg, tmp_path, monkeypatch):
    doc = _obj(made, kind="document", mime="text/plain", name="n.txt", cls="local_only")   # local: any class
    _fixture_file(tmp_path, monkeypatch, data=b"Liste de courses: pain", suffix=".txt")
    r = media.derive(doc, chat=Chat(fail=AssertionError("no model for documents")))
    assert r["status"] == "derived" and _row(doc)["derived_kind"] == "extract" and "pain" in _row(doc)["derived_text"]
    z = _obj(made, kind="document", mime="application/zstd", name="x.zst")
    r = media.derive(z)
    assert r["status"] == "derived" and r["reason"] == "unsupported_format" and _row(z)["derived_text"] == ""
    big = _obj(made, size=30 * 1024 * 1024)
    assert media.derive(big)["reason"] == "too_large"
    img = _obj(made, kind="image", mime="image/jpeg", name="p.jpg")
    assert media.derive(img)["status"] == "disabled" and _row(img)["derived_at"] is None


def test_a_document_the_local_extractor_cannot_read_is_final(made, cfg, tmp_path, monkeypatch):
    """12/11: four damaged PDFs stayed « failing » and were retried for ever; a local tool never changes its mind."""
    oid = _obj(made, kind="document", mime="application/pdf", name="abime.pdf")
    _fixture_file(tmp_path, monkeypatch, data=b"%PDF-1.4 not a real pdf", suffix=".pdf")
    r = media.derive(oid)
    assert r["status"] == "derived" and r["chars"] == 0 and r["reason"] == "unreadable"
    assert _row(oid)["meta"]["media"]["reason"] == "unreadable" and media.derive(oid)["status"] == "done"
    bad = _obj(made, kind="document", name="abime.docx",
               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    _fixture_file(tmp_path, monkeypatch, data=b"not a zip", suffix=".docx")
    assert media.derive(bad)["reason"] == "unreadable"


def test_attachments_in_compact_detail_render_and_search(made, cfg, tmp_path, monkeypatch):
    thread = f"chat-{RUN}"
    sid = f"{thread}|m1"
    got = events.record_events([{"event_type": "message.received", "source": "beeper", "source_id": sid,
                                 "thread_id": thread, "occurred_at": "2026-11-10T10:00:00Z", "content": None, "privacy_class": "cloud_allowed",
                                 "actor": {"external_id": f"p-{RUN}", "display_name": "Fixture"}},
                                {"event_type": "message.received", "source": "beeper", "source_id": f"{thread}|m2",
                                 "thread_id": thread, "occurred_at": "2026-11-10T10:01:00Z", "content": "ok", "privacy_class": "cloud_allowed",
                                 "actor": {"external_id": f"p-{RUN}"}}])
    eid = got["event_ids"][0]
    oid = _obj(made)
    hidden = _obj(made, kind="document", mime="application/pdf", name="secret.pdf", cls="local_only")
    with connection() as conn:
        for o in (oid, hidden):
            conn.execute("insert into core.object_links (object_id, target_type, target_id) values (%s, 'beeper_message', %s)",
                         (o, sid))
    objects.set_derived(oid, "Je serai là à midi", "transcript", model="fake", processor="media/v1")
    detail = events.get_events(event_id=eid, max_privacy="cloud_allowed")[0]
    atts = {a["object_id"]: a for a in detail["attachments"]}
    assert atts[oid]["text"] == "Je serai là à midi" and atts[oid]["derived_kind"] == "transcript"
    assert atts[hidden] == {"object_id": hidden, "kind": "document", "withheld": "privacy"}   # strict test policy
    rows = events.get_events(thread_id=thread, order="asc")
    out = events.compact(rows)
    first = out["events"][0]
    assert first["source_id"] == sid and oid in [a["object_id"] for a in first["attachments"]] and "attachments" not in out["events"][1]
    lines = events.render_messages(rows)
    assert f'[audio · object {oid} · transcript: "Je serai là à midi"]' in lines[0] and lines[1] == "ok"
    assert events.attachment_line({"object_id": "x", "kind": "audio", "text": None}) == "[audio · object x · no text yet]"
    # objects.search: the voice notes of one conversation, of one message
    by_thread = objects.search(kind="audio", thread_id=thread)
    assert [r["id"] for r in by_thread] == [oid] and by_thread[0]["derived_text"].startswith("Je serai")
    assert [r["id"] for r in objects.search(event_id=eid, kind="audio")] == [oid]
    assert objects.search(kind="audio", thread_id=f"other-{RUN}") == []
    assert hidden not in [r["id"] for r in objects.search(thread_id=thread, max_privacy="cloud_allowed")]
    assert hidden in [r["id"] for r in objects.search(thread_id=thread)]
    assert [r["id"] for r in objects.search("midi", thread_id=thread)] == [oid]


def test_object_refs_on_new_events_are_resolved(made, cfg):
    oid = _obj(made)
    got = events.record_events([{"event_type": "note.recorded", "source": "claude", "source_id": f"n-{RUN}",
                                 "occurred_at": "2026-11-10T10:00:00Z", "content": "see file", "object_refs": [oid]}])
    rows = events.get_events(event_id=got["event_ids"][0])
    assert rows[0]["attachments"][0]["object_id"] == oid
    assert [r["id"] for r in objects.search(event_id=got["event_ids"][0])] == [oid]


def test_beeper_connector_refs_known_objects(made):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("beeper_conn", Path(__file__).resolve().parents[1] / "connectors" / "beeper.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    oid = _obj(made)
    sid = f"c-{RUN}|m9"
    with connection() as conn:
        conn.execute("insert into core.object_links (object_id, target_type, target_id) values (%s, 'beeper_message', %s)",
                     (oid, sid))
        evs = [{"event_type": "message.edited", "source_id": f"{sid}|edit|1", "payload": {"target_source_id": sid}},
               {"event_type": "message.received", "source_id": f"c-{RUN}|new", "payload": {}}]
        assert mod.attach_known_objects(conn, evs) == 1
    assert evs[0]["object_refs"] == [oid] and "object_refs" not in evs[1]


def test_cli_media_status_and_search(made, cfg, capsys):
    from walter_memory import cli
    _obj(made)
    with pytest.raises(SystemExit) as e:
        cli.main(["media", "status"])
    assert e.value.code == 0
    s = json.loads(capsys.readouterr().out)
    assert {"kinds", "queued", "switches"} <= set(s) and any(k["kind"] == "audio" for k in s["kinds"])
    with pytest.raises(SystemExit):
        cli.main(["media", "search", "--kind", "audio", "--thread", f"none-{RUN}", "--cloud-safe", "--", "x"])
    assert json.loads(capsys.readouterr().out) == []
