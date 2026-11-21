"""Media derivation (SOCLE A5, 2026-11-11): every Raw Vault object gets a derived text found from its message.

  core.objects insert ──trigger objects_publish (036)──▶ bus memory.object {text: false}
        └─▶ consumer memory.organic (assimilation.route) ──▶ processing.queue 'media.derive' / object id
              └─▶ work() → derive(object id) ──▶ objects.set_derived (core.objects.derived_*)
                    └─▶ trigger: memory.object {text: true} ──▶ search.index (search.chunks, kind 'object')

  audio     → transcript   Walter Router poste `stt` through the walter-llm gateway (llm.chat, input_audio part)
  document  → extract      local extraction, no model: pdftotext, plain text / markdown / html / calendar / vcard,
                           docx / odt (zip + XML); bounded to [media] max_text_chars
  image     → ocr|caption  Walter Router poste `vision` (OFF by default: the owner fixes the catch-up budget first)
  video     → —            off (out of scope, SOCLE § 3)

Read side: the text appears with its message at read time (events.attachments / compact / get_events(event_id) /
render_messages) and objects.search(thread_id=, event_id=) — through core.object_links, so history is covered.

Idempotence and failures: an object with derived_at is done (force=True re-derives). An empty result (no speech,
no text layer, unsupported format, too large) is recorded as derived with empty text and `meta.media` saying why, so
it is never retried by itself. A FAILURE (download, gateway, model) is never recorded on the object: the key stays in
processing.queue with attempts / last_error and is retried with backoff (processing.failed), and it is counted as an
error in processing.stats (`walter-memory assimilation status`, `walter-memory media status`). The memo of a model
outcome is the object row itself: its bytes are unique (sha256), so derived_at keyed on them is the decision keyed by
its exact input, negative ones included; no copy of a transcript is kept elsewhere (a purge of the object removes it).
Privacy: model calls go through llm.chat (its privacy, budget and ledger guards); local_only objects reach a model
only when the owner's cloud ceiling allows it; redacted_cloud media are refused while pseudonymisation is on (bytes
cannot be pseudonymised). Local extraction applies to every class.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import logging
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from functools import lru_cache
from pathlib import Path

from . import privacy, processing
from .db import connection

log = logging.getLogger("walter.media")
PROCESSOR = "media.derive"            # processing.queue / stats key
VERSION = "media/v1"                  # core.objects.derived_processor
STT_POSTE, VISION_POSTE = "stt", "vision"
DEFAULTS = {"audio": "on", "document": "on", "image": "off", "video": "off", "max_audio_mb": 25,
            "max_document_mb": 50, "max_image_mb": 15, "max_text_chars": 20000, "per_run": 200,
            "est_usd_audio": 0.0003, "est_usd_image": 0.002}
GROUP = {"audio": "audio", "document": "document", "image": "image", "screenshot": "image", "video": "video"}
DERIVED_KIND = {"audio": "transcript", "document": "extract", "image": "ocr", "video": "caption"}
MODEL_GROUPS = ("audio", "image", "video")
REJECTED_AFTER = 4                    # every route refused the input itself this many times in a row → a final state
# STT request shape of the Router's `stt` poste (serve/oneshot.transcribe): input_audio part + this instruction
STT_PROMPT = ("Transcris exactement cette note vocale, dans sa langue, sans rien ajouter ni résumer. "
              "S'il n'y a aucune parole, réponds seulement [silence].")
AUDIO_FORMATS = {".oga": "ogg", ".ogg": "ogg", ".opus": "ogg", ".mp3": "mp3", ".m4a": "m4a", ".wav": "wav",
                 ".mp4": "mp4", ".webm": "webm", ".flac": "flac", ".aac": "aac"}
AUDIO_MIME = {"audio/ogg": "ogg", "audio/opus": "ogg", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/x-wav": "wav",
              "audio/wav": "wav", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac", "audio/webm": "webm",
              "audio/flac": "flac"}
VISION_PROMPT = ("Lis cette image pour la mémoire de son propriétaire. Réponds exactement en deux lignes :\n"
                 "TEXTE: <tout le texte lisible, tel quel, sur une ligne ; vide s'il n'y en a pas>\n"
                 "LÉGENDE: <une phrase factuelle sur ce que montre l'image>")
TEXT_MIME = ("text/", "application/json", "application/xml", "application/x-yaml")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ODT = "application/vnd.oasis.opendocument.text"


class Unreadable(Exception):
    """A local, deterministic extractor cannot read these bytes (damaged or protected file): a final state recorded
    on the object (reason `unreadable`), never a retry."""


class Refused(Exception):
    """Policy refusal (privacy, switch off): not a failure — nothing written, nothing retried."""


# ───────────────────────────── settings ─────────────────────────────
@lru_cache(maxsize=1)
def settings() -> dict:
    """organic.toml [media] (instance override first, like organic.settings), safe defaults."""
    path = None
    try:
        path = subprocess.run(["walter", "instance", "config", "memory", "organic.toml"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "config" / "organic.toml"
    try:
        data = tomllib.loads(p.read_text()).get("media") or {}
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    return {**DEFAULTS, **data}


def group(kind: str | None) -> str | None:
    return GROUP.get(kind or "")


def enabled(kind: str | None) -> bool:
    g = group(kind)
    return bool(g) and str(settings().get(g, "off")).lower() in ("on", "true", "1")


def _max_bytes(g: str) -> int:
    return int(float(settings().get(f"max_{g}_mb", 25)) * 1024 * 1024)


# ───────────────────────────── bus routing (assimilation) ─────────────────────────────
def route(conn, object_id: str, payload: dict) -> int:
    """A new object (memory.object, text = false) → its derivation key, when its kind is switched on."""
    if not object_id or not enabled(payload.get("kind")):
        return 0
    processing.mark(conn, PROCESSOR, str(object_id), reason=payload.get("kind") or "object", settle=5, max_wait=60)
    return 1


def run_key(key: str) -> dict:
    """Assimilation worker entry: raises on failure (the queue retries with backoff and counts the error)."""
    r = derive(key)
    return {"changed": 1 if r.get("status") == "derived" else 0}


# ───────────────────────────── extraction ─────────────────────────────
def _audio_format(row: dict) -> str | None:
    suffix = Path(row.get("original_name") or "").suffix.lower()
    return AUDIO_FORMATS.get(suffix) or AUDIO_MIME.get((row.get("mime") or "").split(";")[0].strip())


def _strip_xml(xml: str, para: str) -> str:
    xml = re.sub(para, "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(xml)


def extract_document(path: Path, mime: str | None, name: str | None, max_chars: int) -> tuple[str | None, str]:
    """(text, how) for a document, locally; text None = unsupported format. Never calls a model."""
    m = (mime or "").split(";")[0].strip().lower()
    suffix = Path(name or path.name).suffix.lower()
    if m == "application/pdf" or suffix == ".pdf":
        r = subprocess.run(["pdftotext", "-q", "-l", "200", "-enc", "UTF-8", str(path), "-"], capture_output=True,
                           timeout=120)
        if r.returncode != 0 and not r.stdout:      # same bytes, same local tool: it will never read them
            raise Unreadable(f"pdftotext exit {r.returncode}")
        return r.stdout.decode("utf-8", "replace")[:max_chars], "pdftotext"
    if m == DOCX or suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            return _strip_xml(z.read("word/document.xml").decode("utf-8", "replace"), r"</w:p>")[:max_chars], "docx"
    if m == ODT or suffix == ".odt":
        with zipfile.ZipFile(path) as z:
            return _strip_xml(z.read("content.xml").decode("utf-8", "replace"), r"</text:(?:p|h)>")[:max_chars], "odt"
    if m.startswith(TEXT_MIME) or suffix in (".txt", ".md", ".csv", ".ics", ".vcf", ".json", ".html", ".htm", ".xml"):
        with path.open("rb") as f:
            raw = f.read(max_chars * 4).decode("utf-8", "replace")
        if m == "text/html" or suffix in (".html", ".htm"):
            raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", raw)
            raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            raw = re.sub(r"[ \t]+", " ", raw)
            return raw.strip()[:max_chars], "html"
        return raw[:max_chars], "text"
    return None, "unsupported"


def _fetch(object_id: str, dest_dir: str) -> Path:
    """The object's bytes through the objects API (integrity-checked). Memory's own processor reads every class; the
    model door (llm.chat) decides what may leave."""
    from . import objects
    return objects.get_object(object_id, dest_dir=dest_dir, max_privacy="local_only")


def _model_privacy(cls: str) -> None:
    if not privacy.model_may_receive(cls):
        raise Refused(f"{cls} media cannot reach a cloud model under the current policy")
    if cls == "redacted_cloud" and privacy.pseudonymise():
        raise Refused("redacted_cloud media cannot be pseudonymised before a cloud model")


def _transcribe(row: dict, path: Path, fmt: str, *, budget: str, chat) -> dict:
    content = [{"type": "input_audio", "input_audio": {"data": base64.b64encode(path.read_bytes()).decode("ascii"),
                                                         "format": fmt}},
               {"type": "text", "text": STT_PROMPT}]
    res = chat([{"role": "user", "content": content}], poste=STT_POSTE, processor="media.stt",
               processor_version=VERSION, privacy_class=row["privacy_class"], budget=budget,
               purpose=f"object {row['id']}", max_tokens=4000, timeout=180)
    text = (res.get("content") or "").strip()
    if text.strip("[]. ").lower() == "silence":
        text = ""
    return {"text": text, "model": res.get("model"), "provider": res.get("provider"), "cost_usd": res.get("cost_usd")}


def _vision(row: dict, path: Path, *, budget: str, chat) -> dict:
    mime = row.get("mime") or "image/jpeg"
    url = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    res = chat([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}},
                                             {"type": "text", "text": VISION_PROMPT}]}],
               poste=VISION_POSTE, processor="media.vision", processor_version=VERSION,
               privacy_class=row["privacy_class"], budget=budget, purpose=f"object {row['id']}", max_tokens=1500,
               timeout=180)
    out = res.get("content") or ""
    ocr = re.search(r"(?im)^\s*TEXTE\s*:\s*(.*)$", out)
    cap = re.search(r"(?im)^\s*L[ÉE]GENDE\s*:\s*(.*)$", out)
    ocr_t, cap_t = (ocr.group(1).strip() if ocr else ""), (cap.group(1).strip() if cap else out.strip())
    ocr_t = "" if ocr_t.strip("<>[]. ").lower() in ("", "vide", "aucun", "none") else ocr_t
    text = (ocr_t + ("\n" if ocr_t and cap_t else "") + cap_t).strip()
    return {"text": text, "kind": "ocr" if ocr_t else "caption", "model": res.get("model"),
            "provider": res.get("provider"), "cost_usd": res.get("cost_usd")}


def _rejected(err: Exception, object_id: str) -> bool:
    """The model door refused the INPUT (every route answered a bad-request error: unreadable or unsupported bytes),
    and it already did REJECTED_AFTER - 1 times: not an outage, so not retried for ever. Recorded on the object
    (reason `rejected_by_model`, counted as empty by `media status`); `media derive --force` tries again."""
    text = f"{type(err).__name__}: {err}"
    if "BadRequestError" not in text or re.search(r"Timeout|RateLimit|Connection|InternalServer|Unavailable", text):
        return False
    with connection() as conn:
        r = conn.execute("select attempts from processing.queue where processor = %s and key = %s",
                         (PROCESSOR, str(object_id))).fetchone()
    return bool(r and r["attempts"] >= REJECTED_AFTER - 1)


# ───────────────────────────── derive ─────────────────────────────
def derive(object_id: str, *, force: bool = False, budget: str = "recurring", chat=None) -> dict:
    """Derive one object's text. Returns {object_id, status, ...}: status 'derived' (written, possibly empty with a
    note), 'done' (already derived), 'disabled' (switch off), 'refused' (privacy), 'missing'. Raises on failure
    (never recorded as final: the caller retries)."""
    from . import objects
    if chat is None:
        from . import llm
        chat = llm.chat
    with connection() as conn:
        row = conn.execute("""select id::text as id, sha256, kind, mime, original_name, size_bytes, privacy_class,
                                     derived_at, derived_text, meta
                              from core.objects where id::text = %s and purged_at is null""",
                           (str(object_id),)).fetchone()
    if row is None:
        return {"object_id": str(object_id), "status": "missing"}
    out = {"object_id": row["id"], "kind": row["kind"]}
    if row["derived_at"] is not None and not force:
        return {**out, "status": "done"}
    g = group(row["kind"])
    if not g or not enabled(row["kind"]):
        return {**out, "status": "disabled"}
    dkind = DERIVED_KIND[g]
    if g == "video":
        return {**out, "status": "disabled", "note": "video derivation is not implemented (SOCLE A5 scope)"}

    def write(text: str, kind: str, model: str | None, note: dict) -> dict:
        with connection() as conn:
            if force and row["derived_text"] is not None:      # the index follows the new text
                conn.execute("delete from search.chunks where kind = 'object' and ref_id = %s::uuid", (row["id"],))
            r = objects.set_derived(row["id"], text, kind, model=model, processor=VERSION, meta=note, conn=conn)
        return {**out, "status": "derived", "derived_kind": kind, "chars": r["chars"], "model": model,
                **{k: v for k, v in note.items() if k in ("result", "reason")}}

    if (row["size_bytes"] or 0) > _max_bytes(g):
        return write("", dkind, None, {"result": "skipped", "reason": "too_large"})
    if g == "audio" and _audio_format(row) is None:
        return write("", dkind, None, {"result": "skipped", "reason": "unsupported_format"})
    if g in MODEL_GROUPS:
        try:
            _model_privacy(row["privacy_class"])
        except Refused as e:
            return {**out, "status": "refused", "reason": str(e)}
    with tempfile.TemporaryDirectory(prefix="walter-media-", dir="/var/tmp") as d:
        path = _fetch(row["id"], d)
        if g == "document":
            try:
                text, how = extract_document(path, row["mime"], row["original_name"],
                                             int(settings().get("max_text_chars", 20000)))
            except (Unreadable, zipfile.BadZipFile, KeyError):
                return write("", dkind, None, {"result": "skipped", "reason": "unreadable"})
            if text is None:
                return write("", dkind, None, {"result": "skipped", "reason": "unsupported_format"})
            text = text.strip()
            return write(text, dkind, how, {"result": "text" if text else "empty",
                                            **({} if text else {"reason": "no_text_layer"})})
        if g == "audio":
            fmt = _audio_format(row)
            try:
                res = _transcribe(row, path, fmt, budget=budget, chat=chat)
            except Exception as e:  # noqa: BLE001 - only a repeated refusal of the input is final, the rest is retried
                if not _rejected(e, row["id"]):
                    raise
                return write("", "transcript", None, {"result": "skipped", "reason": "rejected_by_model"})
            processing.count(PROCESSOR, calls=1)
            note = {"result": "transcript" if res["text"] else "empty", "provider": res.get("provider"),
                    **({} if res["text"] else {"reason": "no_speech"})}
            r = write(res["text"], "transcript", res.get("model"), note)
            return {**r, "cost_usd": res.get("cost_usd"), "called": True}
        try:
            res = _vision(row, path, budget=budget, chat=chat)
        except Exception as e:  # noqa: BLE001 - same rule as audio
            if not _rejected(e, row["id"]):
                raise
            return write("", dkind, None, {"result": "skipped", "reason": "rejected_by_model"})
        processing.count(PROCESSOR, calls=1)
        note = {"result": res.get("kind") if res["text"] else "empty", "provider": res.get("provider"),
                **({} if res["text"] else {"reason": "no_content"})}
        r = write(res["text"], res.get("kind") or "caption", res.get("model"), note)
        return {**r, "cost_usd": res.get("cost_usd"), "called": True}


def record_failure(object_id: str, err: Exception) -> None:
    """A failure outside the worker (CLI, backfill): the key enters the queue with backoff and counts as an error."""
    with connection() as conn:
        processing.mark(conn, PROCESSOR, str(object_id), reason="retry", settle=0)
        row = conn.execute("""select processor, key, attempts, rev from processing.queue
                              where processor = %s and key = %s""", (PROCESSOR, str(object_id))).fetchone()
    processing.failed(row, err)
    processing.count(PROCESSOR, keys=1, errors=1)


# ───────────────────────────── status and catch-up ─────────────────────────────
def status() -> dict:
    """Counts only (no names, no texts): per object kind derived / empty / pending / failing, the switches, and the
    processor's last-24 h counters."""
    with connection() as conn:
        kinds = conn.execute("""select kind, count(*) as total, count(derived_at) as derived,
                                       count(*) filter (where derived_at is not null and derived_text = '') as empty,
                                       count(*) filter (where derived_at is null) as pending
                                from core.objects where purged_at is null group by 1 order by 1""").fetchall()
        failing = {r["kind"]: r for r in conn.execute(
            """select o.kind, count(*) as failing, max(q.attempts) as max_attempts
               from processing.queue q join core.objects o on o.id::text = q.key
               where q.processor = %s and q.attempts > 0 group by 1""", (PROCESSOR,)).fetchall()}
        queued = conn.execute("select count(*) n from processing.queue where processor = %s", (PROCESSOR,)).fetchone()["n"]
        stats = conn.execute("""select processor, sum(keys) keys, sum(changed) changed, sum(calls) calls, sum(hits) hits,
                                       sum(errors) errors
                                from processing.stats where hour >= now() - interval '24 hours'
                                  and processor in (%s, 'media.stt', 'media.vision') group by 1""",
                             (PROCESSOR,)).fetchall()
        calls = conn.execute("""select processor, status, count(*) n, round(sum(coalesce(cost_usd, 0))::numeric, 4) usd
                                from system.model_calls where processor in ('media.stt', 'media.vision')
                                  and at >= now() - interval '24 hours' group by 1, 2 order by 1, 2""").fetchall()
    s = settings()
    for k in kinds:
        f = failing.get(k["kind"]) or {}
        k["failing"] = int(f.get("failing") or 0)
        k["switch"] = s.get(group(k["kind"]) or "", "n/a") if group(k["kind"]) else "n/a"
    return {"kinds": kinds, "queued": queued, "last_24h": stats, "model_calls_24h": calls,
            "switches": {g: s.get(g) for g in ("audio", "document", "image", "video")}}


