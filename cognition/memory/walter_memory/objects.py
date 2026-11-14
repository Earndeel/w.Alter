"""Raw Vault object registry (A5: core.objects is the single registry).

Bytes: S3 API of `raw-vault-s3` (rclone over Google Drive). Bucket `raw` = clear (browsable in Drive),
bucket `secure` = rclone crypt (local_only objects, P1.5). The original is stored before any analysis.
Layout: <source>/<YYYY>/<MM>/<YYYYMMDD-HHMMSS>_<sha8>_<original-name>
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

from . import privacy
from .db import connection

BUCKETS = {"clear": "raw", "secure": "secure"}
_ENV_PARTS = ("bootstrap", "raw-vault", "s3.env")   # @instance/… (0600), no ~/.hermes path since 2026-11-11
_s3 = None


def _env() -> dict:
    from .purge import _instance
    env = {}
    env_file = _instance(*_ENV_PARTS)
    if env_file is not None and env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith("RAW_VAULT_")}}


def s3(config=None):
    global _s3
    if _s3 is None or config is not None:
        e = _env()
        client = boto3.client("s3", endpoint_url=e.get("RAW_VAULT_S3_ENDPOINT", "http://127.0.0.1:8899"),
                           aws_access_key_id=e["RAW_VAULT_S3_ACCESS_KEY"], aws_secret_access_key=e["RAW_VAULT_S3_SECRET_KEY"],
                           region_name="«secret:vault»",
                           config=config or Config(s3={"addressing_style": "path"}, signature_version="s3v4",
                                         retries={"max_attempts": 5, "mode": "standard"}))
        if config is not None:
            return client
        _s3 = client
    return _s3


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


SCREENSHOT_RE = re.compile(r"(screenshot|capture d.?[ée]cran|screen ?shot|scr_)", re.I)


def kind_of(mime: str | None, name: str) -> str:
    m = mime or ""
    if m.startswith("image/"):
        return "screenshot" if SCREENSHOT_RE.search(name) else "image"
    for prefix, kind in (("video/", "video"), ("audio/", "audio")):
        if m.startswith(prefix):
            return kind
    if m in ("application/zip", "application/x-tar", "application/gzip", "application/x-7z-compressed"):
        return "archive"
    return "document" if m.startswith(("text/", "application/")) else "other"


def _image_meta(path: Path) -> tuple[dict, datetime | None]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            meta = {"width": im.width, "height": im.height}
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)
            when = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc) if raw else None
            return meta, when
    except Exception:
        return {}, None


def safe_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).strip().replace("/", "_")
    return re.sub(r"[\x00-\x1f\\:*?\"<>|]+", "_", name)[-120:] or "file"


def put_object(path: str | Path, source: str, *, source_ref: dict | None = None, captured_at: datetime | None = None,
               links: list[tuple[str, str]] | None = None, original_name: str | None = None,
               privacy_class: str | None = None, zone: str | None = None, conn=None, storage_client=None) -> dict:
    """Store a file once (dedupe by sha256) in the right zone, register it, attach links. Returns the row."""
    if conn is None:
        with connection() as c:
            return put_object(path, source, source_ref=source_ref, captured_at=captured_at, links=links,
                              original_name=original_name, privacy_class=privacy_class, zone=zone, conn=c, storage_client=storage_client)
    path = Path(path)
    sha = sha256_file(path)
    name = original_name or path.name
    row = conn.execute("select * from core.objects where sha256 = %s", (sha,)).fetchone()
    if row is None:
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        kind = kind_of(mime, name)
        meta, exif_when = _image_meta(path) if mime.startswith("image/") else ({}, None)
        when = captured_at or exif_when
        if when is None:
            when = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            meta["captured_at_from"] = "file_mtime"
        cls, _ = privacy.classify(conn, {"source": source, "mime": mime, "object_kind": kind,
                                         "categories": {c for c, _ in privacy.detect(name)}})
        cls = privacy.strictest(cls, privacy_class)
        # local_only always lands in the encrypted zone; callers may also ask for it explicitly (e.g. third-party media)
        zone = "secure" if cls == "local_only" or zone == "secure" else "clear"
        key = f"{source}/{when:%Y}/{when:%m}/{when:%Y%m%d-%H%M%S}_{sha[:8]}_{safe_name(name)}"
        (storage_client or s3()).upload_file(str(path), BUCKETS[zone], key, ExtraArgs={"ContentType": mime})
        row = conn.execute(
            """insert into core.objects (sha256, size_bytes, mime, kind, storage_key, original_name, captured_at, source,
                                         source_ref, meta, privacy_class, storage_zone)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
            (sha, path.stat().st_size, mime, kind, key, name, when, source, json.dumps(source_ref or {}),
             json.dumps(meta), cls, zone)).fetchone()
        row["created"] = True
    else:
        row["created"] = False  # same bytes already stored: only add provenance links
    for target_type, target_id in links or []:
        conn.execute("""insert into core.object_links (object_id, target_type, target_id) values (%s,%s,%s)
                        on conflict do nothing""", (row["id"], target_type, str(target_id)))
    return row


