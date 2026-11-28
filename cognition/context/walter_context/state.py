"""WorkingState — the living context of one session / thread (2026-11-17).

Walter Memory stays the truth. It already rebuilds a per-thread working state (`walter_memory.working`: objective,
constraints, decisions, commitments, pending owner messages, the agent's plan). This module is the engine-side,
incremental layer ON TOP of it: what happened during the run that Memory has not (or not yet) absorbed — tool
results, tasks and sub-agents, observations, failures, interruptions — plus an invalidatable projection of what
Memory said. It is compact, persistable, updated by events with deterministic code (no model), and renders a French
block of at most `text_chars` for injection after a compaction or on a wake-up turn.

Every item carries
  source        {"type": message|tool|task|subagent|memory|system|observation, "id": ..., "at": ISO}
  observed_at   when the fact was seen; `ttl_s` + `stale` say how long it can be trusted
  verification  observed (seen by a tool / the system) | inferred | reported (said by the owner, a sub-agent, Memory) |
                unverified (not checked, or invalidated)
Memory-derived items also carry `memory_ref` {ref, updated_at, version}: on `memory.changed` they are marked stale and
unverified (or replaced by a fresh projection) — never trusted silently.

Events (kind → payload): message.owner {text} · tool.result {tool, ok, summary, ref} · task.started / task.ended
{task_id, goal, status, result} · subagent.reply {subagent_id, text, alternative, contradicts} · objective.changed
{goal, status, objective_id} · observation {text, key, value, verification} · memory.changed {refs, items,
updated_at, version} · failure {where, error} · interrupted {reason} · context.changed {reason, capabilities}.
Unknown kinds are refused (`UnknownEvent`), never guessed.

Concurrency: events are queued per session and applied together after `coalesce_ms` (the HTTP door returns at once);
a session's apply holds a thread lock plus an flock on its file, reloads the file when another process wrote it, and
saves atomically (tmp + rename, 0600) with `version` + 1 per applied event. `update(..., expected_version=n)` is the
compare-and-set door: it raises VersionConflict when the version moved.

Bounded: `compact()` drops only what can be recomputed or has lost its use (old observations, stale information,
ended tasks, references) and says so (`dropped`: count + last references). Pending items, constraints, open tasks,
objectives, decisions, contradictions and uncertainties are never dropped.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import state_settings
from .longtext import binding, represent

EVENT_KINDS = ("message.owner", "tool.result", "task.started", "task.updated", "task.ended", "subagent.started",
               "subagent.reply", "objective.changed", "observation", "memory.changed", "failure", "interrupted",
               "context.changed")
SECTIONS = ("objectives", "tasks", "constraints", "decisions", "information", "observations", "sources", "pending",
            "uncertainties", "contradictions", "capabilities")
PROTECTED = ("objectives", "constraints", "decisions", "pending", "contradictions", "uncertainties")   # never dropped
VERIFICATIONS = ("observed", "inferred", "reported", "unverified")
OPEN_TASK = ("running", "pending", "interrupted", "waiting")
SCHEMA = 1


class UnknownEvent(ValueError):
    pass


class VersionConflict(RuntimeError):
    pass


def now_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).isoformat(timespec="seconds")


def _ts(iso: str | None) -> float | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() if iso else None
    except (ValueError, AttributeError):
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _id(kind: str, text: str) -> str:
    return hashlib.sha1(f"{kind}|{_norm(text).lower()}".encode()).hexdigest()[:10]


# ── storage ──────────────────────────────────────────────────────────────────────────────────────────────────────
_ROOT: list[Path | None] = []


def state_dir() -> Path | None:
    """<instance>/state/context/working (resolved with `walter instance path`, once); WALTER_CONTEXT_STATE_DIR overrides."""
    env = os.environ.get("WALTER_CONTEXT_STATE_DIR")
    if env:
        return Path(env)
    if not _ROOT:
        try:
            root = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None                                    # not cached: asked again next time
        _ROOT.append(Path(root) / "state" / "context" / "working" if root else None)
    return _ROOT[0]


def empty(session_id: str) -> dict:
    return {"schema": SCHEMA, "session_id": session_id, "version": 0, "updated_at": now_iso(), "thread_id": None,
            "run_id": None, "operation": {"phase": "idle", "failures": 0, "interrupted": False, "events": 0,
                                          "needs_reinjection": False, "memory_dirty": False},
            **{s: [] for s in SECTIONS}, "dropped": {}}


class Store:
    """One JSON file per session under the instance's state dir: 0600, atomic writes, flock'ed read-modify-write."""

    def __init__(self, root: Path | None):
        self.root = root

    def _path(self, session_id: str) -> Path | None:
        if self.root is None:
            return None
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id)[:80]
        return self.root / f"{safe}-{hashlib.sha1(session_id.encode()).hexdigest()[:8]}.json"

    def load(self, session_id: str) -> dict | None:
        p = self._path(session_id)
        try:
            d = json.loads(p.read_text()) if p and p.exists() else None
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) and d.get("schema") == SCHEMA else None

    def lock(self, session_id: str):
        """Context manager: exclusive flock on the session's lock file (cross-process writers)."""
        store = self

        class _L:
            def __enter__(self_):
                p = store._path(session_id)
                self_.fd = None
                if p is not None:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    os.chmod(p.parent, 0o700)
                    self_.fd = os.open(str(p) + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
                    fcntl.flock(self_.fd, fcntl.LOCK_EX)
                return self_

            def __exit__(self_, *a):
                if self_.fd is not None:
                    fcntl.flock(self_.fd, fcntl.LOCK_UN)
                    os.close(self_.fd)
        return _L()

    def save(self, st: dict) -> None:
        p = self._path(st["session_id"])
        if p is None:
            return
        tmp = p.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def sessions(self) -> list[Path]:
        return sorted(self.root.glob("*.json")) if self.root and self.root.exists() else []


# ── items ────────────────────────────────────────────────────────────────────────────────────────────────────────
def item(kind: str, text: str, *, source_type: str, source_id: str | None = None, at: str | None = None,
         verification: str = "unverified", ttl_s: float | None = None, thread_id: str | None = None,
         memory_ref: dict | None = None, id: str | None = None, **extra) -> dict:
    if verification not in VERIFICATIONS:
        verification = "unverified"
    at = at or now_iso()
    out = {"id": id or _id(kind, text), "text": _norm(text), "source": {"type": source_type, "id": source_id, "at": at},
           "observed_at": at, "ttl_s": ttl_s, "stale": False, "verification": verification}
    if thread_id:
        out["thread_id"] = thread_id
    if memory_ref:
        out["memory_ref"] = memory_ref
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _put(st: dict, section: str, it: dict, *, replace_key: str = "id") -> dict:
    """Insert or refresh (same id): the freshest observation wins, its provenance replaces the older one."""
    rows = st[section]
    for i, old in enumerate(rows):
        if old.get(replace_key) == it.get(replace_key):
            rows[i] = {**old, **it}
            return rows[i]
    rows.append(it)
    return it


def _resolve(st: dict, section: str, pred) -> int:
    before = len(st[section])
    st[section] = [x for x in st[section] if not pred(x)]
    return before - len(st[section])


def _text(p: dict, *keys: str) -> str:
    for k in keys:
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if v is not None and not isinstance(v, (dict, list)) and str(v).strip():
            return str(v)
    return ""


# ── event handlers (deterministic) ───────────────────────────────────────────────────────────────────────────────
def _on_message_owner(st, ev, cfg):
    text, at, th = _text(ev["payload"], "text", "message"), ev["at"], ev.get("thread_id")
    mid = ev["payload"].get("message_id") or ev["payload"].get("event_id")
    if not text:
        return
    rep = represent(text, 400)
    st["operation"]["last_owner_message"] = {"text": rep.text, "length": rep.length, "at": at, "id": mid}
    st["operation"]["phase"] = "owner_message"
    # what the owner said that binds the work: sentences with a negation or an instruction (reported, in his words)
    n = 0
    for s in re.split(r"(?<=[.!?…;])\s+|\n+", text):
        if binding(s) and len(_norm(s)) > 6 and n < 5:
            _put(st, "constraints", item("constraint", _norm(s)[:300], source_type="message", source_id=mid, at=at,
                                         verification="reported", thread_id=th, owner=True))
            n += 1
    if "?" in text:
        _put(st, "pending", item("pending", "question du propriétaire : " + _norm(text)[-200:], source_type="message",
                                 source_id=mid, at=at, verification="reported", thread_id=th, resolves="agent_reply"))
    # a new owner message answers the agent's pending question and supersedes waiting items it addresses
    _resolve(st, "pending", lambda x: x.get("resolves") == "owner_reply")


def _on_tool_result(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    tool = _text(p, "tool", "name") or "outil"
    ok = p.get("ok", True) is not False and not p.get("error")
    summary = _text(p, "summary", "text", "result", "error")[:300]
    it = item("observation", f"{tool} : {'ok' if ok else 'échec'}{(' — ' + summary) if summary else ''}",
              source_type="tool", source_id=p.get("call_id") or p.get("ref") or tool, at=at, verification="observed",
              ttl_s=p.get("ttl_s", cfg["tool_ttl_s"]), thread_id=ev.get("thread_id"), ok=ok, tool=tool,
              key=p.get("key"), value=p.get("value"))
    _observe(st, it)
    if p.get("ref"):
        _put(st, "sources", item("source", str(p["ref"]), source_type="tool", source_id=tool, at=at,
                                 verification="observed", id=_id("source", str(p["ref"]))))
    if not ok:
        st["operation"]["failures"] += 1


def _observe(st, it: dict) -> None:
    """Keyed observations replace their predecessor; a different value from an equally or less certain source is a
    contradiction, never a silent overwrite."""
    key = it.get("key")
    if key:
        for old in st["observations"]:
            if old.get("key") == key and old["id"] != it["id"] and old.get("value") != it.get("value"):
                rank = {"observed": 3, "reported": 2, "inferred": 1, "unverified": 0}
                if rank[it["verification"]] < rank[old["verification"]] and not old.get("stale"):
                    _put(st, "contradictions", item("contradiction", f"« {key} » : {old.get('value')!r} "
                         f"({old['verification']}, {old['source']['type']}) ≠ {it.get('value')!r} ({it['verification']}, "
                         f"{it['source']['type']})", source_type="system", at=it["observed_at"], verification="unverified",
                         between=[old["id"], it["id"]]))
                    _put(st, "observations", it)
                    return
                st["observations"] = [o for o in st["observations"] if o is not old]
    _put(st, "observations", it)


def _task_row(st, task_id: str) -> dict | None:
    return next((t for t in st["tasks"] if t.get("task_id") == task_id), None)


def _on_task(st, ev, cfg):
    p, at, kind = ev["payload"], ev["at"], ev["kind"]
    tid = str(p.get("task_id") or p.get("id") or "")
    if not tid:
        return
    status = p.get("status") or {"task.started": "running", "task.ended": "done"}.get(kind, "running")
    if kind == "task.ended" and status not in ("done", "failed", "cancelled"):
        status = "done"
    goal = _text(p, "goal", "text", "title")
    row = _task_row(st, tid)
    new = item("task", goal or (row or {}).get("text") or f"tâche {tid}", source_type="task", source_id=tid, at=at,
               verification="observed", id=_id("task", tid), task_id=tid, status=status, task_kind=p.get("kind", "task"),
               result=(_text(p, "result", "error") or None) and _text(p, "result", "error")[:300],
               thread_id=ev.get("thread_id"))
    if row:
        new["text"] = goal or row["text"]
    _put(st, "tasks", new)
    if status in ("done", "cancelled"):
        _resolve(st, "pending", lambda x: x.get("task_id") == tid)
    elif status == "failed":
        st["operation"]["failures"] += 1
        _put(st, "pending", item("pending", f"tâche {tid} échouée : décider de la reprise ou de l'abandon",
                                 source_type="task", source_id=tid, at=at, verification="observed", task_id=tid))


def _on_subagent_started(st, ev, cfg):
    p = ev["payload"]
    tid = str(p.get("subagent_id") or p.get("id") or "")
    if tid:
        _put(st, "tasks", item("task", _text(p, "goal", "text") or f"sous-agent {tid}", source_type="subagent",
                               source_id=tid, at=ev["at"], verification="observed", id=_id("task", "sub:" + tid),
                               task_id="sub:" + tid, status="running", task_kind="subagent", thread_id=ev.get("thread_id")))


def _on_subagent_reply(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    sid = str(p.get("subagent_id") or p.get("id") or "subagent")
    text = _text(p, "text", "reply", "result")
    ok = p.get("ok", True) is not False
    row = _task_row(st, "sub:" + sid)
    if row:
        row.update(status="done" if ok else "failed", result=text[:300] or row.get("result"))
    else:
        _put(st, "tasks", item("task", f"sous-agent {sid}", source_type="subagent", source_id=sid, at=at,
                               verification="observed", id=_id("task", "sub:" + sid), task_id="sub:" + sid,
                               status="done" if ok else "failed", task_kind="subagent", result=text[:300] or None))
    if text:
        # a sub-agent's word is reported, not observed: it is information until something checks it
        info = item("information", text[:400], source_type="subagent", source_id=sid, at=at, verification="reported",
                    thread_id=ev.get("thread_id"))
        _put(st, "information", info)
        for ref in p.get("contradicts") or []:
            other = next((x for s in ("information", "observations", "decisions") for x in st[s] if x["id"] == ref), None)
            _put(st, "contradictions", item("contradiction", f"le sous-agent {sid} contredit « {(other or {}).get('text', ref)[:120]} »",
                                            source_type="subagent", source_id=sid, at=at, verification="unverified",
                                            between=[ref, info["id"]]))
    if p.get("alternative"):
        _put(st, "uncertainties", item("uncertainty", "autre voie proposée par " + sid + " : " + _norm(str(p["alternative"]))[:200],
                                       source_type="subagent", source_id=sid, at=at, verification="reported"))
    if not ok:
        st["operation"]["failures"] += 1


def _on_objective(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    goal = _text(p, "goal", "text", "objective")
    oid = str(p.get("objective_id") or p.get("id") or _id("objective", goal))
    status = p.get("status") or "active"
    old = next((o for o in st["objectives"] if o.get("objective_id") == oid), None)
    if status in ("done", "cancelled", "failed", "replaced"):
        if old:
            old.update(status=status, observed_at=at, stale=False)
        _resolve(st, "pending", lambda x: x.get("objective_id") == oid)
        return
    if not goal and not old:
        return
    for o in st["objectives"]:       # one active objective at a time: a new one replaces (and says so)
        if o.get("status") == "active" and o.get("objective_id") != oid:
            o["status"] = "replaced"
    _put(st, "objectives", item("objective", goal or old["text"], source_type=p.get("source", "message"),
                                source_id=p.get("message_id"), at=at, verification=p.get("verification", "reported"),
                                id=_id("objective", oid), objective_id=oid, status="active", thread_id=ev.get("thread_id")))
    st["operation"]["objective_version"] = st["operation"].get("objective_version", 0) + 1
    st["objectives"] = [o for o in st["objectives"] if o.get("status") == "active"] + \
        [o for o in st["objectives"] if o.get("status") != "active"][-3:]


def _on_observation(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    text = _text(p, "text", "summary")
    if not text:
        return
    _observe(st, item("observation", text, source_type=p.get("source", "observation"), source_id=p.get("source_id"),
                      at=at, verification=p.get("verification", "observed"), ttl_s=p.get("ttl_s", cfg["observation_ttl_s"]),
                      thread_id=ev.get("thread_id"), key=p.get("key"), value=p.get("value")))
    if p.get("ref"):
        _put(st, "sources", item("source", str(p["ref"]), source_type="observation", at=at, verification="observed",
                                 id=_id("source", str(p["ref"]))))
    if p.get("answers_owner"):                  # the agent answered: the owner's question is no longer waiting
        _resolve(st, "pending", lambda x: x.get("resolves") == "agent_reply")
    if p.get("uncertain"):
        _put(st, "uncertainties", item("uncertainty", _norm(str(p["uncertain"]))[:200], source_type="observation",
                                       at=at, verification="unverified"))


def _on_memory_changed(st, ev, cfg):
    """Memory is the truth: what it said is a projection, now out of date. Marked stale + unverified (or replaced by the
    fresh projection the event carries); never kept as if still current."""
    p, at = ev["payload"], ev["at"]
    refs = set(map(str, p.get("refs") or []))
    n = 0
    for section in SECTIONS:
        for x in st[section]:
            mr = x.get("memory_ref")
            if mr and (not refs or str(mr.get("ref")) in refs) and not x.get("memory_invalidated"):
                x.update(stale=True, verification="unverified", memory_invalidated=at)
                n += 1
    if p.get("items") is not None:
        fresh = {}
        for it in p["items"]:
            if isinstance(it, dict) and _text(it, "text"):
                kind = it.get("kind") if it.get("kind") in ("objective", "constraint", "decision", "information",
                                                           "pending", "uncertainty") else "information"
                sect = {"objective": "objectives", "constraint": "constraints", "decision": "decisions",
                        "information": "information", "pending": "pending", "uncertainty": "uncertainties"}[kind]
                ref = str(it.get("ref") or _id(kind, it["text"]))
                fresh[ref] = (sect, item(kind, it["text"], source_type="memory", source_id=ref, at=at,
                                         verification="reported", ttl_s=cfg["memory_ttl_s"], thread_id=ev.get("thread_id"),
                                         memory_ref={"ref": ref, "updated_at": it.get("updated_at") or p.get("updated_at") or at,
                                                     "version": it.get("version", p.get("version"))},
                                         **({"status": "active"} if kind == "objective" else {}),
                                         **({"objective_id": ref} if kind == "objective" else {})))
        whole = bool(p.get("refresh") or p.get("replace_all"))   # a complete projection: what Memory dropped leaves
        for sect in SECTIONS:                      # the old projection of these refs is replaced, not accumulated
            st[sect] = [x for x in st[sect] if not (x.get("memory_ref") and (whole or str(x["memory_ref"].get("ref")) in fresh))]
        for sect, it in fresh.values():
            st[sect].append(it)
        n = max(n - len(fresh), 0)
    st["operation"]["memory_dirty"] = n > 0
    st["operation"]["memory_changed_at"] = at


def _on_failure(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    where = _text(p, "where", "tool", "task_id") or "exécution"
    err = _text(p, "error", "text", "reason")[:240]
    st["operation"]["failures"] += 1
    st["operation"]["phase"] = "failed"
    st["operation"]["last_failure"] = {"where": where, "error": err, "at": at}
    _observe(st, item("observation", f"échec de {where}{(' : ' + err) if err else ''}", source_type=p.get("source", "system"),
                      source_id=where, at=at, verification="observed", ttl_s=cfg["observation_ttl_s"], ok=False,
                      thread_id=ev.get("thread_id")))
    _put(st, "pending", item("pending", f"traiter l'échec de {where}", source_type="system", source_id=where, at=at,
                             verification="observed", resolves="failure"))


def _on_interrupted(st, ev, cfg):
    p, at = ev["payload"], ev["at"]
    st["operation"].update(interrupted=True, phase="interrupted", interrupted_at=at)
    for t in st["tasks"]:
        if t.get("status") == "running":
            t["status"] = "interrupted"
    _put(st, "pending", item("pending", "reprise après interruption" + (f" ({_norm(_text(p, 'reason', 'by'))[:80]})"
                                                                       if _text(p, "reason", "by") else ""),
                             source_type="system", at=at, verification="observed", resolves="resume"))


def _on_context_changed(st, ev, cfg):
    p = ev["payload"]
    op = st["operation"]
    op["context_changes"] = op.get("context_changes", 0) + 1
    op["last_context_change"] = {"reason": _text(p, "reason") or "changed", "at": ev["at"]}
    if _text(p, "reason") in ("compaction", "wake", "wake-up", "window"):
        op["needs_reinjection"] = True
    for cap in p.get("capabilities") or []:
        _put(st, "capabilities", item("capability", str(cap), source_type="system", at=ev["at"], verification="observed"))
    if op.get("interrupted") and _text(p, "reason") in ("wake", "wake-up", "resumed"):
        op["interrupted"] = False
        _resolve(st, "pending", lambda x: x.get("resolves") == "resume")


HANDLERS = {"message.owner": _on_message_owner, "tool.result": _on_tool_result, "task.started": _on_task,
            "task.updated": _on_task, "task.ended": _on_task, "subagent.started": _on_subagent_started,
            "subagent.reply": _on_subagent_reply, "objective.changed": _on_objective, "observation": _on_observation,
            "memory.changed": _on_memory_changed, "failure": _on_failure, "interrupted": _on_interrupted,
            "context.changed": _on_context_changed}


# ── expiry and compaction ────────────────────────────────────────────────────────────────────────────────────────
def expire(st: dict, now: float | None = None) -> int:
    """Flag items past their ttl as stale (never deleted here: stale information is shown as such, and compaction
    decides what leaves). Returns the number newly flagged."""
    now = now if now is not None else time.time()
    n = 0
    for s in SECTIONS:
        for x in st[s]:
            ttl, t0 = x.get("ttl_s"), _ts(x.get("observed_at"))
            if ttl and t0 is not None and not x.get("stale") and now > t0 + ttl:
                x["stale"] = True
                n += 1
    return n


def compact(st: dict, max_items: int) -> dict:
    """Bound the state. Order of loss: stale observations (oldest first), stale information, ended tasks, sources,
    fresh observations beyond 20, capabilities. Protected sections stay whole. What is dropped is counted and its
    references kept (last 8) in `dropped`."""
    total = lambda: sum(len(st[s]) for s in SECTIONS)        # noqa: E731
    if total() <= max_items:
        return st
    dropped = st.setdefault("dropped", {})

    def drop(section, pred):
        rows = [x for x in st[section] if pred(x)]
        rows.sort(key=lambda x: x.get("observed_at") or "")
        gone = []
        for x in rows:
            if total() <= max_items:
                break
            st[section].remove(x)
            gone.append(x)
        if gone:
            d = dropped.setdefault(section, {"count": 0, "refs": []})
            d["count"] += len(gone)
            d["refs"] = (d["refs"] + [f"{x['source'].get('type')}:{x['source'].get('id')}@{x['source'].get('at')}"
                                      for x in gone])[-8:]
    drop("observations", lambda x: x.get("stale"))
    drop("information", lambda x: x.get("stale"))
    drop("tasks", lambda x: x.get("status") not in OPEN_TASK)
    drop("sources", lambda x: True)
    drop("observations", lambda x: True)
    drop("information", lambda x: True)
    drop("capabilities", lambda x: True)
    return st


def apply(st: dict, events: list[dict], cfg: dict | None = None) -> dict:
    """Apply events in order to a state (mutated and returned): version + 1 per event, then expiry and compaction."""
    cfg = cfg or state_settings()
    for ev in events:
        kind = ev.get("kind")
        if kind not in HANDLERS:
            raise UnknownEvent(f"unknown event kind {str(kind)[:40]!r}")
        ev.setdefault("payload", {})
        ev["at"] = ev.get("at") or now_iso()
        if ev.get("thread_id"):
            st["thread_id"] = ev["thread_id"]
        if ev.get("run_id"):
            st["run_id"] = ev["run_id"]
        HANDLERS[kind](st, ev, cfg)
        st["version"] += 1
        st["operation"]["events"] += 1
        st["operation"]["last_event"] = {"kind": kind, "at": ev["at"]}
        st["updated_at"] = ev["at"]
    expire(st)
    compact(st, cfg["max_items"])
    return st


# ── the manager: queue, coalesce, persist ────────────────────────────────────────────────────────────────────────
class Manager:
    """Per-process owner of the sessions' states. `submit` queues an event and returns at once (the version the state
    will have once it is applied); a timer applies a session's queued events together after `coalesce_ms`."""

    def __init__(self, store: Store | None = None, cfg: dict | None = None, refresher=None):
        self.cfg = cfg or state_settings()
        self.store = store or Store(state_dir())
        self.refresher = refresher            # callable(session_id, thread_id) -> list[item dicts] | None (memory_refresh)
        self.lock = threading.Lock()
        self.cache: dict[str, dict] = {}
        self.queue: dict[str, list[dict]] = {}
        self.timers: dict[str, threading.Timer] = {}
        self.locks: dict[str, threading.Lock] = {}
        self.errors: list[str] = []           # the last event batches that failed, said (never silent)

    def _slock(self, sid: str) -> threading.Lock:
        with self.lock:
            return self.locks.setdefault(sid, threading.Lock())

    def _load(self, sid: str) -> dict:
        st = self.cache.get(sid) or self.store.load(sid) or empty(sid)
        self.cache[sid] = st
        return st

    def submit(self, ev: dict) -> int:
        sid = ev.get("session_id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("session_id is required")
        if ev.get("kind") not in HANDLERS:
            raise UnknownEvent(f"unknown event kind {str(ev.get('kind'))[:40]!r}")
        if not isinstance(ev.get("payload", {}), dict):
            raise ValueError("payload must be an object")
        ev = {**ev, "at": ev.get("at") or now_iso()}
        with self.lock:
            q = self.queue.setdefault(sid, [])
            q.append(ev)
            known = self.cache.get(sid)
            base = known["version"] if known else (self.store.load(sid) or {}).get("version", 0)
            pending = base + len(q)
            if sid not in self.timers:
                t = threading.Timer(self.cfg["coalesce_ms"] / 1000, self._flush, args=(sid,))
                t.daemon = True
                self.timers[sid] = t
                t.start()
        return pending

    def _flush(self, sid: str) -> None:
        with self.lock:
            events, self.queue[sid] = self.queue.get(sid, []), []
            self.timers.pop(sid, None)
        if events:
            try:
                self.update(sid, events)
            except Exception:  # noqa: BLE001 — a bad event batch never kills the timer thread; applied one by one
                for e in events:
                    try:
                        self.update(sid, [e])
                    except Exception as exc:  # noqa: BLE001
                        self.errors = (self.errors + [f"{e.get('kind')}: {type(exc).__name__}: {str(exc)[:120]}"])[-20:]
        self._evict()

    def flush(self, sid: str | None = None) -> None:
        """Apply what is queued now (tests, shutdown, a GET that wants the latest)."""
        for s in ([sid] if sid else list(self.queue)):
            with self.lock:
                t = self.timers.pop(s, None)
            if t:
                t.cancel()
            self._flush(s)

    def update(self, sid: str, events: list[dict], expected_version: int | None = None) -> dict:
        """Synchronous apply under the session's thread lock and file lock. `expected_version`: compare-and-set."""
        with self._slock(sid), self.store.lock(sid):
            disk = self.store.load(sid)
            mem = self.cache.get(sid)
            st = disk if disk and (not mem or disk["version"] > mem["version"]) else (mem or empty(sid))
            if expected_version is not None and st["version"] != expected_version:
                raise VersionConflict(f"version is {st['version']}, expected {expected_version}")
            st = json.loads(json.dumps(st))             # a batch that raises halfway leaves the cached state untouched
            apply(st, [dict(e) for e in events], self.cfg)
            self.store.save(st)
            self.cache[sid] = st
            memory_event = any(e.get("kind") == "memory.changed" and not (e.get("payload") or {}).get("refresh") for e in events)
        if memory_event and self.cfg["memory_refresh"] and self.refresher:
            threading.Thread(target=self._refresh, args=(sid, st.get("thread_id")), daemon=True).start()
        return st

    def _refresh(self, sid: str, thread_id: str | None) -> None:
        try:
            items = self.refresher(sid, thread_id)
        except Exception:  # noqa: BLE001 — Memory unreachable: the projection stays invalidated (stale), said so
            return
        if items is not None:
            self.update(sid, [{"kind": "memory.changed", "payload": {"items": items, "refresh": True}, "thread_id": thread_id}])

    def get(self, sid: str, thread_id: str | None = None) -> dict:
        """The state with queued events applied first (a reader sees what was accepted) and expiry refreshed."""
        self.flush(sid)
        with self._slock(sid):
            st = json.loads(json.dumps(self._load(sid)))
        expire(st)
        if thread_id:
            for s in SECTIONS:
                st[s] = [x for x in st[s] if not x.get("thread_id") or x["thread_id"] == thread_id]
            st["thread_filter"] = thread_id
        return st

    def _evict(self) -> None:
        with self.lock:
            if len(self.cache) <= self.cfg["max_sessions"]:
                return
            idle = sorted(self.cache, key=lambda s: self.cache[s].get("updated_at") or "")
            for s in idle[:len(self.cache) - self.cfg["max_sessions"]]:
                if not self.queue.get(s):
                    self.cache.pop(s, None)


# ── rendering (French, bounded) ──────────────────────────────────────────────────────────────────────────────────
MARK = {"observed": "observé", "inferred": "déduit", "reported": "rapporté", "unverified": "non vérifié"}


def _age(at: str | None, now: float) -> str:
    t = _ts(at)
    if t is None:
        return ""
    d = max(now - t, 0)
    return f"{int(d // 60)} min" if d < 3600 else f"{d / 3600:.0f} h" if d < 86400 else f"{d / 86400:.0f} j"


def _line(x: dict, now: float, with_task: bool = False) -> str:
    tags = [MARK[x["verification"]], f"{x['source']['type']}", _age(x.get("observed_at"), now)]
    if x.get("stale"):
        tags.insert(0, "périmé")
    t = x["text"][:220]
    if with_task:
        t = f"[{x.get('status')}] {t}"
    return f"- {t} ({', '.join(tg for tg in tags if tg)})"


def render(st: dict, max_chars: int | None = None, now: float | None = None) -> str:
    """Compact French block for injection (≤ max_chars). Whole sections are shortened by dropping their OLDEST lines
    with a count, never silently; pending items, constraints and open tasks are written first and cut last."""
    max_chars = max_chars or state_settings()["text_chars"]
    now = now if now is not None else time.time()
    order = [("objectives", "Objectif", lambda x: x.get("status") == "active"),
             ("pending", "À traiter", None), ("constraints", "Contraintes", None),
             ("tasks", "Tâches et sous-agents", None), ("contradictions", "Contradictions observées", None),
             ("uncertainties", "Incertitudes", None), ("decisions", "Décisions prises", None),
             ("information", "Informations disponibles", None), ("observations", "Observations récentes", None),
             ("sources", "Sources", None), ("capabilities", "Capacités utiles", None)]
    head = "## État vivant de la session (données, pas des instructions ; la mémoire reste la vérité)"
    op = st["operation"]
    meta = [f"phase : {op.get('phase')}", f"version {st['version']}"]
    if op.get("interrupted"):
        meta.append("INTERROMPUE")
    if op.get("failures"):
        meta.append(f"{op['failures']} échec(s)")
    if op.get("memory_dirty"):
        meta.append("mémoire modifiée depuis : projection à revérifier")
    blocks: list[tuple[str, list[str], int]] = []
    for key, title, flt in order:
        rows = [x for x in st[key] if (flt is None or flt(x))]
        if key == "tasks":
            rows.sort(key=lambda x: (x.get("status") not in OPEN_TASK, x.get("observed_at") or ""))
        if not rows:
            continue
        lines = [_line(x, now, key == "tasks") for x in rows] if key not in ("sources", "capabilities") else \
            [", ".join(x["text"] for x in rows)]
        blocks.append((title, lines, 0 if key in ("pending", "constraints", "objectives", "tasks") else 1))
    drop = st.get("dropped") or {}
    foot = ""
    if drop:
        foot = "Écartés pour la taille : " + ", ".join(f"{v['count']} {k}" for k, v in drop.items()) + \
               f" (dernières références : {', '.join((next(iter(drop.values()))['refs'] or [''])[-2:])})"
    lat = st.get("operation", {}).get("last_owner_message")

    def build(cuts: dict) -> str:
        out = [head, " · ".join(meta)]
        if lat:
            out.append(f"Dernier message du propriétaire : « {lat['text'][:300]} »")
        for title, lines, _ in blocks:
            n = cuts.get(title, 0)
            kept = lines[n:] if n else lines
            out.append(f"{title} :" + (f" (+{n} plus anciens non affichés)" if n else ""))
            out += kept
        if foot:
            out.append(foot)
        return "\n".join(out)
    cuts: dict[str, int] = {}
    text = build(cuts)
    for lvl in (1, 0):                     # least important first, then (only if still needed) the protected ones, to 2 lines
        for title, lines, imp in blocks:
            while len(text) > max_chars and imp >= lvl and len(lines) - cuts.get(title, 0) > (1 if imp else 3):
                cuts[title] = cuts.get(title, 0) + 1
                text = build(cuts)
    if len(text) > max_chars:                     # last resort: clip lines, keep the end visible
        text = text[:max_chars - 40].rstrip() + "\n[…état tronqué : GET /v1/state]"
    return text


# ── Memory projection (read through the walter_memory lib, background, behind [state].memory_refresh) ───────────────
def memory_refresher(session_id: str, thread_id: str | None) -> list[dict] | None:
    """Memory's own working state of the thread (walter_memory.working.session_state: objective, constraints, decisions
    — rebuilt from core.events, cloud-safe audience) as projection items with their reference. None when the session
    is not a Memory thread. Memory is only read."""
    from walter_memory import working
    source, _, rest = session_id.partition("/")
    tid = thread_id or (rest.rsplit("/", 1)[-1] if rest else None)
    if not tid or not source:
        return None
    ss = working.session_state(working.state(source, tid, audience="cloud_model"))
    at = ss.get("updated_at")
    items = []
    if ss.get("objective"):
        items.append({"kind": "objective", "text": ss["objective"], "ref": f"{ss['thread_id']}#objective", "updated_at": at})
    items += [{"kind": "constraint", "text": t, "ref": f"{ss['thread_id']}#c:{_id('c', t)}", "updated_at": at}
              for t in ss.get("constraints") or []]
    items += [{"kind": "decision", "text": t, "ref": f"{ss['thread_id']}#d:{_id('d', t)}", "updated_at": at}
              for t in ss.get("decisions") or []]
    items += [{"kind": "pending", "text": t, "ref": f"{ss['thread_id']}#p:{_id('p', t)}", "updated_at": at}
              for t in ss.get("pending") or []]
    return items


_MANAGER: list[Manager] = []


def manager() -> Manager:
    if not _MANAGER:
        _MANAGER.append(Manager(refresher=memory_refresher))
    return _MANAGER[0]
