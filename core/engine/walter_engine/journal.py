"""Walter Engine — the session journal (2026-11-17).

One append-only JSONL file per session (`<state>/sessions/<id>.jsonl`): a header line, then events
`{type, seq, time, data}` in the vocabulary DSH used (turn/start, user/message, assistant/message, tool/call,
tool/result, turn/end, compaction/window…), so walter_logs reads it the same way and a client follows a session by
`seq`. The journal is the truth: what the model sees (the surface) is derived from it — after a compaction, the
window's record plus the originals from the cut on — and a turn's result, its stream and its resumption after a
restart are computed from it the same way live and after a crash. A session imported from DSH keeps its seq numbers
(clients resume at the seq they had).

One writer per session: an in-process lock and an exclusive file lock (a second engine on the same state cannot
interleave writes).
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

MESSAGE_TYPES = ("user/message", "assistant/message", "tool/result")


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return str(uuid.uuid4())



def _utf8(v):
    """A value whose strings are all valid UTF-8: surrogate-escaped bytes become their `\\xNN` text."""
    if isinstance(v, str):
        try:
            v.encode("utf-8")
            return v
        except UnicodeEncodeError:
            return v.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    if isinstance(v, dict):
        return {_utf8(k): _utf8(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_utf8(x) for x in v]
    return v

class Session:
    """A session's journal: header + events, appended under lock, readable at any time."""

    def __init__(self, path: Path, header: dict, events: list[dict]):
        self.path = path
        self.header = header
        self.events = events
        self.lock = threading.RLock()
        self._fh = None
        self.listeners: set = set()        # callables(event) for live followers (SSE, waits)

    # ── identity ──
    @property
    def id(self) -> str:
        return self.header["id"]

    @property
    def seq(self) -> int:
        # an imported session continues after the source's last seq (a client may have seen events not taken over)
        return max(self.events[-1]["seq"] if self.events else 0, int(self.header.get("seq_base", 0)))

    def _open(self):
        if self._fh is None:
            self._fh = open(self.path, "a", encoding="utf-8")   # noqa: SIM115
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._fh.close()
                self._fh = None
                raise RuntimeError(f"session {self.id} is written by another engine process") from None
        return self._fh

    def append(self, type_: str, data: dict | None = None, *, sync: bool = False) -> dict:
        with self.lock:
            ev = {"type": type_, "seq": self.seq + 1, "time": now_ms(), "data": data or {}}
            line = json.dumps(ev, ensure_ascii=False)
            try:
                line.encode("utf-8")
            except UnicodeEncodeError:            # a file name or output that is not UTF-8 (surrogate-escaped bytes):
                ev = _utf8(ev)                    # the stray bytes are written as text (\xd0), never a lost event
                line = json.dumps(ev, ensure_ascii=False)
            fh = self._open()
            fh.write(line + "\n")
            fh.flush()
            if sync:
                os.fsync(fh.fileno())
            self.events.append(ev)
        for listener in list(self.listeners):
            try:
                listener(ev)
            except Exception:  # noqa: BLE001 — a follower never breaks the writer
                pass
        return ev

    def sync(self) -> None:
        with self.lock:
            if self._fh is not None:
                self._fh.flush()
                os.fsync(self._fh.fileno())

    def close(self) -> None:
        with self.lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None

    def since(self, seq: int) -> list[dict]:
        with self.lock:
            return [e for e in self.events if e["seq"] > seq]

    # ── derived views ──
    def title(self) -> str | None:
        for e in reversed(self.events):
            if e["type"] == "session/title":
                return e["data"].get("title")
        return self.header.get("title")

    def turns(self) -> int:
        return sum(1 for e in self.events if e["type"] == "turn/start")

    def open_turn(self) -> dict | None:
        """The turn/start without its turn/end (a turn running, or cut by a crash)."""
        open_ = None
        for e in self.events:
            if e["type"] == "turn/start":
                open_ = e
            elif e["type"] == "turn/end" and open_ and e["data"].get("turn") == open_["data"].get("turn"):
                open_ = None
        return open_

    def pending_calls(self) -> list[dict]:
        """tool/call events with no tool/result (in flight when the engine stopped)."""
        done = {e["data"].get("callId") for e in self.events if e["type"] == "tool/result"}
        return [e for e in self.events if e["type"] == "tool/call" and e["data"].get("callId") not in done]

    def last_window(self) -> dict | None:
        for e in reversed(self.events):
            if e["type"] == "compaction/window":
                return e
        return None


