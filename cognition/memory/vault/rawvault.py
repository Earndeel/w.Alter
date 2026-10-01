#!/usr/bin/env python3
"""walter-raw-vault — W.Alter's store for every non-text raw file (images, video, audio, documents...).

Bytes live in Google Drive (folder "W.Alter Raw Vault", plain files, browsable), reached through a local
S3 API (`raw-vault-s3`, rclone serve s3 on 127.0.0.1:8899). The catalog lives in Postgres, schema `vault`:
one row per distinct file (sha256), with provenance, links to people/messages/sessions, and the derived
text (OCR, transcript, caption) that memory can actually use.

Layout in the bucket "raw" (readable from Drive):
    <source>/<YYYY>/<MM>/<YYYYMMDD-HHMMSS>_<sha8>_<original-name>

Library:  put(path, source, ...) -> dict    get(ref, dest) -> path    search(text) -> list
CLI:      rawvault.py put FILE --source S [--ref JSON] [--captured ISO] [--link type:id]
          rawvault.py get ID|SHA256 [DEST]  |  rawvault.py search TEXT  |  rawvault.py stats
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import boto3
import psycopg2
import psycopg2.extras
from botocore.config import Config

HERE = Path(__file__).resolve().parent
BUCKET = "raw"


def _load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _s3():
    return boto3.client(
        "s3", endpoint_url=os.environ.get("RAW_VAULT_S3_ENDPOINT", "http://127.0.0.1:8899"),
        aws_access_key_id=os.environ["RAW_VAULT_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["RAW_VAULT_S3_SECRET_KEY"], region_name="«secret:vault»",
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4",
                      retries={"max_attempts": 5, "mode": "standard"}))


def _db():
    conn = psycopg2.connect(os.environ["RAW_VAULT_DATABASE_URL"])
    conn.autocommit = False
    return conn


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


SCREENSHOT_RE = re.compile(r"(screenshot|capture d.?[ée]cran|screen ?shot|scr_|img_\d+_\d+_screenshot)", re.I)


def _kind(mime: str | None, name: str) -> str:
    m = mime or ""
    if m.startswith("image/"):
        return "screenshot" if SCREENSHOT_RE.search(name) else "image"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    if m in ("application/zip", "application/x-tar", "application/gzip", "application/x-7z-compressed"):
        return "archive"
    if m.startswith("text/") or m.startswith("application/"):
        return "document"
    return "other"


def _image_meta(path: Path) -> tuple[dict, datetime | None]:
    """Dimensions + EXIF capture time when the file is an image Pillow can read."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            meta = {"width": im.width, "height": im.height}
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, else DateTime
            when = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc) if raw else None
            return meta, when
    except Exception:
        return {}, None


def _safe_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).strip().replace("/", "_")
    name = re.sub(r"[\x00-\x1f\\:*?\"<>|]+", "_", name)
    return name[-120:] or "file"