def find(ref: str) -> dict | None:
    col = "sha256" if re.fullmatch(r"[0-9a-f]{64}", ref) else "id::text"
    with connection() as conn:
        return conn.execute(f"select * from core.objects where {col} = %s and purged_at is null", (ref,)).fetchone()


def get_object(ref: str, dest: str | Path | None = None, *, max_privacy: str = "local_only",
               dest_dir: str | Path | None = None) -> Path:
    """Download authorized bytes, then verify SHA256. Deny before filesystem or S3 access."""
    row = find(ref)
    if not row:
        raise FileNotFoundError(f"no vault object {ref}")
    if row.get("privacy_class") not in privacy.allowed_classes(max_privacy):
        raise PermissionError("vault object is not permitted for this privacy scope")
    if dest_dir is not None:
        if dest is not None:
            raise ValueError("pass dest or dest_dir, not both")
        directory = Path(dest_dir)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest = directory
    out = Path(dest) if dest else Path.cwd() / safe_name(row["original_name"] or row["sha256"])
    if out.is_dir():
        out = out / safe_name(row["original_name"] or row["sha256"])
    s3().download_file(BUCKETS[row["storage_zone"]], row["storage_key"], str(out))
    if sha256_file(out) != row["sha256"]:
        out.unlink(missing_ok=True)
        raise IOError(f"integrity error: object {ref} does not match its sha256")
    return out


def _scope_sql(thread_id: str | None, event_id: str | None) -> tuple[str, list]:
    """Object ids attached to the messages of a thread, or to one event: per-message links (core.object_links),
    the events' object_refs, and files linked to a whole thread (e.g. a Hermes session). Resolved at read time, so
    the whole history is covered without rewriting append-only events (A5)."""
    from .events import EVENT_LINKS, THREAD_LINKS, link_sql
    if event_id:
        ev, ev_args = "e.event_id = %s::uuid", [event_id]
    else:   # the source list lets the (source, thread_id, occurred_at) index serve the thread
        ev, ev_args = "e.source = any(%s) and e.thread_id = %s", [list(EVENT_LINKS) + list(THREAD_LINKS), thread_id]
    sql = (f"id in (select l.object_id from core.events e join core.object_links l on {link_sql('e')} where {ev}"
           f" union select unnest(e.object_refs) from core.events e where {ev}")
    args = ev_args + ev_args
    if thread_id and not event_id:
        sql += " union select l.object_id from core.object_links l where l.target_type = any(%s) and l.target_id = %s"
        args += [list(THREAD_LINKS.values()), thread_id]
    return sql + ")", args


def search(text: str = "", kind: str | None = None, source: str | None = None, limit: int = 20,
           *, max_privacy: str = "local_only", thread_id: str | None = None, event_id: str | None = None,
           since=None, until=None, derived: bool | None = None, text_chars: int = 300) -> list[dict]:
    """Filter metadata and derived snippets before any object row leaves the library.
    thread_id / event_id: the files of one conversation or one message (« the voice notes of conversation X » = one
    call with kind="audio", oldest first); since/until on captured_at; derived: only objects with (True) / without
    (False) a derived text."""
    where, args = ["purged_at is null", "privacy_class = any(%s)"], [privacy.allowed_classes(max_privacy)]
    if text:
        where.append("(to_tsvector('french', coalesce(derived_text,'') || ' ' || coalesce(original_name,''))"
                     " @@ websearch_to_tsquery('french', %s) or original_name ilike %s)")
        args += [text, f"%{text}%"]
    if kind:
        where.append("kind = %s"); args.append(kind)
    if source:
        where.append("source = %s"); args.append(source)
    if thread_id or event_id:
        s, a = _scope_sql(thread_id, event_id)
        where.append(s); args += a
    if since:
        where.append("captured_at >= %s::timestamptz"); args.append(str(since))
    if until:
        where.append("captured_at < %s::timestamptz"); args.append(str(until))
    if derived is not None:
        where.append("derived_at is not null" if derived else "derived_at is null")
    order = "captured_at asc nulls last" if thread_id or event_id else "captured_at desc nulls last"
    with connection() as conn:
        return conn.execute(
            f"""select id::text, kind, source, mime, original_name, captured_at, size_bytes, privacy_class, storage_zone,
                       derived_kind, left(derived_text, {max(0, int(text_chars))}) as derived_text
                from core.objects where {' and '.join(where)} order by {order} limit %s""",
            (*args, limit)).fetchall()