def message_of(ev: dict) -> dict | None:
    """One journal event → one chat message (OpenAI shape) or None."""
    d = ev.get("data") or {}
    t = ev.get("type")
    if t == "user/message":
        m = {"role": "user", "content": d.get("text") or ""}
        if d.get("images"):
            m["_images"] = d["images"]          # [{path, mime}]: the engine inlines them for the live turn only
        return m
    if t == "assistant/message":
        m: dict[str, Any] = {"role": "assistant", "content": d.get("text") or None}
        calls = d.get("tool_calls") or []
        if calls:
            m["tool_calls"] = [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": c.get("arguments") or "{}"}} for c in calls]
        if m["content"] is None and not calls:
            m["content"] = ""
        return m
    if t == "tool/result":
        return {"role": "tool", "tool_call_id": d.get("callId"), "content": d.get("content") or ""}
    return None


def surface(session: Session, *, prune=None) -> list[tuple[int, dict]]:
    """(seq, message) pairs the model sees: the last window's record, then every message from its cut on.
    `prune(event) -> str` may shorten a tool result for the model (the journal keeps the original)."""
    with session.lock:
        events = list(session.events)
    window = None
    for e in reversed(events):
        if e["type"] == "compaction/window":
            window = e
            break
    out: list[tuple[int, dict]] = []
    cut = -1
    if window:
        cut = int(window["data"].get("cut_seq", -1))
        out.append((window["seq"], {"role": "user", "content": window["data"].get("content") or ""}))
    for e in events:
        if e["type"] not in MESSAGE_TYPES or e["seq"] < cut or (e.get("data") or {}).get("nested"):
            continue                          # nested = a call made from Python (journaled, not a model message)
        m = message_of(e)
        if m is None:
            continue
        if e["type"] == "tool/result" and prune is not None:
            m["content"] = prune(e)
        out.append((e["seq"], m))
    return _paired(out)


def _paired(items: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """Tool pairing the providers require: every assistant tool call answered right after it, no orphan result.
    A cut that would split a pair drops the orphan side; a call never answered gets an explicit unknown result."""
    out: list[tuple[int, dict]] = []
    i = 0
    while i < len(items):
        seq, m = items[i]
        if m["role"] == "tool":            # orphan result (its call is before the cut)
            i += 1
            continue
        out.append((seq, m))
        i += 1
        if m["role"] == "assistant" and m.get("tool_calls"):
            want = [c["id"] for c in m["tool_calls"]]
            got: dict[str, tuple[int, dict]] = {}
            others: list[tuple[int, dict]] = []
            while i < len(items) and (items[i][1]["role"] == "tool" or (len(got) < len(want) and items[i][1]["role"] == "user")):
                s2, m2 = items[i]
                if m2["role"] == "tool" and m2.get("tool_call_id") in want:
                    got[m2["tool_call_id"]] = (s2, m2)
                elif m2["role"] == "user":
                    others.append((s2, m2))   # a steer that arrived while tools ran: after the results
                i += 1
            for cid in want:
                out.append(got.get(cid) or (seq, {"role": "tool", "tool_call_id": cid,
                                                  "content": "[résultat inconnu : l'appel n'a pas rendu de résultat]"}))
            out.extend(others)
    return out


class Store:
    """All sessions of the engine (loaded lazily, kept in memory while the engine runs)."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def path(self, sid: str) -> Path:
        if not sid or "/" in sid or sid.startswith("."):
            raise ValueError("invalid session id")
        return self.root / f"{sid}.jsonl"

    def exists(self, sid: str) -> bool:
        return sid in self.sessions or self.path(sid).exists()

    def create(self, *, cwd: str, depth: int = 0, parent: str | None = None, origin: str = "owner",
               door: str | None = None, sid: str | None = None, extra: dict | None = None,
               events: list[dict] | None = None, seq_base: int = 0) -> Session:
        sid = sid or new_id()
        with self.lock:
            p = self.path(sid)
            if p.exists():
                raise FileExistsError(sid)
            header = {"type": "session", "version": 1, "engine": "walter", "id": sid, "created_at": now_ms(),
                      "cwd": cwd, "depth": depth, "parent": parent, "origin": origin, "door": door,
                      **({"seq_base": seq_base} if seq_base else {}), **(extra or {})}
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(header, ensure_ascii=False) + "\n")
                for ev in events or []:
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(p, 0o600)
            s = Session(p, header, list(events or []))
            self.sessions[sid] = s
            return s

    def get(self, sid: str) -> Session:
        with self.lock:
            s = self.sessions.get(sid)
            if s is not None:
                return s
            p = self.path(sid)
            if not p.exists():
                raise KeyError(sid)
            header, events = None, []
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue          # a torn last line (crash mid-write): skipped, never fatal
                    if header is None:
                        header = obj
                    else:
                        events.append(obj)
            if not header or header.get("type") != "session":
                raise ValueError(f"session {sid}: no header")
            with open(p, "rb") as fh:          # a torn last line: the next event starts on its own line
                fh.seek(max(0, p.stat().st_size - 1))
                torn = fh.read(1) not in (b"\n", b"")
            if torn:
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write("\n")
            s = Session(p, header, events)
            self.sessions[sid] = s
            return s

    def all_ids(self) -> Iterator[str]:
        for p in sorted(self.root.glob("*.jsonl")):
            yield p.stem