def put(path: str | Path, source: str, source_ref: dict | None = None, captured_at: datetime | None = None,
        links: list[tuple[str, str]] | None = None, original_name: str | None = None) -> dict:
    """Store a file once (dedupe by sha256), catalog it, attach links. Returns the catalog row."""
    path = Path(path)
    sha = _sha256(path)
    name = original_name or path.name
    with _db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select * from vault.objects where sha256 = %s", (sha,))
        row = cur.fetchone()
        if row is None:
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            meta, exif_when = _image_meta(path) if mime.startswith("image/") else ({}, None)
            when = captured_at or exif_when
            if when is None:
                when = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                meta["captured_at_from"] = "file_mtime"
            key = f"{source}/{when:%Y}/{when:%m}/{when:%Y%m%d-%H%M%S}_{sha[:8]}_{_safe_name(name)}"
            _s3().upload_file(str(path), BUCKET, key, ExtraArgs={"ContentType": mime})
            cur.execute(
                """insert into vault.objects (sha256, size_bytes, mime, kind, storage_key, original_name,
                                              captured_at, source, source_ref, meta)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
                (sha, path.stat().st_size, mime, _kind(mime, name), key, name, when, source,
                 json.dumps(source_ref or {}), json.dumps(meta)))
            row = cur.fetchone()
            row["created"] = True
        else:
            row["created"] = False  # same bytes already stored: only add the new provenance as links
        for target_type, target_id in links or []:
            cur.execute("""insert into vault.links (object_id, target_type, target_id) values (%s,%s,%s)
                           on conflict do nothing""", (row["id"], target_type, str(target_id)))
        conn.commit()
    return dict(row)


def _find(cur, ref: str) -> dict | None:
    col = "sha256" if re.fullmatch(r"[0-9a-f]{64}", ref) else "id::text"
    cur.execute(f"select * from vault.objects where {col} = %s", (ref,))
    return cur.fetchone()


def get(ref: str, dest: str | Path | None = None) -> Path:
    """Download an object (by id or sha256) to dest (default: current dir, original name)."""
    with _db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        row = _find(cur, ref)
    if not row:
        raise SystemExit(f"no vault object {ref}")
    out = Path(dest) if dest else Path.cwd() / _safe_name(row["original_name"] or row["sha256"])
    if out.is_dir():
        out = out / _safe_name(row["original_name"] or row["sha256"])
    _s3().download_file(BUCKET, row["storage_key"], str(out))
    if _sha256(out) != row["sha256"]:
        raise SystemExit(f"integrity error: {out} does not match sha256 {row['sha256']}")
    return out


def search(text: str = "", kind: str | None = None, source: str | None = None, limit: int = 20) -> list[dict]:
    """Full-text search over derived text + file names, newest first when text is empty."""
    where, args = [], []
    if text:
        where.append("(to_tsvector('french', coalesce(derived_text,'') || ' ' || coalesce(original_name,''))"
                     " @@ websearch_to_tsquery('french', %s) or original_name ilike %s)")
        args += [text, f"%{text}%"]
    if kind:
        where.append("kind = %s"); args.append(kind)
    if source:
        where.append("source = %s"); args.append(source)
    sql = ("select id::text, kind, source, original_name, captured_at, size_bytes, storage_key, "
           "left(derived_text, 300) as derived_text from vault.objects "
           + ("where " + " and ".join(where) if where else "") + " order by captured_at desc nulls last limit %s")
    with _db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (*args, limit))
        return [dict(r) for r in cur.fetchall()]


def stats() -> list[dict]:
    with _db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""select source, kind, count(*) as files, pg_size_pretty(sum(size_bytes)) as size,
                              count(derived_text) as with_text from vault.objects group by 1, 2 order by 1, 2""")
        return [dict(r) for r in cur.fetchall()]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("put"); a.add_argument("file"); a.add_argument("--source", required=True)
    a.add_argument("--ref", default="{}"); a.add_argument("--captured"); a.add_argument("--name")
    a.add_argument("--link", action="append", default=[], help="type:id, e.g. kardex_contact:5")
    g = sub.add_parser("get"); g.add_argument("ref"); g.add_argument("dest", nargs="?")
    s = sub.add_parser("search"); s.add_argument("text", nargs="?", default="")
    s.add_argument("--kind"); s.add_argument("--source"); s.add_argument("--limit", type=int, default=20)
    sub.add_parser("stats")
    args = p.parse_args()
    if args.cmd == "put":
        when = datetime.fromisoformat(args.captured) if args.captured else None
        row = put(args.file, args.source, json.loads(args.ref), when,
                  [tuple(x.split(":", 1)) for x in args.link], args.name)
        print(json.dumps({k: row[k] for k in ("id", "created", "kind", "storage_key")}, default=str))
    elif args.cmd == "get":
        print(get(args.ref, args.dest))
    elif args.cmd == "search":
        print(json.dumps(search(args.text, args.kind, args.source, args.limit), default=str, ensure_ascii=False, indent=1))
    else:
        print(json.dumps(stats(), default=str, indent=1))


if __name__ == "__main__":
    main()