def _estimate(g: str) -> float:
    if g not in MODEL_GROUPS:
        return 0.0
    proc = "media.stt" if g == "audio" else "media.vision"
    try:
        with connection() as conn:
            r = conn.execute("""select avg(cost_usd) c from (select cost_usd from system.model_calls
                                where processor = %s and status = 'ok' and cost_usd is not null
                                order by at desc limit 50) x""", (proc,)).fetchone()
        if r and r["c"]:
            return float(r["c"])
    except Exception:  # noqa: BLE001
        pass
    return float(settings().get(f"est_usd_{g}", 0.0003))


def backfill(kind: str = "audio", *, limit: int | None = None, max_usd: float | None = None, apply: bool = False,
             newest_first: bool = False, chat=None) -> dict:
    """Catch up the objects of one kind group without a derived text (dry run by default). Oldest first unless
    newest_first; stops before the budget max_usd would be passed; idempotent and resumable (a derived object is
    skipped; a failing one waits for its backoff). Model calls are booked on the 'backfill' budget."""
    if kind not in ("audio", "document", "image", "video"):
        raise ValueError("kind must be audio, document, image or video")
    kinds = [k for k, g in GROUP.items() if g == kind]
    n = int(limit or settings().get("per_run", 200))
    with connection() as conn:
        rows = conn.execute(
            f"""select o.id::text as id, o.size_bytes, o.privacy_class from core.objects o
                where o.kind = any(%s) and o.derived_at is null and o.purged_at is null
                  and not exists (select 1 from processing.queue q where q.processor = %s and q.key = o.id::text
                                  and q.attempts > 0 and q.due_at > now())
                order by o.captured_at {'desc' if newest_first else 'asc'} nulls last, o.id limit %s""",
            (kinds, PROCESSOR, n)).fetchall()
    est = _estimate(kind)
    refused = 0
    if kind in MODEL_GROUPS:
        for r in rows:
            try:
                _model_privacy(r["privacy_class"])
            except Refused:
                refused += 1
    plan = {"kind": kind, "switch": settings().get(kind), "candidates": len(rows), "refused_privacy": refused,
            "est_usd_per_object": round(est, 6), "est_usd": round(est * (len(rows) - refused), 4),
            "order": "newest_first" if newest_first else "oldest_first", "max_usd": max_usd}
    if not apply:
        return {"dry_run": True, **plan}
    if not enabled(kinds[0]):
        return {"dry_run": False, **plan, "stopped": f"[media] {kind} is off"}
    spent, done, errors, consecutive, stopped = 0.0, {}, 0, 0, None
    for r in rows:
        if max_usd is not None and spent + est > max_usd:
            stopped = "budget"
            break
        try:
            res = derive(r["id"], budget="backfill", chat=chat)
        except Exception as e:  # noqa: BLE001 — counted, retried with backoff, never recorded as final
            log.warning("media backfill: %s failed: %s", r["id"], type(e).__name__)
            record_failure(r["id"], e)
            errors += 1
            consecutive += 1
            if consecutive >= 5:
                stopped = "errors"
                break
            continue
        consecutive = 0
        st = res.get("status")
        done[st] = done.get(st, 0) + 1
        if res.get("called"):
            spent += float(res.get("cost_usd") if res.get("cost_usd") is not None else est)
        if st == "derived":
            processing.count(PROCESSOR, keys=1, changed=1)
    return {"dry_run": False, **plan, "results": done, "errors": errors, "spent_usd": round(spent, 6),
            "stopped": stopped}


