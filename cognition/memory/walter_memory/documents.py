"""Documents as knowledge (2026-10-28): the instance's curated records, cut into sections, in the knowledge lane.

Decisions taken in Claude Code / Codex sessions reach the knowledge lane only through the records the agents keep
(the L3 extract summarises Hermes conversations): the dated register of decisions, the rules an agent wrote down
after the owner said them. The DSH context trials (2026-10-28) found 5 of 6 such answers absent from the context
because nothing indexed them. This source reads the documents the instance declares
(`walter instance config memory documents.toml`), one `core.derived_items` row per section (kind `doc_section`),
no model call. Each section version is first a canonical event (`document.section`, the evidence the knowledge row
points to, as read_policy requires); a section whose text changes gets a new event and row, the old ones are
retracted and their chunks hidden, so the knowledge lane holds only the current text. A section where a secret pattern is detected is never stored.

  [[source]]  name = "decisions", path = "/…/DECISIONS.md", split = "h2"     one row per `## ` section
              name = "owner-rules", path = "/…/memory/*.md", split = "file"  one row per file (front matter dropped)
              privacy = "cloud_allowed" (default; a detected category tightens it to local_only)
              exclude = ["INDEX.md"]  file names a glob must skip
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from . import privacy
from .db import connect
from .events import record_events

KIND = "doc_section"
PROCESSOR = "documents"
VERSION = 1
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})")
FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)
MAX_CHARS = 12000


def config() -> list[dict]:
    try:
        path = subprocess.run(["walter", "instance", "config", "memory", "documents.toml"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
        return tomllib.loads(Path(path).read_text()).get("source", []) if path else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def sections(path: str, split: str) -> list[dict]:
    text = Path(path).read_text(errors="replace")
    mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    if split == "file":
        body = FRONT.sub("", text).strip()
        m = re.search(r"^description:\s*\"?(.+?)\"?\s*$", text, re.M)
        title = m.group(1) if m else Path(path).stem
        return [{"key": Path(path).name, "title": title, "text": body, "date": mtime}] if body else []
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                out.append(cur)
            heading = line[3:].strip()
            d = DATED.match(heading)
            cur = {"key": heading, "title": heading, "lines": [line],
                   "date": datetime.fromisoformat(d.group(1)).replace(tzinfo=timezone.utc) if d else mtime}
        elif cur:
            cur["lines"].append(line)
    if cur:
        out.append(cur)
    for s in out:
        s["text"] = "\n".join(s.pop("lines")).strip()
    # the same heading can recur (two entries the same day with one title): keep each, numbered
    seen: dict[str, int] = {}
    for s in out:
        n = seen[s["key"]] = seen.get(s["key"], 0) + 1
        if n > 1:
            s["key"] = f"{s['key']} #{n}"
    return out


def sync(dry_run: bool = False) -> dict:
    stats = {"sources": 0, "sections": 0, "new": 0, "changed": 0, "unchanged": 0, "removed": 0, "skipped_secret": 0}
    with connect() as conn:
        current = {r["k"]: r for r in conn.execute(
            """select item_id, attributes->>'doc_key' k, attributes->>'sha' sha, source_event_ids from core.derived_items
               where kind = %s and status = 'derived'""", (KIND,)).fetchall()}
        live = set()
        for src in config():
            stats["sources"] += 1
            files = sorted(glob.glob(src["path"])) if any(c in src["path"] for c in "*?[") else [src["path"]]
            for f in files:
                if not os.path.isfile(f) or os.path.basename(f) in src.get("exclude", []):
                    continue
                for s in sections(f, src.get("split", "h2")):
                    stats["sections"] += 1
                    key = f"{src['name']}:{f}:{s['key']}"
                    body = s["text"][:MAX_CHARS]
                    sha = hashlib.sha256(body.encode()).hexdigest()
                    found = privacy.detect(body)
                    if any(cat == "secret" for cat, _ in found):
                        stats["skipped_secret"] += 1
                        continue
                    live.add(key)
                    old = current.get(key)
                    if old and old["sha"] == sha and old["source_event_ids"]:
                        stats["unchanged"] += 1
                        continue
                    stats["changed" if old else "new"] += 1
                    if not dry_run:
                        _record(conn, src, f, s, key, body, sha, "local_only" if found else src.get("privacy", "cloud_allowed"))
                        if old:
                            _retire(conn, old, "superseded")
        for key, old in current.items():
            if key not in live:
                stats["removed"] += 1
                if not dry_run:
                    _retire(conn, old, "removed")
    return stats


def _record(conn, src: dict, path: str, s: dict, key: str, body: str, sha: str, pclass: str) -> None:
    """The section version as canonical evidence (document.section), then the knowledge row that points to it: derived
    knowledge is only readable through readable provenance (read_policy)."""
    meta = {"doc_key": key, "source": src["name"], "path": path, "title": s["title"], "sha": sha}
    source_id = f"{key}|{sha[:16]}"
    record_events([{"event_type": "document.section", "source": PROCESSOR, "source_id": source_id,
                    "occurred_at": s["date"], "content": body, "payload": meta, "privacy_class": pclass}], conn=conn)
    event_id = conn.execute("""select event_id from core.event_keys where source = %s and source_id = %s
                               and event_type = 'document.section'""", (PROCESSOR, source_id)).fetchone()["event_id"]
    conn.execute(
        """insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version, source_event_ids,
               source_refs, confidence, valid_from, privacy_class)
           values (%s, %s, %s, 'derived', %s, %s, %s, %s, 1.0, %s, %s)""",
        (KIND, body, json.dumps(meta, ensure_ascii=False), PROCESSOR, VERSION, [event_id],
         json.dumps([{"type": "file", "path": path, "section": s["key"]}], ensure_ascii=False), s["date"], pclass))


def _retire(conn, old: dict, reason: str) -> None:
    conn.execute("""update core.derived_items set status = 'retracted',
                    attributes = attributes || jsonb_build_object('retracted_reason', %s::text) where item_id = %s""",
                 (reason, old["item_id"]))
    conn.execute("""update search.chunks set hidden = true, hidden_reason = %s where kind = 'derived' and ref_id = %s""",
                 (reason, old["item_id"]))
    for eid in old.get("source_event_ids") or []:
        record_events([{"event_type": "event.retracted", "source": "walter", "source_id": f"retract:{eid}",
                        "occurred_at": datetime.now(timezone.utc), "privacy_class": "cloud_allowed",
                        "payload": {"target_event_id": str(eid), "reason": f"document section {reason}"}}], conn=conn)


def sync_if_changed() -> dict:
    """The index pass calls this every time: a stat of the declared files, a sync only when one changed."""
    from . import ingestion
    stamp = {}
    for src in config():
        files = sorted(glob.glob(src["path"])) if any(c in src["path"] for c in "*?[") else [src["path"]]
        for f in files:
            if os.path.isfile(f):
                stamp[f] = os.path.getmtime(f)
    digest = hashlib.sha256(json.dumps(stamp, sort_keys=True).encode()).hexdigest()
    if ingestion.get_checkpoint(PROCESSOR, "files").get("digest") == digest:
        return {}
    out = sync()
    ingestion.set_checkpoint(PROCESSOR, "files", {"digest": digest, "files": len(stamp)})
    ingestion.mark_success(PROCESSOR)
    return out


def listing() -> list[dict]:
    with connect() as conn:
        return conn.execute("""select attributes->>'source' source, attributes->>'title' title, valid_from::date day,
                                      privacy_class, length(content) chars from core.derived_items
                               where kind = %s and status = 'derived' order by valid_from desc""", (KIND,)).fetchall()


def register() -> None:
    """Once per instance: the source, the connector (its checkpoint) and the event type (seeded in event_types/v1.json)."""
    from . import ingestion, types
    types.sync_seed()
    with connect() as conn:
        conn.execute("""insert into core.sources (source, kind, description, privacy_default)
                        values ('documents', 'files', 'Curated records the instance declares (documents.toml)', 'cloud_allowed')
                        on conflict (source) do nothing""")
    ingestion.register_connector(PROCESSOR, "documents", "pull", "Curated records (documents.toml) as document.section "
                                 "events + doc_section knowledge; synced by the index pass when a file changes")
