"""walter-logs (2026-10-04): raw, append-only session log of every agent runtime → walter_logs.* in Postgres.

What the agents DID, in order, whatever the runtime: user/message, assistant/reasoning, assistant/message,
tool/call (full arguments), tool/result (full output), model/selection, compaction/summary, system/message...
(DeepSeek Harness session-log vocabulary). Readers (pure: one source row/line → events) for Hermes (every profile's
state.db, read-only), Claude Code and Codex (JSONL transcripts) and DSH (zstd session logs); incremental per source,
idempotent (session_id, source_ref). Triggered by file changes (connectors/walter_logs.py watch), not by a timer.

Storage rules: secrets are masked BEFORE storage (mask()); each event gets a privacy class from the same policies as
core.events (privacy.classify on detected categories; Hermes profile `wild` = local_only). Agents read through
search()/timeline()/get() with max_privacy: cloud agents see cloud_allowed as is, redacted_cloud pseudonymised,
never local_only.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import ingestion, privacy

CONNECTOR = "walter_logs"
HERMES_HOME = Path("/root/.hermes")
CLAUDE_DIR = Path("/root/.claude/projects")
CODEX_DIR = Path("/root/.codex/sessions")
DSH_DIR = Path("/opt/dsh/home/sessions")
PROFILE_PRIVACY = {"wild": "local_only"}          # macOS app, uncensored: never leaves the VM
DETECT_CHARS = 50_000                               # privacy detectors read the head of very long outputs
HERMES_BATCH = 5_000

# ───────────────────────── secrets: masked before storage ─────────────────────────
_EXTRA_SECRETS = [
    ("env_secret", re.compile(r"(?i)(?<![«:\w])([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|ACCESS_KEY)[A-Z0-9_]*)"
                              r"(\s*[=:]\s*[\"']?)((?!«)[^\s\"'`,;«»]{8,})")),
    ("json_secret", re.compile(r"(?i)(\"(?:api_?key|access_?token|refresh_?token|token|secret|client_secret|password)\"\s*:\s*\")"
                               r"((?!«)[^\"]{8,})(\")")),
    ("bearer", re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9._~+/=-]{20,})")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("url_cred", re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]{4,})(@)")),
]


def mask(text: str | None) -> str | None:
    """Replace credentials by «secret:<kind>» (names of variables kept, values gone). Idempotent."""
    if not text:
        return text
    for name, rx in privacy.SECRET_PATTERNS:
        if name in ("api_key", "private_key"):
            text = rx.sub(f"«secret:{name}»", text)
        elif name == "password_stmt":
            text = rx.sub(lambda m: re.sub(r"\S{4,}$", "«secret:password»", m.group()), text)
        elif name in ("otp", "cvv"):
            text = rx.sub(lambda m: re.sub(r"\d{3,8}$", "«secret:code»", m.group()), text)
    text = _EXTRA_SECRETS[0][1].sub(lambda m: m.group(1) + m.group(2) + "«secret»", text)
    text = _EXTRA_SECRETS[1][1].sub(lambda m: m.group(1) + "«secret»" + m.group(3), text)
    text = _EXTRA_SECRETS[2][1].sub(lambda m: m.group(1) + " «secret»", text)
    text = _EXTRA_SECRETS[3][1].sub("«secret:jwt»", text)
    text = _EXTRA_SECRETS[4][1].sub(lambda m: m.group(1) + "«secret»" + m.group(3), text)
    return text


_MASKED = re.compile(r"«secret[^»]*»")


def classify(conn, runtime: str, base: str, text: str | None) -> str:
    # masked placeholders are not secrets any more ("password: «secret:password»" must not re-trigger the detector)
    cats = {c for c, _ in privacy.detect(_MASKED.sub("", text[:DETECT_CHARS]))} if text else set()
    cls, _ = privacy.classify(conn, {"source": runtime, "categories": cats})
    return privacy.strictest(base, cls)


def _ts(v) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _text(content) -> str:
    """Text of a message content (string or list of blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") in ("text", "input_text", "output_text") or ("text" in b and isinstance(b["text"], str)):
                    parts.append(b.get("text") or "")
                elif b.get("type") in ("image", "input_image", "image_url"):
                    parts.append("[image]")
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return _text(content.get("content")) or content.get("text") or json.dumps(content, ensure_ascii=False)
    return str(content)


def _json(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


# ───────────────────────── writer ─────────────────────────
class Writer:
    """Buffers sessions and events for one transaction; assigns per-session seq; idempotent on source_ref."""

    def __init__(self, conn):
        self.conn = conn
        self.sess: dict[str, dict] = {}
        self.rows: list[tuple] = []
        self.calls: dict[str, str] = {}
        self.dirty: set[str] = set()
        self.inserted = 0

    def session(self, session_id: str, *, runtime: str, native_id: str, privacy_class: str = "cloud_allowed",
                **fields) -> dict:
        """Upsert a session (non-null fields win) and return its live counters."""
        meta = fields.pop("meta", None) or {}
        cols = ["profile", "platform", "title", "model", "cwd", "parent_session_id", "started_at", "ended_at"]
        vals = [fields.get(c) for c in cols]
        row = self.conn.execute(
            f"""insert into walter_logs.sessions (session_id, runtime, native_id, privacy_class, meta, {", ".join(cols)})
                values (%s, %s, %s, %s, %s::jsonb, {", ".join(["%s"] * len(cols))})
                on conflict (session_id) do update set
                  {", ".join(f"{c} = coalesce(excluded.{c}, walter_logs.sessions.{c})" for c in cols)},
                  meta = walter_logs.sessions.meta || excluded.meta, updated_at = now()
                returning last_seq, turns, privacy_class""",
            (session_id, runtime, native_id, privacy_class, json.dumps(meta, default=str), *vals)).fetchone()
        if session_id not in self.sess:
            self.sess[session_id] = {"seq": row["last_seq"], "turns": row["turns"], "privacy": row["privacy_class"],
                                     "runtime": runtime, "last": None}
        return self.sess[session_id]

    def add(self, session_id: str, type_: str, occurred_at, source_ref: str, *, text: str | None = None,
            call_id: str | None = None, tool: str | None = None, model: str | None = None, status: str | None = None,
            data: dict | None = None, human: bool = False) -> None:
        s = self.sess[session_id]
        if human:
            s["turns"] += 1
        s["seq"] += 1
        text = mask(text.replace("\x00", "")) if text else None
        cls = classify(self.conn, s["runtime"], s["privacy"], text)
        occurred_at = occurred_at or s["last"] or datetime.now(timezone.utc)
        s["last"] = occurred_at
        self.dirty.add(session_id)
        if type_ == "tool/call" and call_id and tool:
            self.calls[call_id] = tool
        self.rows.append((session_id, s["seq"], type_, occurred_at, s["turns"] or None, call_id, tool, model, status,
                          text, json.dumps(data or {}, default=str, ensure_ascii=False).replace("\\u0000", ""), len(text or ""), cls, source_ref))
        if len(self.rows) >= 2000:
            self.flush()

    def flush(self) -> int:
        if self.rows:
            with self.conn.cursor() as cur:
                cur.executemany("""insert into walter_logs.events (session_id, seq, type, occurred_at, turn, call_id, tool,
                                       model, status, text, data, chars, privacy_class, source_ref)
                                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) on conflict do nothing""",
                                self.rows)
                self.inserted += max(cur.rowcount, 0)
            self.rows = []
        for sid in self.dirty:
            s = self.sess[sid]
            self.conn.execute("""update walter_logs.sessions set last_seq = greatest(last_seq, %s), turns = greatest(turns, %s),
                                   last_event_at = greatest(last_event_at, %s), updated_at = now() where session_id = %s""",
                              (s["seq"], s["turns"], s["last"], sid))
        self.dirty.clear()
        return self.inserted

    def tool_of(self, call_id: str | None) -> str | None:
        if not call_id:
            return None
        if call_id in self.calls:
            return self.calls[call_id]
        row = self.conn.execute("""select tool from walter_logs.events where call_id = %s and type = 'tool/call'
                                   order by occurred_at desc limit 1""", (call_id,)).fetchone()
        return row["tool"] if row else None


# ───────────────────────── Hermes (state.db of every profile, read-only) ─────────────────────────
def hermes_dbs() -> dict[str, Path]:
    dbs = {"main": HERMES_HOME / "state.db"}
    for p in sorted((HERMES_HOME / "profiles").glob("*/state.db")):
        dbs[p.parent.name] = p
    return {k: v for k, v in dbs.items() if v.exists()}


def _hermes_status(content: str | None) -> str | None:
    if content is None:
        return None
    head = content[:400].lower()
    return "error" if ('"error"' in head or '"success": false' in head or '"status": "error"' in head) else "ok"


def _hermes_reasoning(m) -> str:
    for col in ("reasoning", "reasoning_content"):
        if m[col]:
            return m[col]
    if m["reasoning_details"]:
        try:
            det = json.loads(m["reasoning_details"])
            return "\n".join(d.get("text") or d.get("summary") or "" for d in det if isinstance(d, dict)).strip()
        except (ValueError, TypeError):
            return ""
    return ""


def sync_hermes(conn, profile: str, path: Path, max_rows: int = 50_000) -> dict:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    stream = f"hermes:{profile}"
    cur = ingestion.get_checkpoint(CONNECTOR, stream)
    last_id, activity = int(cur.get("last_id", 0)), float(cur.get("activity", 0))
    rows = db.execute("""select id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count,
                                finish_reason, reasoning, reasoning_content, reasoning_details,
                                length(codex_reasoning_items) enc, display_kind, _compressed_summary
                         from messages where id > ? order by id limit ?""", (last_id, max_rows)).fetchall()
    sids = {r["session_id"] for r in rows}
    srows = db.execute("""select * from sessions where coalesce(last_activity_at, ended_at, started_at) > ?""",
                       (activity,)).fetchall()
    srows += [r for r in db.execute(f"select * from sessions where id in ({','.join('?' * len(sids))})", list(sids))
              if r["id"] not in {s["id"] for s in srows}] if sids else []
    w = Writer(conn)
    pref = f"hermes/{profile}/"
    base_cls = PROFILE_PRIVACY.get(profile, "cloud_allowed")
    top = activity
    for s in srows:
        keys = s.keys()
        g = (lambda k: s[k] if k in keys else None)
        w.session(pref + s["id"], runtime="hermes", native_id=s["id"], privacy_class=base_cls, profile=profile,
                  platform=s["source"], title=g("title"), model=s["model"], cwd=g("cwd"),
                  parent_session_id=pref + s["parent_session_id"] if s["parent_session_id"] else None,
                  started_at=_ts(s["started_at"]), ended_at=_ts(s["ended_at"]),
                  meta={k: g(k) for k in ("end_reason", "message_count", "tool_call_count", "api_call_count", "input_tokens",
                                          "output_tokens", "cache_read_tokens", "reasoning_tokens", "billing_provider",
                                          "estimated_cost_usd", "actual_cost_usd", "system_prompt_hash", "chat_type")
                        if g(k) not in (None, "", 0)})
        top = max(top, float(g("last_activity_at") or s["ended_at"] or s["started_at"] or 0))
    models = {s["id"]: s["model"] for s in srows}
    for m in rows:
        sid, ts, ref = pref + m["session_id"], _ts(m["timestamp"]), f"m{m['id']}"
        if sid not in w.sess:     # session row missing (deleted/rewound): keep the events anyway
            w.session(sid, runtime="hermes", native_id=m["session_id"], privacy_class=base_cls, profile=profile)
        model = models.get(m["session_id"])
        role, content = m["role"], m["content"]
        if role == "user":
            injected = bool(m["display_kind"]) or m["_compressed_summary"] in (1, "1")
            if (content or "").startswith("[CONTEXT COMPACTION]") or m["_compressed_summary"] in (1, "1"):
                w.add(sid, "compaction/summary", ts, ref, text=content)
            else:
                w.add(sid, "user/message", ts, ref, text=content, human=not injected,
                      data={"injected": injected, "display_kind": m["display_kind"]} if injected else None)
        elif role == "assistant":
            reasoning = _hermes_reasoning(m)
            if reasoning:
                w.add(sid, "assistant/reasoning", ts, ref + ":reasoning", text=reasoning, model=model)
            elif m["enc"]:
                w.add(sid, "assistant/reasoning", ts, ref + ":reasoning", model=model,
                      data={"encrypted": True, "bytes": m["enc"]})
            if content and content.strip():
                w.add(sid, "assistant/message", ts, ref, text=content, model=model,
                      data={"finish_reason": m["finish_reason"], "token_count": m["token_count"]})
            try:
                calls = json.loads(m["tool_calls"]) if m["tool_calls"] else []
            except ValueError:
                calls = []
            for i, c in enumerate(calls if isinstance(calls, list) else []):
                fn = c.get("function") or {}
                w.add(sid, "tool/call", ts, f"{ref}:call:{c.get('id') or i}", call_id=c.get("id"),
                      tool=fn.get("name") or c.get("name"), text=_json(fn.get("arguments") or c.get("arguments")), model=model)
        elif role == "tool":
            w.add(sid, "tool/result", ts, ref, call_id=m["tool_call_id"], text=content,
                  tool=m["tool_name"] or w.tool_of(m["tool_call_id"]), status=_hermes_status(content))
        else:   # system, session_meta
            w.add(sid, "system/message", ts, ref, text=content, data={"role": role})
    n = w.flush()
    ingestion.set_checkpoint(CONNECTOR, stream, {"last_id": rows[-1]["id"] if rows else last_id, "activity": top},
                             last_item_at=_ts(rows[-1]["timestamp"]) if rows else None, conn=conn)
    db.close()
    return {"rows": len(rows), "inserted": n, "more": len(rows) == max_rows}


# ───────────────────────── JSONL transcripts (Claude Code, Codex, DSH) ─────────────────────────
CLAUDE_ATTACH_TEXT = {"hook_additional_context": "content", "queued_command": "prompt", "edited_text_file": "filename",
                      "model": "text", "silent_turn_reminder": "text"}
CLAUDE_INJECTED = ("<local-command-", "<command-name>", "<command-message>", "<task-notification>", "Caveat: The messages",
                   "<system-reminder>")


def parse_claude(w: Writer, d: dict, ref: str, st: dict) -> None:
    kind, sid0 = d.get("type"), d.get("sessionId") or st.get("sid")
    if kind == "custom-title" and d.get("customTitle"):
        st["title"] = d["customTitle"]
        if st.get("sid"):
            w.session(f"claude_code/vm/{st['sid']}", runtime="claude_code", native_id=st["sid"], title=d["customTitle"])
        return
    if not sid0 or kind not in ("user", "assistant", "attachment", "system"):
        return
    st["sid"] = sid0
    sidechain = d.get("isSidechain") and d.get("agentId")
    native = f"{sid0}:{d['agentId']}" if sidechain else sid0
    sid = f"claude_code/vm/{native}"
    ts = _ts(d.get("timestamp"))
    if sid not in w.sess:
        w.session(sid, runtime="claude_code", native_id=native, platform=d.get("entrypoint"), cwd=d.get("cwd"),
                  title=st.get("title"), started_at=ts,
                  parent_session_id=f"claude_code/vm/{sid0}" if sidechain else None,
                  meta={"version": d.get("version"), "git_branch": d.get("gitBranch")})
    msg = d.get("message") or {}
    content = msg.get("content")
    if kind == "assistant":
        model = msg.get("model")
        if model and model != st.get("model"):
            st["model"] = model
            w.session(sid, runtime="claude_code", native_id=native, model=model)
        data = {"message_id": msg.get("id"), "usage": msg.get("usage"), "stop_reason": msg.get("stop_reason")}
        for i, b in enumerate(content if isinstance(content, list) else [{"type": "text", "text": _text(content)}]):
            t = b.get("type")
            r = f"{ref}:{i}"
            if t == "thinking":
                w.add(sid, "assistant/reasoning", ts, r, text=b.get("thinking") or None, model=model,
                      data=None if b.get("thinking") else {"redacted": True})
            elif t == "redacted_thinking":
                w.add(sid, "assistant/reasoning", ts, r, model=model, data={"redacted": True})
            elif t == "text" and (b.get("text") or "").strip():
                w.add(sid, "assistant/message", ts, r, text=b["text"], model=model, data=data)
            elif t in ("tool_use", "server_tool_use"):
                w.add(sid, "tool/call", ts, r, call_id=b.get("id"), tool=b.get("name"), text=_json(b.get("input")),
                      model=model)
        return
    if kind == "attachment":
        a = d.get("attachment") or {}
        field = CLAUDE_ATTACH_TEXT.get(a.get("type"))
        text = _text(a.get(field)) if field else None
        w.add(sid, "developer/message" if text else "system/context", ts, ref, text=text,
              data={"attachment": a.get("type"), "hook": a.get("hookName"), "chars": len(json.dumps(a, default=str))})
        return
    if kind == "system":
        w.add(sid, "system/message", ts, ref, text=d.get("content") if isinstance(d.get("content"), str) else None,
              data={"subtype": d.get("subtype"), "stop_reason": d.get("stopReason")})
        return
    # user line: tool results and/or a human (or injected) message
    blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
    for i, b in enumerate(blocks):
        if isinstance(b, dict) and b.get("type") == "tool_result":
            w.add(sid, "tool/result", ts, f"{ref}:{i}", call_id=b.get("tool_use_id"), text=_text(b.get("content")),
                  tool=w.tool_of(b.get("tool_use_id")), status="error" if b.get("is_error") else "ok")
    text = _text([b for b in blocks if isinstance(b, dict) and b.get("type") != "tool_result"]).strip()
    if not text:
        return
    if d.get("isCompactSummary"):
        w.add(sid, "compaction/summary", ts, ref, text=text)
        return
    origin = (d.get("origin") or {}).get("kind")
    injected = bool(d.get("isMeta")) or text.startswith(CLAUDE_INJECTED) or bool(origin and origin != "human")
    w.add(sid, "user/message", ts, ref, text=text, human=not injected,
          data={"injected": True, "origin": origin} if injected else None)


def parse_codex(w: Writer, d: dict, ref: str, st: dict) -> None:
    kind, p = d.get("type"), d.get("payload") or {}
    ts = _ts(d.get("timestamp") or p.get("timestamp"))
    if kind == "session_meta":
        st.update(sid=p.get("id"), originator=p.get("originator") or p.get("source"))
        w.session(f"codex/{st['originator'] or 'unknown'}/{st['sid']}", runtime="codex", native_id=st["sid"],
                  profile=st.get("originator"), platform=st.get("originator"), cwd=p.get("cwd"), started_at=ts,
                  meta={"cli_version": p.get("cli_version"), "model_provider": p.get("model_provider")})
        return
    if not st.get("sid"):
        return
    sid = f"codex/{st.get('originator') or 'unknown'}/{st['sid']}"
    if sid not in w.sess:
        w.session(sid, runtime="codex", native_id=st["sid"])
    ptype, model = p.get("type"), st.get("model")
    if kind == "turn_context":
        if p.get("model") != st.get("model"):
            st["model"] = p.get("model")
            w.session(sid, runtime="codex", native_id=st["sid"], model=p.get("model"))
        w.add(sid, "model/selection", ts, ref, model=p.get("model"),
              data={"effort": p.get("effort"), "approval_policy": p.get("approval_policy"), "cwd": p.get("cwd")})
    elif kind == "event_msg" and ptype == "user_message":
        w.add(sid, "user/message", ts, ref, text=p.get("message"), human=True)
    elif kind == "event_msg" and ptype == "agent_message":
        w.add(sid, "assistant/message", ts, ref, text=p.get("message"), model=model)
    elif kind == "event_msg" and ptype in ("agent_reasoning", "agent_reasoning_raw_content"):
        w.add(sid, "assistant/reasoning", ts, ref, text=p.get("text"), model=model)
    elif kind == "event_msg" and ptype == "token_count":
        w.add(sid, "step/end", ts, ref, model=model, data={"usage": p.get("info")})
    elif kind == "response_item" and ptype in ("function_call", "custom_tool_call", "local_shell_call"):
        w.add(sid, "tool/call", ts, ref, call_id=p.get("call_id") or p.get("id"), tool=p.get("name") or ptype,
              text=_json(p.get("arguments") or p.get("input") or p.get("action")), model=model)
    elif kind == "response_item" and ptype in ("function_call_output", "custom_tool_call_output"):
        out = p.get("output")
        failed = isinstance(out, dict) and out.get("success") is False
        w.add(sid, "tool/result", ts, ref, call_id=p.get("call_id"), tool=w.tool_of(p.get("call_id")),
              text=_text(out.get("content") if isinstance(out, dict) else out) or _json(out),
              status="error" if failed else "ok")
    elif kind == "compacted":
        w.add(sid, "compaction/summary", ts, ref, text=p.get("message"))


def parse_dsh(w: Writer, d: dict, ref: str, st: dict) -> None:
    """DSH events are already in this vocabulary: copy type, extract the text, keep small fields."""
    kind, data = d.get("type"), d.get("data") or {}
    if kind == "session":
        st.update(sid=d.get("id"))
        w.session(f"dsh/vm/{st['sid']}", runtime="dsh", native_id=st["sid"], cwd=d.get("cwd"),
                  started_at=_ts(d.get("time") or d.get("createdAt")), meta={"delegation_depth": d.get("delegationDepth")})
        return
    if not st.get("sid") or not kind:
        return
    sid = f"dsh/vm/{st['sid']}"
    if sid not in w.sess:
        w.session(sid, runtime="dsh", native_id=st["sid"])
    ts = _ts(d.get("time") or d.get("createdAt"))
    if kind == "request/context":
        st["model"] = f"{data.get('provider')}/{data.get('model')}"
    msg = data.get("message") or {}
    text = _text(msg.get("content") if msg else data.get("content")) or None
    if kind == "tool/call":
        text = _json(data.get("arguments"))
    human = kind == "user/message" and (data.get("source") or {}).get("kind") == "user"
    w.add(sid, kind, ts, f"seq:{d.get('seq', ref)}", text=text, human=human,
          call_id=data.get("callId") or msg.get("toolCallId"), tool=data.get("name"), model=st.get("model"),
          status=("error" if msg.get("isError") else "ok") if kind == "tool/result" else None,
          data={k: data[k] for k in ("reason", "interrupted", "usage") if k in data})


PARSERS = {"claude": parse_claude, "codex": parse_codex, "dsh": parse_dsh}
ROOTS = {"claude": CLAUDE_DIR, "codex": CODEX_DIR, "dsh": DSH_DIR}


def transcript_files(runtime: str) -> list[Path]:
    root = ROOTS[runtime]
    pattern = {"claude": "**/*.jsonl", "codex": "*/*/*/rollout-*.jsonl", "dsh": "*/session-*/session.v4.jsonl.zstd"}[runtime]
    return sorted(root.glob(pattern)) if root.exists() else []


def runtime_of(path: Path) -> str | None:
    p = str(path.resolve())
    return next((r for r, root in ROOTS.items() if p.startswith(str(root) + "/")), None)


def sync_transcript(conn, runtime: str, path: Path) -> dict:
    from connectors.agent_sessions import read_complete_lines, read_zstd_lines   # shared readers (offsets, zstd)
    stream = f"{runtime}:{path}"
    cur = ingestion.get_checkpoint(CONNECTOR, stream)
    offset, st = int(cur.get("offset", 0)), cur.get("state") or {}
    size = path.stat().st_size
    if runtime == "dsh":
        if size == cur.get("size"):
            return {"rows": 0, "inserted": 0}
        gen = read_zstd_lines(path, offset)
    else:
        if size < offset:
            offset, st = 0, {}
        if size == offset:
            return {"rows": 0, "inserted": 0}
        gen = read_complete_lines(path, offset)
    w, n = Writer(conn), 0
    try:
        while True:
            at, d = next(gen)
            PARSERS[runtime](w, d, f"o{at}", st)
            n += 1
    except StopIteration as stop:
        new_offset = stop.value
    ins = w.flush()
    ingestion.set_checkpoint(CONNECTOR, stream, {"offset": new_offset, "state": st, "size": size}, conn=conn)
    return {"rows": n, "inserted": ins}


# ───────────────────────── reading (agents) ─────────────────────────
def _visible(max_privacy: str) -> list[str]:
    return privacy.allowed_classes(max_privacy)


def _show(text: str | None, cls: str, max_privacy: str, limit: int | None = None) -> str | None:
    if text is None:
        return None
    if cls not in _cloud_view(max_privacy):
        return "[contenu local uniquement]"
    if cls == "redacted_cloud" and max_privacy == "cloud_allowed":
        text = privacy.redact(text)[0]
    if limit and len(text) > limit:
        return text[:limit] + f"… [+{len(text) - limit} car.]"
    return text


def _cloud_view(max_privacy: str) -> list[str]:
    """A cloud agent may see cloud_allowed as is and redacted_cloud pseudonymised."""
    return ["cloud_allowed", "redacted_cloud"] if max_privacy == "cloud_allowed" else _visible(max_privacy)


def resolve_session(conn, ref: str) -> str | None:
    row = conn.execute("""select session_id from walter_logs.sessions
                          where session_id = %s or native_id = %s or session_id like %s
                          order by last_event_at desc nulls last limit 1""", (ref, ref, f"%{ref}%")).fetchone()
    return row["session_id"] if row else None


def search(conn, query: str = "", *, runtime: str | None = None, types: list[str] | None = None, tool: str | None = None,
           session: str | None = None, since: str | None = None, until: str | None = None, limit: int = 20,
           max_privacy: str = "local_only") -> dict:
    where, args = ["e.privacy_class = any(%s)"], [_cloud_view(max_privacy)]
    if runtime:
        where.append("s.runtime = %s"); args.append(runtime)
    if types:
        where.append("e.type = any(%s)"); args.append(types)
    if tool:
        where.append("e.tool ilike %s"); args.append(f"%{tool}%")
    if session:
        sid = resolve_session(conn, session)
        where.append("e.session_id = %s"); args.append(sid)
    if since:
        where.append("e.occurred_at >= %s"); args.append(since)
    if until:
        where.append("e.occurred_at < %s"); args.append(until)
    sel = """select e.session_id, e.seq, e.type, e.occurred_at, e.turn, e.tool, e.model, e.status, e.call_id, e.chars,
                    e.privacy_class, s.runtime, s.profile, s.platform, s.title, s.privacy_class as session_privacy,
                    {snippet} as snippet
             from walter_logs.events e join walter_logs.sessions s using (session_id)"""
    mode = "recent"
    if query.strip():
        q = "websearch_to_tsquery('simple', search.f_unaccent(%s))"
        rows = conn.execute(
            sel.format(snippet=f"ts_headline('simple', left(coalesce(e.text, ''), 20000), {q}, "
                              "'MaxWords=40, MinWords=15, MaxFragments=2, StartSel=**, StopSel=**')")
            + f" where e.tsv @@ {q} and " + " and ".join(where)
            + f" order by ts_rank_cd(e.tsv, {q}) * (1 + 1 / (1 + extract(epoch from now() - e.occurred_at) / 604800)) desc"
            + " limit %s", [query, query, *args, query, limit]).fetchall()
        mode = "fts"
        if not rows:   # paths, error codes, identifiers: exact substring over the last 90 days
            rows = conn.execute(sel.format(snippet="substr(e.text, greatest(strpos(lower(e.text), lower(%s)) - 120, 1), 320)")
                                + " where e.text ilike %s and e.occurred_at > now() - interval '90 days' and "
                                + " and ".join(where) + " order by e.occurred_at desc limit %s",
                                [query, f"%{query}%", *args, limit]).fetchall()
            mode = "substring"
    else:
        rows = conn.execute(sel.format(snippet="left(e.text, 300)") + " where " + " and ".join(where)
                            + " order by e.occurred_at desc limit %s", [*args, limit]).fetchall()
    hidden = 0
    out = []
    for r in rows:
        r = dict(r)
        r["snippet"] = _show(r["snippet"], r["privacy_class"], max_privacy)
        r["title"] = _title(r["title"], r.pop("session_privacy"), max_privacy)
        r["ref"] = f"{r['session_id']}#{r['seq']}"
        out.append(r)
    if max_privacy == "cloud_allowed" and query.strip() and mode == "fts":
        hidden = conn.execute(f"""select count(*) n from walter_logs.events e where e.tsv @@ websearch_to_tsquery('simple',
                                  search.f_unaccent(%s)) and e.privacy_class = 'local_only'""", (query,)).fetchone()["n"]
    return {"mode": mode, "results": out, "hidden_local_only": hidden}


def timeline(conn, session: str, *, around: int | None = None, before: int = 5, after: int = 15,
             types: list[str] | None = None, max_chars: int = 600, max_privacy: str = "local_only") -> dict:
    sid = resolve_session(conn, session)
    if not sid:
        return {"error": f"session inconnue: {session}"}
    s = dict(conn.execute("select * from walter_logs.sessions where session_id = %s", (sid,)).fetchone())
    where, args = ["session_id = %s"], [sid]
    if types:
        where.append("type = any(%s)"); args.append(types)
    else:   # runtime bookkeeping (token reminders, tool listings) only on request
        where.append("type <> 'system/context'")
    if around is not None:
        lo = conn.execute(f"select seq from walter_logs.events where {' and '.join(where)} and seq <= %s order by seq desc "
                          "offset %s limit 1", [*args, around, before]).fetchone()
        where.append("seq >= %s"); args.append(lo["seq"] if lo else 0)
        order, lim = "seq", before + after + 1
    else:
        order, lim = "seq desc", before + after   # no anchor: the latest events
    rows = conn.execute(f"""select seq, type, occurred_at, turn, tool, model, status, call_id, chars, text, privacy_class, data
                            from walter_logs.events where {' and '.join(where)} order by {order} limit %s""",
                        [*args, lim]).fetchall()
    rows = sorted(rows, key=lambda r: r["seq"])
    evs = [{**{k: r[k] for k in ("seq", "type", "occurred_at", "turn", "tool", "model", "status", "call_id", "chars")},
            "text": _show(r["text"], r["privacy_class"], max_privacy, max_chars),
            **({"data": r["data"]} if r["data"] and r["type"] not in ("assistant/message",) else {})} for r in rows]
    s.pop("meta", None)
    s["title"] = _title(s["title"], s["privacy_class"], max_privacy)
    return {"session": s, "events": evs}


def get(conn, session: str, seq: int, max_privacy: str = "local_only") -> dict:
    sid = resolve_session(conn, session)
    r = conn.execute("select * from walter_logs.events where session_id = %s and seq = %s", (sid, seq)).fetchone()
    if not r:
        return {"error": "événement introuvable"}
    r = dict(r)
    r.pop("tsv", None)
    r["text"] = _show(r["text"], r["privacy_class"], max_privacy)
    if r["type"] in ("tool/call", "tool/result") and r["call_id"]:   # the other half of the tool call
        o = conn.execute("""select seq, type, status, chars from walter_logs.events where session_id = %s and call_id = %s
                            and seq <> %s""", (sid, r["call_id"], seq)).fetchall()
        r["linked"] = [dict(x) for x in o]
    return r


def _title(title: str | None, cls: str, max_privacy: str) -> str | None:
    return title if cls in _cloud_view(max_privacy) else ("[session locale]" if title else None)


def sessions(conn, *, runtime: str | None = None, text: str | None = None, since: str | None = None,
             limit: int = 20, max_privacy: str = "local_only") -> list[dict]:
    where, args = ["true"], []
    if max_privacy == "cloud_allowed":
        where.append("privacy_class <> 'local_only'")
    if runtime:
        where.append("runtime = %s"); args.append(runtime)
    if text:
        where.append("(title ilike %s or session_id ilike %s)"); args += [f"%{text}%", f"%{text}%"]
    if since:
        where.append("coalesce(last_event_at, started_at) >= %s"); args.append(since)
    return [{**dict(r), "title": _title(r["title"], r["privacy_class"], max_privacy)} for r in conn.execute(
        f"""select session_id, runtime, profile, platform, title, model, started_at, last_event_at, last_seq as events,
                   turns, privacy_class from walter_logs.sessions where {' and '.join(where)}
            order by coalesce(last_event_at, started_at) desc nulls last limit %s""", [*args, limit])]


def stats(conn) -> dict:
    return {"sessions": [dict(r) for r in conn.execute(
                """select runtime, profile, count(*) sessions, sum(last_seq) events, max(last_event_at) last
                   from walter_logs.sessions group by 1, 2 order by 1, 2""")],
            "types": [dict(r) for r in conn.execute(
                """select type, privacy_class, count(*) n, pg_size_pretty(sum(chars)::bigint) text
                   from walter_logs.events group by 1, 2 order by 3 desc""")]}


def _when(t) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if t else "?"


def render(action: str, res) -> str:
    """Compact text for agents (one line per event, refs reusable with timeline/get)."""
    if isinstance(res, dict) and res.get("error"):
        return res["error"]
    if action == "search":
        lines = [f"{len(res['results'])} résultat(s) ({res['mode']})"
                 + (f", {res['hidden_local_only']} masqué(s) (local uniquement)" if res.get("hidden_local_only") else "")]
        for r in res["results"]:
            who = f"{r['runtime']}{'/' + r['profile'] if r['profile'] else ''}"
            what = r["type"] + (f" {r['tool']}" if r["tool"] else "") + (" ✗" if r["status"] == "error" else "")
            lines.append(f"- [{r['ref']}] {_when(r['occurred_at'])}Z {who} « {(r['title'] or '')[:60]} » · {what}\n"
                         f"    {' '.join((r['snippet'] or '').split())[:400]}")
        return "\n".join(lines)
    if action == "timeline":
        s = res["session"]
        lines = [f"Session {s['session_id']} · {s['runtime']} {s.get('platform') or ''} · « {s.get('title') or ''} » · "
                 f"{s.get('model') or ''} · {_when(s.get('started_at'))}Z → {_when(s.get('last_event_at'))}Z · "
                 f"{s.get('last_seq')} événements"]
        for e in res["events"]:
            head = f"#{e['seq']} {_when(e['occurred_at'])[11:]} {e['type']}" + (f" {e['tool']}" if e["tool"] else "") \
                   + (" ✗" if e["status"] == "error" else "") + (f" [{e['chars']} car.]" if e["chars"] > 600 else "")
            body = (e["text"] or "").strip()
            if not body and e.get("data"):
                body = json.dumps(e["data"], ensure_ascii=False, default=str)[:200]
            lines.append(head + ("\n    " + body.replace("\n", "\n    ") if body else ""))
        return "\n".join(lines)
    if action == "get":
        head = {k: v for k, v in res.items() if k not in ("text",)}
        return json.dumps(head, ensure_ascii=False, default=str, indent=1) + "\n---\n" + (res.get("text") or "")
    return json.dumps(res, ensure_ascii=False, default=str, indent=1)