# ───────────────────────────── CLI (walter-memory media …) ─────────────────────────────
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="walter-memory media", description="Raw Vault media derivation (A5)")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("status", help="counts by kind: derived / empty / pending / failing (aggregates only)")
    d = sub.add_parser("derive", help="derive one object now")
    d.add_argument("object_id"); d.add_argument("--force", action="store_true")
    b = sub.add_parser("backfill", help="catch up one kind (dry run unless --apply)")
    b.add_argument("--kind", default="audio", choices=["audio", "document", "image", "video"])
    b.add_argument("--limit", type=int); b.add_argument("--max-usd", type=float)
    b.add_argument("--apply", action="store_true"); b.add_argument("--newest-first", action="store_true")
    s = sub.add_parser("search", help="objects by words / kind / conversation / message (MCP vault_search)")
    s.add_argument("text", nargs="?", default=""); s.add_argument("--kind"); s.add_argument("--source")
    s.add_argument("--thread"); s.add_argument("--event"); s.add_argument("--since"); s.add_argument("--until")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--cloud-safe", action="store_true", help="what a cloud reader may see (Memory's privacy policy)")
    a = p.parse_args(argv)
    if a.action == "status":
        r = status()
    elif a.action == "derive":
        try:
            r = derive(a.object_id, force=a.force)
        except Exception as e:
            record_failure(a.object_id, e)
            r = {"object_id": a.object_id, "status": "failed", "error": type(e).__name__, "retry": "queued with backoff"}
    elif a.action == "backfill":
        r = backfill(a.kind, limit=a.limit, max_usd=a.max_usd, apply=a.apply, newest_first=a.newest_first)
    else:
        from . import objects
        r = objects.search(a.text, kind=a.kind, source=a.source, limit=max(1, min(a.limit, 100)),
                           max_privacy="cloud_allowed" if a.cloud_safe else "local_only", thread_id=a.thread,
                           event_id=a.event, since=a.since, until=a.until)
    print(json.dumps(r, default=str, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
