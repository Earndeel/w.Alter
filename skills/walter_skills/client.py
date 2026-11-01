"""Client of walter-skills for adapters (hooks, MCP). Standard library only — importable from any venv.

Resilience ladder: the service answers → full policy and ranking. The service is down → search and read fall back to
the git store on disk (keyword search over SKILL.md frontmatter, direct file read); exposure fails open (nothing
injected, the agent keeps its own search). Never raises.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL = os.environ.get("WALTER_SKILLS_URL", "http://127.0.0.1:8891")
STORE = Path(os.environ.get("WALTER_SKILLS_STORE", "/walter/skills"))


def _call(method: str, path: str, body: dict | None = None, timeout: float = 4.0):
    req = urllib.request.Request(URL + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (local service)
        raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw


def expose(kind: str, message: str, *, context: str = "", session_id: str | None = None, runtime: str = "agent",
           first_turn: bool = False, timeout: float = 4.0) -> dict:
    try:
        return _call("POST", "/v1/expose", {"kind": kind, "message": message, "context": context,
                                            "session_id": session_id, "runtime": runtime, "first_turn": first_turn},
                     timeout)
    except Exception:
        return {"text": "", "shown": [], "mode": "unavailable"}


def search(query: str, context: str = "", k: int = 8, include_archived: bool = False, runtime: str = "agent",
           session_id: str | None = None) -> list[dict]:
    try:
        return _call("POST", "/v1/search", {"query": query, "context": context, "k": k, "runtime": runtime,
                                            "include_archived": include_archived, "session_id": session_id},
                     10)["results"]
    except Exception:
        return _local_search(query, k, include_archived)


def read(name: str, file_path: str = "", runtime: str = "agent", session_id: str | None = None) -> str | None:
    q = urllib.parse.urlencode({k: v for k, v in {"file_path": file_path, "runtime": runtime,
                                                  "session_id": session_id}.items() if v})
    try:
        return _call("GET", f"/v1/skill/{urllib.parse.quote(name)}?{q}", timeout=10)
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else _local_read(name, file_path)
    except Exception:
        return _local_read(name, file_path)


def manifest() -> str:
    try:
        return _call("GET", "/v1/manifest", timeout=10)
    except Exception:
        try:
            return (STORE / "manifest" / "GUIDE.md").read_text()
        except OSError:
            return "Module manifest unavailable; search/read remain available."


def index(domain: str = "", offset: int = 0, limit: int = 20) -> dict:
    q = urllib.parse.urlencode({"domain": domain, "offset": offset, "limit": limit})
    try:
        return _call("GET", f"/v1/index?{q}", timeout=10)
    except Exception:
        return {"unavailable": True, "hint": "Use skills_search(query=…) and skill_read(name)."}


def write(kind: str, body: dict) -> dict:
    try:
        return _call("POST", f"/v1/skills/{kind}", body, timeout=30)
    except Exception as e:
        return {"ok": False, "refused": f"walter-skills unavailable: {e}"}


# ── degraded mode: the git store on disk ──────────────────────────────────────────────────────────────

def _skill_dirs(include_archived: bool):
    roots = [STORE / "skills"] + ([STORE / "archive"] if include_archived else [])
    for root in roots:
        for md in root.rglob("SKILL.md") if root.exists() else []:
            yield md.parent, root.name == "archive"


def _desc(md: Path) -> str:
    m = re.search(r"(?m)^description:\s*(.+)$", md.read_text(errors="replace")[:4000])
    return m.group(1).strip().strip("\"'") if m else ""


def _local_search(query: str, k: int, include_archived: bool) -> list[dict]:
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
    scored = []
    for d, archived in _skill_dirs(include_archived):
        desc = _desc(d / "SKILL.md")
        hay = f"{d.name} {desc}".lower()
        s = sum(hay.count(w) + 3 * (w in d.name) for w in words)
        if s:
            scored.append((s, {"name": d.name, "summary": desc[:220], "state": "archived" if archived else "active",
                               "score": float(s), "degraded": True}))
    return [x for _, x in sorted(scored, key=lambda x: -x[0])[:k]]


def _local_read(name: str, file_path: str = "") -> str | None:
    for d, _ in _skill_dirs(True):
        if d.name == name:
            p = (d / file_path).resolve() if file_path else d / "SKILL.md"
            if str(p).startswith(str(d.resolve())) and p.is_file():
                return p.read_text(errors="replace")
    return None