DERIVED_KINDS = ("transcript", "extract", "ocr", "caption")   # core.objects.derived_kind check (001)


def set_derived(object_id: str, text: str, derived_kind: str, *, model: str | None, processor: str,
                meta: dict | None = None, conn=None) -> dict:
    """The write path of an object's derived text (A5): text, kind, model, processor, time, status 'derived', and
    `meta.media` (result notes such as no speech). Credentials are masked before storage; the object's privacy class
    is only ever tightened by what the text reveals. The objects_publish trigger publishes the change (memory.object)
    in the same transaction, so the search index follows within seconds."""
    if derived_kind not in DERIVED_KINDS:
        raise ValueError(f"derived_kind must be one of {DERIVED_KINDS}")
    if conn is None:
        with connection() as c:
            return set_derived(object_id, text, derived_kind, model=model, processor=processor, meta=meta, conn=c)
    text = privacy.mask_secrets(text or "") or ""
    if "\x00" in text:
        text = text.replace("\x00", "\ufffd")
    row = conn.execute("select source, privacy_class from core.objects where id = %s::uuid", (str(object_id),)).fetchone()
    if row is None:
        raise FileNotFoundError(f"no vault object {object_id}")
    cats = {c for c, _ in privacy.detect(text)}
    cls = row["privacy_class"]
    if cats:
        cls = privacy.strictest(cls, privacy.classify(conn, {"source": row["source"], "categories": cats})[0])
    return conn.execute(
        """update core.objects set derived_text = %s, derived_kind = %s, derived_model = %s, derived_processor = %s,
                  derived_at = now(), status = 'derived', privacy_class = %s,
                  meta = meta || jsonb_build_object('media', %s::jsonb)
           where id = %s::uuid
           returning id::text, kind, derived_kind, derived_model, derived_processor, derived_at, privacy_class,
                     length(derived_text) as chars""",
        (text, derived_kind, model, processor, cls, json.dumps(meta or {}, ensure_ascii=False, default=str),
         str(object_id))).fetchone()


def stats() -> list[dict]:
    with connection() as conn:
        return conn.execute("""select source, kind, storage_zone, count(*) as files, pg_size_pretty(sum(size_bytes)) as size,
                                      count(derived_text) as with_text
                               from core.objects where purged_at is null group by 1, 2, 3 order by 1, 2, 3""").fetchall()


def move_to_secure(ref: str, conn=None) -> dict:
    """Re-home an object in the encrypted zone (bytes copied + verified, clear copy deleted, row updated)."""
    import tempfile
    if conn is None:
        with connection() as c:
            return move_to_secure(ref, conn=c)
    row = conn.execute("select * from core.objects where id::text = %s or sha256 = %s", (ref, ref)).fetchone()
    if row["storage_zone"] == "secure":
        return row
    with tempfile.TemporaryDirectory(dir="/var/tmp") as d:
        tmp = Path(d) / "obj"
        s3().download_file(BUCKETS["clear"], row["storage_key"], str(tmp))
        if sha256_file(tmp) != row["sha256"]:
            raise IOError(f"integrity error while moving {ref}")
        s3().upload_file(str(tmp), BUCKETS["secure"], row["storage_key"], ExtraArgs={"ContentType": row["mime"]})
    s3().delete_object(Bucket=BUCKETS["clear"], Key=row["storage_key"])
    return conn.execute("""update core.objects set storage_zone = 'secure',
                               privacy_class = case when privacy_class = 'cloud_allowed' then 'local_only' else privacy_class end
                           where id = %s returning *""", (row["id"],)).fetchone()
