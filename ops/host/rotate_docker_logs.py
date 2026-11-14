#!/usr/bin/env python3
"""Small copytruncate rotator for Docker json-file logs on hosts without logrotate.

Default target is only the memory stack containers. Safe for running containers:
copy current log to a timestamped .1 file, truncate original in-place, gzip the copy,
and keep the newest N archives.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def inspect_containers(names: list[str]) -> list[dict]:
    out = []
    for name in names:
        p = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            out.append({"container": name, "ok": False, "error": p.stderr.strip()})
            continue
        obj = json.loads(p.stdout)[0]
        out.append({"container": name, "ok": True, "log_path": obj.get("LogPath")})
    return out


def rotate(path: Path, max_bytes: int, keep: int, dry_run: bool = False) -> dict:
    if not path.exists():
        return {"path": str(path), "ok": False, "error": "missing"}
    size = path.stat().st_size
    result = {"path": str(path), "size_mb_before": round(size / 1024 / 1024, 2), "rotated": False}
    if size < max_bytes:
        return result
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archive = path.with_name(path.name + f".{ts}")
    gz = Path(str(archive) + ".gz")
    if dry_run:
        result["would_archive"] = str(gz)
        return result
    with path.open("rb") as src, archive.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    with path.open("r+b") as f:
        f.truncate(0)
    with archive.open("rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    archive.unlink(missing_ok=True)
    archives = sorted(path.parent.glob(path.name + ".*.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for old in archives[keep:]:
        removed.append(str(old))
        old.unlink(missing_ok=True)
    result.update({"rotated": True, "archive": str(gz), "size_mb_after": round(path.stat().st_size / 1024 / 1024, 2), "removed_old_archives": removed})
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--containers", nargs="*", default=["hindsight-pg"])
    ap.add_argument("--max-mb", type=int, default=50)
    ap.add_argument("--keep", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    max_bytes = args.max_mb * 1024 * 1024
    report = []
    for item in inspect_containers(args.containers):
        if not item.get("ok"):
            report.append(item)
            continue
        lp = item.get("log_path")
        if not lp:
            item.update({"ok": False, "error": "no LogPath"})
            report.append(item)
            continue
        r = rotate(Path(lp), max_bytes, args.keep, args.dry_run)
        r["container"] = item["container"]
        report.append(r)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
