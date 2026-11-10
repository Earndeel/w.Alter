"""Walter Telegram — the engine's Telegram door (lot E7, 2026-11-10).

A client of the Engine API and nothing else: it owns no loop, no session store, no model choice. One Telegram chat of
the owner = one engine conversation `telegram/<account>/chat-<id>[-n]` (persistent, `/nouveau` starts the next one).
Messages are submitted with the Telegram message id as idempotency key (a replayed update never runs twice); the
session's events (SSE) drive what the owner sees: « écrit… », the tools at work, the answer, approval buttons, the end
of an interrupted or failed turn. Only the owner's Telegram accounts are served; anything else is ignored and logged.

    walter-telegram [serve]                     the door (service walter-telegram)
    walter-telegram check                       configuration, bot and engine reachable
    walter-telegram send [--plain] [--silent] [--buttons JSON] TEXT|-
                                                one message to the owner through Walter's bot (modules' notices)
Buttons of other modules: `[callbacks]` maps a callback-data prefix to a command; the door runs `<command> <data>`,
which prints {ok, toast, drop}.
Conversational web services (`/gpt …`, lot E6): `[web] list` prints {command: service}; such a command goes to
`[web] run` (JSON spec on stdin: service, message, model from a `[model]` prefix, files, conversation, request_id),
never to an engine turn; the reply comes back as is, produced images/files as Telegram photos/documents.

Settings: `walter instance config core telegram.toml` (instance override of `core/config/telegram.toml`).
State: `@instance/state/core/telegram/state.json` (0600: Telegram offset, conversation numbers, last event seen).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tgformat  # noqa: E402

log = logging.getLogger("walter-telegram")
TG_URL = "https://api.telegram.org/bot{token}/{method}"
TG_FILE = "https://api.telegram.org/file/bot{token}/{path}"


# ── outside world ────────────────────────────────────────────────────────────────────────────────────────────────

class TelegramError(Exception):
    def __init__(self, description: str, code: int = 0, retry_after: int | None = None):
        super().__init__(description)
        self.code, self.retry_after = code, retry_after


class Telegram:
    """Bot API. The token is only ever in the request URL Telegram requires; no URL is logged or raised."""

    def __init__(self, token: str):
        self._token = token

    def call(self, method: str, payload: dict | None = None, timeout: float = 30) -> dict:
        req = urllib.request.Request(TG_URL.format(token=self._token, method=method),
                                     data=json.dumps(payload or {}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed host)
                out = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                out = json.load(e)
            except ValueError:
                raise TelegramError(f"http {e.code}", e.code) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise TelegramError(f"network: {type(e).__name__}") from None
        if not out.get("ok"):
            raise TelegramError(str(out.get("description"))[:200], out.get("error_code") or 0,
                                (out.get("parameters") or {}).get("retry_after"))
        return out["result"]

    def upload(self, method: str, fields: dict, field: str, path: Path, mime: str = "") -> dict:
        """multipart/form-data upload (sendPhoto, sendDocument): one file from disk."""
        boundary = "walter" + os.urandom(12).hex()
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        name = re.sub(r'["\r\n\\]', "_", path.name)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
                     f'Content-Type: {mime or "application/octet-stream"}\r\n\r\n'.encode())
        body = b"".join(parts) + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(TG_URL.format(token=self._token, method=method), data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 (fixed host)
                out = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                out = json.load(e)
            except ValueError:
                raise TelegramError(f"http {e.code}", e.code) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise TelegramError(f"network: {type(e).__name__}") from None
        if not out.get("ok"):
            raise TelegramError(str(out.get("description"))[:200], out.get("error_code") or 0)
        return out["result"]

    def download(self, file_path: str, dest: Path, limit: int = 20 << 20) -> Path:
        req = urllib.request.Request(TG_FILE.format(token=self._token, path=file_path))
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:  # noqa: S310
                size = 0
                while chunk := r.read(1 << 16):
                    size += len(chunk)
                    if size > limit:
                        raise TelegramError("file too large")
                    f.write(chunk)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise TelegramError(f"download: {type(e).__name__}") from None
        os.chmod(dest, 0o600)
        return dest


class EngineError(Exception):
    def __init__(self, status: int, code: str, detail: str | None = None):
        super().__init__(f"{status} {code}" + (f": {detail}" if detail else ""))
        self.status, self.code, self.detail = status, code, detail


class Engine:
    """Engine API client (core/interfaces/api): token in the header, loopback only."""

    def __init__(self, base: str, token: str):
        self.base, self._token = base.rstrip("/"), token

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self._token, "Content-Type": "application/json"}

    def op(self, body: dict, timeout: float = 60) -> dict:
        req = urllib.request.Request(self.base + "/v1", data=json.dumps({"version": 1, **body}).encode(),
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                d = json.load(e)
            except ValueError:
                d = {}
            raise EngineError(e.code, d.get("error") or f"http_{e.code}", d.get("detail")) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise EngineError(0, "engine_unavailable", type(e).__name__) from None

    def events(self, session_id: str, since: int | None, stop: threading.Event):
        """SSE of one session, subscribed when this returns: an iterator of client events (dicts) until the stream
        ends or `stop` is set."""
        q = f"session_id={urllib.request.quote(session_id, safe='')}" + (f"&since_seq={since}" if since is not None else "")
        req = urllib.request.Request(f"{self.base}/v1/events?{q}", headers=self._headers())
        try:
            r = urllib.request.urlopen(req, timeout=45)   # pings every 15 s keep the read alive
        except urllib.error.HTTPError as e:
            try:
                d = json.load(e)
            except ValueError:
                d = {}
            raise EngineError(e.code, d.get("error") or f"http_{e.code}", d.get("detail")) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            raise EngineError(0, "engine_unavailable", type(e).__name__) from None
        return self._read(r, stop)

    @staticmethod
    def _read(r, stop: threading.Event):
        with r:
            data: list[str] = []
            for raw in r:
                if stop.is_set():
                    return
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("data:"):
                    data.append(line[5:].lstrip())
                elif not line and data:
                    try:
                        yield json.loads("\n".join(data))
                    except ValueError:
                        pass
                    data = []


# ── settings and state ───────────────────────────────────────────────────────────────────────────────────────────

def _walter(*args: str) -> str:
    return subprocess.run(["walter", *args], capture_output=True, text=True, timeout=60, check=True).stdout.strip()


def load_settings() -> dict:
    shipped = Path(__file__).resolve().parents[2] / "config" / "telegram.toml"     # this module's defaults
    chosen = Path(_walter("instance", "config", "core", "telegram.toml"))
    cfg = tomllib.loads(shipped.read_text()) if shipped.is_file() else {}
    if chosen.resolve() != shipped.resolve():                                       # the instance overrides per key
        for section, values in tomllib.loads(chosen.read_text()).items():
            cfg[section] = {**cfg.get(section, {}), **values} if isinstance(values, dict) else values
    root = Path(_walter("instance", "path"))
    expand = lambda v: str(root / v[len("@instance/"):]) if isinstance(v, str) and v.startswith("@instance/") else v  # noqa: E731
    t = cfg.get("telegram", {})
    e = cfg.get("engine", {})
    return {"grant": t.get("grant", "telegram-walter-bot"), "owner_ids": [int(x) for x in t.get("owner_ids", [])],
            "account": str(t.get("account") or "owner"), "state": expand(t.get("state", "@instance/state/core/telegram")),
            "callbacks": {str(k): list(v) for k, v in (cfg.get("callbacks") or {}).items() if isinstance(v, list) and v},
            "web": {k: list(v) for k, v in (cfg.get("web") or {}).items() if k in ("list", "run") and isinstance(v, list) and v},
            "engine_url": e.get("url", "http://127.0.0.1:8895"),
            "engine_token_file": expand(e.get("token_file", "@instance/bootstrap/engine/api.token"))}


class State:
    """Durable bits, written atomically (0600): Telegram offset, conversation number per chat, last seq per session."""

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = self.dir / "state.json"
        self.lock = threading.Lock()
        try:
            self.d = json.loads(self.file.read_text())
        except (OSError, ValueError):
            self.d = {}
        self.d.setdefault("offset", 0)
        self.d.setdefault("chats", {})
        self.d.setdefault("seq", {})

    def save(self) -> None:
        with self.lock:
            tmp = self.file.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.d, f)
            os.replace(tmp, self.file)

    def conversation(self, chat: int) -> str:
        n = int(self.d["chats"].get(str(chat), {}).get("n", 0))
        return f"chat-{chat}" + (f"-{n}" if n else "")

    def next_conversation(self, chat: int) -> str:
        c = self.d["chats"].setdefault(str(chat), {})
        c["n"] = int(c.get("n", 0)) + 1
        self.save()
        return self.conversation(chat)

    def seq(self, sid: str) -> int | None:
        return self.d["seq"].get(sid)

    def set_seq(self, sid: str, seq) -> None:
        if isinstance(seq, int) and seq > (self.d["seq"].get(sid) or 0):
            self.d["seq"][sid] = seq
            self.save()


# ── the door ─────────────────────────────────────────────────────────────────────────────────────────────────────

HELP = ("Je suis Walter, sur mon propre moteur.\n\n"
        "Écris-moi normalement. Commandes :\n"
        "/stop — interrompre ce que je fais\n"
        "/nouveau — commencer une nouvelle conversation\n"
        "/etat — où j'en suis (tâche en cours, autorisations en attente)")

_MODEL_PREFIX = re.compile(r"^\[([^\]\n]{1,60})\]\s*")


def split_model(text: str) -> tuple[str | None, str]:
    """`[GPT-6 high] question` → ("GPT-6 high", "question"); without brackets the service keeps its own model."""
    m = _MODEL_PREFIX.match(text)
    return (m.group(1).strip() or None, text[m.end():]) if m else (None, text)


END_NOTICE = {
    "cancelled": "⏹ Interrompu.",
    "budget_exhausted": "⚠️ Budget de ce tour atteint : je me suis arrêté.",
    "interrupted": "⚠️ Mon moteur a redémarré pendant ce tour. Redis-moi si je dois reprendre.",
    "unknown_outcome": "⚠️ Ce tour s'est terminé sans issue claire.",
}


def _at(v) -> float | None:
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else float(v)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


class Turn:
    def __init__(self):
        self.text = ""
        self.tools: list[str] = []
        self.status_msg: int | None = None
        self.status_shown = ""
        self.status_at = 0.0
        self.typing = threading.Event()


class Bot:
    def __init__(self, settings: dict, tg: Telegram, engine: Engine, state: State):
        self.s, self.tg, self.engine, self.state = settings, tg, engine, state
        self.stop = threading.Event()
        self.sessions: dict[int, str] = {}           # chat → engine session id (cache of session.open)
        self.followers: dict[str, threading.Thread] = {}
        self.turns: dict[str, Turn] = {}             # session → turn in progress
        self.approvals: dict[str, tuple[int, int, str]] = {}   # request id → (chat, message id, tool)
        self.lock = threading.Lock()
        self.polling = False                         # blocked in getUpdates: a stop may cut it short
        self._web: dict[str, str] | None = None      # web command → service (asked once, `[web] list`)

    # Telegram side ------------------------------------------------------------------------------------------------
    def send(self, chat: int, text: str, **extra) -> int | None:
        last = None
        for part in tgformat.chunks(text):
            for attempt in range(3):
                try:
                    try:
                        last = self.tg.call("sendMessage", {"chat_id": chat, "text": tgformat.to_html(part),
                                                            "parse_mode": "HTML", "disable_web_page_preview": True,
                                                            **extra})["message_id"]
                    except TelegramError as e:
                        if e.code != 400:
                            raise
                        last = self.tg.call("sendMessage", {"chat_id": chat, "text": part,
                                                            "disable_web_page_preview": True, **extra})["message_id"]
                    break
                except TelegramError as e:
                    if e.retry_after and attempt < 2:
                        time.sleep(min(e.retry_after, 30))
                        continue
                    log.warning("send failed: %s", e)
                    break
        return last

    def edit(self, chat: int, msg: int, text: str, **extra) -> None:
        try:
            self.tg.call("editMessageText", {"chat_id": chat, "message_id": msg, "text": text, **extra})
        except TelegramError as e:
            if "not modified" not in str(e):
                log.debug("edit failed: %s", e)

    def delete(self, chat: int, msg: int | None) -> None:
        if msg:
            try:
                self.tg.call("deleteMessage", {"chat_id": chat, "message_id": msg})
            except TelegramError:
                pass

    def _typing(self, chat: int, turn: Turn) -> None:
        while not turn.typing.is_set() and not self.stop.is_set():
            try:
                self.tg.call("sendChatAction", {"chat_id": chat, "action": "typing"}, timeout=10)
            except TelegramError:
                pass
            turn.typing.wait(4.5)

    # engine side ----------------------------------------------------------------------------------------------------
    def session(self, chat: int) -> str:
        sid = self.sessions.get(chat)
        if sid:
            return sid
        r = self.engine.op({"op": "session.open", "interface": "telegram", "conversation": self.state.conversation(chat),
                            "principal": {"kind": "owner", "id": self.s["account"]}, "mode": "interactive"})
        sid = r["session_id"]
        self.sessions[chat] = sid
        if self.state.seq(sid) is None and not r.get("resumed"):   # a new session: follow it from its start
            self.state.d["seq"][sid] = 0
            self.state.save()
        self.follow(chat, sid)
        return sid

    def follow(self, chat: int, sid: str) -> None:
        with self.lock:
            th = self.followers.get(sid)
            if th and th.is_alive():
                return
            ready = threading.Event()
            th = threading.Thread(target=self._follow, args=(chat, sid, ready), name=f"follow:{sid}", daemon=True)
            self.followers[sid] = th
            th.start()
        ready.wait(10)            # subscribed before anything is submitted (headers come at once)

    def _follow(self, chat: int, sid: str, ready: threading.Event) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            since = self.state.seq(sid)
            # a session met without state (state lost, older chat): only what happens from now on is shown
            skip_before = time.time() - 5 if since is None else None
            try:
                stream = self.engine.events(sid, 0 if since is None else since, self.stop)
                ready.set()
                for ev in stream:
                    backoff = 1.0
                    at = _at(ev.get("at"))
                    if skip_before and at and at < skip_before:
                        self.state.set_seq(sid, ev.get("seq"))
                        continue
                    self.on_event(chat, sid, ev)
                    self.state.set_seq(sid, ev.get("seq"))
            except EngineError as e:
                ready.set()
                if e.code == "unknown_session":
                    log.warning("session %s unknown to the engine: follower stops", sid)
                    return
                log.info("event stream %s: %s (reconnecting)", sid, e.code)
            except Exception as e:  # noqa: BLE001  a follower never dies silently
                ready.set()
                log.warning("event stream %s: %s", sid, type(e).__name__)
            self.stop.wait(backoff)
            backoff = min(backoff * 2, 30)

    def on_event(self, chat: int, sid: str, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "turn.started":
            turn = self.turns[sid] = Turn()
            threading.Thread(target=self._typing, args=(chat, turn), daemon=True).start()
        elif kind == "message.assistant":
            turn = self.turns.setdefault(sid, Turn())
            turn.text = ev.get("text") or turn.text
        elif kind == "tool.called":
            turn = self.turns.setdefault(sid, Turn())
            label = tgformat.tool_label(ev.get("name", ""))
            if label not in turn.tools:
                turn.tools.append(label)
            self._status(chat, turn)
        elif kind == "approval.requested":
            what = tgformat.tool_label(ev.get("tool", ""))
            why = f"\n{ev['reason']}" if ev.get("reason") else ""
            child = " (par un sous-agent)" if ev.get("child") else ""
            rid = ev.get("request_id")
            msg = self.send(chat, f"🔐 Autorisation demandée{child} : **{what}** (`{ev.get('tool')}`){why}",
                            reply_markup={"inline_keyboard": [[
                                {"text": "✅ Autoriser une fois", "callback_data": f"ap|{rid}|a"},
                                {"text": "⛔ Refuser", "callback_data": f"ap|{rid}|d"}]]})
            if msg and rid:
                self.approvals[rid] = (chat, msg, ev.get("tool") or "")
        elif kind == "approval.answered":
            rid = ev.get("request_id")
            if rid in self.approvals:
                c, msg, tool = self.approvals.pop(rid)
                outcome = {"allowed-once": "✅ autorisé une fois", "rejected": "⛔ refusé",
                           "cancelled": "⏹ annulé"}.get(ev.get("outcome"), str(ev.get("outcome")))
                self.edit(c, msg, f"🔐 {tool} — {outcome}")
        elif kind == "turn.ended":
            turn = self.turns.pop(sid, None) or Turn()
            turn.typing.set()
            self.delete(chat, turn.status_msg)
            status = ev.get("status")
            if status == "ok":
                self.send(chat, turn.text or "(pas de réponse)")
            elif status == "error":
                self.send(chat, (turn.text + "\n\n" if turn.text else "") +
                          f"⚠️ Ce tour a échoué ({ev.get('reason') or 'erreur'}). Rien d'autre n'a été lancé à sa place.")
            else:
                self.send(chat, (turn.text + "\n\n" if turn.text else "") + END_NOTICE.get(status, f"Fin : {status}"))
        elif kind == "stream.error":
            raise EngineError(0, ev.get("code") or "stream_error")

    def _status(self, chat: int, turn: Turn) -> None:
        text = "⏳ " + " · ".join(turn.tools[-6:])
        if text == turn.status_shown or time.time() - turn.status_at < 2.5:
            return
        turn.status_at = time.time()
        turn.status_shown = text
        if turn.status_msg:
            self.edit(chat, turn.status_msg, text)
        else:
            try:
                turn.status_msg = self.tg.call("sendMessage", {"chat_id": chat, "text": text,
                                                               "disable_notification": True})["message_id"]
            except TelegramError:
                pass

    # updates ---------------------------------------------------------------------------------------------------------
    def owner(self, user: dict | None) -> bool:
        return bool(user) and int(user.get("id", 0)) in self.s["owner_ids"]

    def handle(self, u: dict) -> None:
        if "callback_query" in u:
            return self.on_callback(u["callback_query"])
        m = u.get("message") or u.get("edited_message")
        if not m:
            return
        chat = m["chat"]["id"]
        if not self.owner(m.get("from")) or m["chat"].get("type") != "private":
            log.warning("ignored a message from a non-owner (user %s, chat type %s)",
                        (m.get("from") or {}).get("id"), m["chat"].get("type"))
            return
        if u.get("edited_message"):
            return       # an edit is not a new instruction
        text = (m.get("text") or m.get("caption") or "").strip()
        cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else None
        try:
            if cmd in ("/start", "/aide", "/help"):
                self.session(chat)
                self.send(chat, HELP + "".join(f"\n/{c} — écrire directement à {v} (service web, sans tour du moteur)"
                                               for c, v in sorted(self.web_commands().items())))
                return
            if cmd == "/stop":
                return self.cmd_stop(chat)
            if cmd in ("/nouveau", "/new"):
                self.sessions.pop(chat, None)
                self.state.next_conversation(chat)
                self.session(chat)
                self.send(chat, "🆕 Nouvelle conversation.")
                return
            if cmd in ("/etat", "/status"):
                return self.cmd_status(chat)
            service = self.web_commands().get(cmd[1:]) if cmd else None
            if service:       # a web service's own conversation: never an engine turn
                return self.web_command(chat, m, service, text)
            attachment = self.attachment(chat, m)
            if attachment:
                text = f"{attachment}\n\n{text}".strip()
            if not text:
                self.send(chat, "Je ne sais pas encore lire ce type de message (notes vocales : bientôt).")
                return
            sid = self.session(chat)
            self.engine.op({"op": "turn.submit", "session_id": sid, "message": {"text": text}, "channel": "owner",
                            "idempotency_key": f"tg-{chat}-{m['message_id']}"})
        except EngineError as e:
            log.warning("engine refused: %s", e)
            if e.code == "engine_unavailable":
                self.send(chat, "⚠️ Mon moteur est indisponible pour l'instant ; ton message n'a pas été traité. "
                                "Réessaie dans un moment.")
            else:
                self.send(chat, f"⚠️ Message non traité : {e.code}" + (f" — {e.detail}" if e.detail else ""))

    def attachment(self, chat: int, m: dict) -> str | None:
        """A photo or a document: kept in the instance (0600) and named to the engine, which reads it with its tools."""
        kind, dest, note = self.save_attachment(chat, m)
        if note:
            return note
        return f"[{kind} reçu de Monsieur sur Telegram, enregistré ici : {dest}]" if dest else None

    def save_attachment(self, chat: int, m: dict) -> tuple[str | None, Path | None, str | None]:
        """(kind, saved path, note when it could not be kept) of the message's photo or document."""
        if m.get("photo"):
            f, kind, name = m["photo"][-1], "photo", f"photo-{m['message_id']}.jpg"
        elif m.get("document"):
            d = m["document"]
            f, kind = d, "document"
            name = re.sub(r"[^A-Za-z0-9._-]", "_", d.get("file_name") or f"document-{m['message_id']}")[:120]
        else:
            return None, None, None
        if (f.get("file_size") or 0) > 20 << 20:
            return kind, None, f"[{kind} reçu mais trop lourd pour le bot Telegram (> 20 Mo)]"
        info = self.tg.call("getFile", {"file_id": f["file_id"]})
        inbox = self.state.dir / "inbox" / str(chat)
        inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        return kind, self.tg.download(info["file_path"], inbox / f"{m['message_id']}-{name}"), None

    # web services (lot E6: /gpt … no longer through Hermes) -----------------------------------------------------
    def web_commands(self) -> dict[str, str]:
        if self._web is None:
            self._web = {}
            lister = (self.s.get("web") or {}).get("list")
            if lister:
                try:
                    r = subprocess.run(lister, capture_output=True, text=True, timeout=60)
                    out = json.loads((r.stdout or "").strip() or "{}")
                    self._web = {str(k).lower(): str(v) for k, v in out.items()} if isinstance(out, dict) else {}
                except (OSError, subprocess.SubprocessError, ValueError) as e:
                    log.warning("web commands unavailable: %s", type(e).__name__)
        return self._web

    def web_command(self, chat: int, m: dict, service: str, text: str) -> None:
        word, rest = (re.match(r"^(\S+)\s*(.*)$", text, re.S) or re.match(r"(.*)()", text)).groups()
        model, rest = split_model(rest.strip())
        if not rest.strip():
            self.send(chat, f"Usage : {word} [modèle] <message> — photo ou document joints possibles, en légende ; "
                            "sans [modèle], celui déjà choisi dans le service")
            return
        threading.Thread(target=self.web_exchange, args=(chat, m, service, model, rest.strip()), daemon=True).start()

    def web_exchange(self, chat: int, m: dict, service: str, model: str | None, message: str) -> dict:
        """One owner message to a web service (`[web] run`) and its reply as is; produced files sent back."""
        t0 = time.time()
        try:
            self.tg.call("sendChatAction", {"chat_id": chat, "action": "typing"})
        except TelegramError:
            pass
        spec = {"service": service, "message": message, "conversation": f"telegram:{chat}",
                "request_id": f"telegram-walter:{chat}:{m['message_id']}"}
        if model:
            spec["model"] = model
        try:
            kind, path, note = self.save_attachment(chat, m)
        except TelegramError as e:
            kind, path, note = None, None, f"pièce jointe illisible ({e})"
        if note:
            self.send(chat, f"⚠️ {note.strip('[]')}")
            return {"ok": False}
        if path:
            spec["files"] = [str(path)]
        try:
            r = subprocess.run(self.s["web"]["run"], input=json.dumps(spec), capture_output=True, text=True,
                               timeout=900)
            out = json.loads((r.stdout or "").strip() or "{}")
        except subprocess.TimeoutExpired:
            out = {"ok": False, "error": "délai dépassé"}
        except (OSError, ValueError, KeyError) as e:
            out = {"ok": False, "error": type(e).__name__}
        produced = out.get("files") or []
        if out.get("ok"):
            body = out.get("reply") or ""
            lost = [f.get("name") or f.get("kind") for f in produced if not f.get("path")]
            if lost:
                body += ("\n\n" if body else "") + "⚠️ non récupéré : " + ", ".join(map(str, lost))
        elif out.get("error") == "service_disabled":
            body = f"⚠️ {service} est désactivé. {out.get('note') or ''}".strip()
        else:
            body = f"⚠️ {service} : {out.get('error') or out.get('status') or 'échec'}"
            if out.get("status") == "incomplete" and out.get("reply"):
                body = out["reply"] + "\n\n⚠️ réponse incomplète (délai dépassé)"
        sendable = [f for f in produced if f.get("path")] if out.get("ok") else []
        if body or not sendable:
            self.send(chat, body or "(réponse vide)")
        for f in sendable:
            p = Path(f["path"])
            photo = f.get("kind") == "image" and f.get("mime") in ("image/png", "image/jpeg", "image/webp") \
                and p.stat().st_size < 10_000_000
            try:
                self.tg.upload("sendPhoto" if photo else "sendDocument", {"chat_id": chat},
                               "photo" if photo else "document", p, f.get("mime") or "")
            except (TelegramError, OSError) as e:
                self.send(chat, f"⚠️ fichier non envoyé : {p.name} ({e})")
        measure = {"service": service, "ok": bool(out.get("ok")), "status": out.get("status"),
                   "duplicate": bool(out.get("duplicate")), "model": bool(model), "files_in": int(bool(path)),
                   "files_out": len(sendable), "seconds": round(time.time() - t0, 1)}
        log.info("WALTER_WEB %s", json.dumps(measure))
        return measure

    def on_callback(self, q: dict) -> None:
        if not self.owner(q.get("from")):
            return
        data = q.get("data") or ""
        answer = "?"
        command = self.s.get("callbacks", {}).get(data.split(":", 1)[0]) if ":" in data else None
        if command:      # a module's button (e.g. a Router alert): its own command decides, off the polling thread
            threading.Thread(target=self.module_button, args=(q, command, data), daemon=True).start()
            return
        if data.startswith("ap|"):
            _, rid, choice = (data.split("|") + ["", ""])[:3]
            decision = "allow_once" if choice == "a" else "deny"
            try:
                self.engine.op({"op": "approval.answer", "request_id": rid, "decision": decision,
                                "principal": {"kind": "owner", "id": self.s["account"]}})
                answer = "Autorisé une fois" if decision == "allow_once" else "Refusé"
            except EngineError as e:
                answer = "Déjà répondu ou expiré" if e.code == "unknown_request" else f"Erreur : {e.code}"
                if e.code == "unknown_request" and q.get("message"):
                    self.edit(q["message"]["chat"]["id"], q["message"]["message_id"], "🔐 Demande expirée ou déjà traitée.")
        try:
            self.tg.call("answerCallbackQuery", {"callback_query_id": q["id"], "text": answer})
        except TelegramError:
            pass

    def module_button(self, q: dict, command: list[str], data: str) -> None:
        """Run `<command> <data>`; it prints {ok, toast, drop: [callback prefixes whose buttons go]}."""
        try:
            r = subprocess.run([*command, data], capture_output=True, text=True, timeout=120)
            out = json.loads((r.stdout or "").strip() or "{}")
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            out = {"ok": False, "toast": f"Échec : {type(e).__name__}"}
        toast = str(out.get("toast") or ("Enregistré" if out.get("ok") else "Échec"))[:190]
        m = q.get("message") or {}
        if out.get("ok") and m:
            rows = (m.get("reply_markup") or {}).get("inline_keyboard") or []
            clicked = next((b.get("text") for row in rows for b in row if b.get("callback_data") == data), data)
            drop = [str(x) for x in out.get("drop") or [data]]
            keep = [r for r in ([b for b in row if not any(str(b.get("callback_data", "")).startswith(d) for d in drop)]
                                for row in rows) if r]
            self.edit(m["chat"]["id"], m["message_id"], f"{m.get('text') or ''}\n\n→ {clicked}",
                      disable_web_page_preview=True, **({"reply_markup": {"inline_keyboard": keep}} if keep else {}))
        try:
            self.tg.call("answerCallbackQuery", {"callback_query_id": q["id"], "text": toast,
                                                 **({} if out.get("ok") else {"show_alert": True})})
        except TelegramError:
            pass

    def cmd_stop(self, chat: int) -> None:
        sid = self.session(chat)
        try:
            self.engine.op({"op": "turn.cancel", "session_id": sid, "reason": "telegram /stop"})
            if sid not in self.turns:
                self.send(chat, "Rien en cours.")
        except EngineError as e:
            self.send(chat, f"⚠️ Interruption impossible : {e.code}")

    def cmd_status(self, chat: int) -> None:
        sid = self.session(chat)
        turn = self.turns.get(sid)
        pending = self.engine.op({"op": "approval.list", "session_id": sid}).get("approvals", [])
        lines = [f"Conversation : {sid.split('/')[-1]}",
                 ("En cours : " + (" · ".join(turn.tools) or "réflexion")) if turn else "Rien en cours.",
                 f"Autorisations en attente : {len(pending)}"]
        self.send(chat, "\n".join(lines))

    def run(self) -> None:
        log.info("walter-telegram: started (owners %d, engine %s)", len(self.s["owner_ids"]), self.engine.base)
        for chat in list({int(k) for k in self.state.d["chats"]}):
            try:
                self.session(chat)                    # pick up followers of known chats after a restart
            except EngineError as e:
                log.warning("resume chat follower: %s", e.code)
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self.polling = True
                updates = self.tg.call("getUpdates", {"offset": self.state.d["offset"], "timeout": 50,
                                                      "allowed_updates": ["message", "edited_message", "callback_query"]},
                                       timeout=65)
                backoff = 1.0
                self.polling = False
            except TelegramError as e:
                self.polling = False
                log.info("getUpdates: %s", e)
                self.stop.wait(e.retry_after or backoff)
                backoff = min(backoff * 2, 60)
                continue
            for u in updates:
                try:
                    m = u.get("message") or {}
                    if m.get("chat", {}).get("type") == "private" and self.owner(m.get("from")):
                        self.state.d["chats"].setdefault(str(m["chat"]["id"]), {})
                    self.handle(u)
                except Exception:  # noqa: BLE001  one bad update never stops the door
                    log.exception("update %s failed", u.get("update_id"))
                # the offset moves once handled: a crash in between replays the update, and its turn is idempotent
                # (Telegram message id = idempotency key), so it never runs twice
                self.state.d["offset"] = u["update_id"] + 1
                self.state.save()


def token_from_grant(grant: str) -> str:
    r = subprocess.run(["walter-secret", "grant", "access", grant], capture_output=True, text=True, timeout=120)
    if r.returncode or not r.stdout.strip():
        raise SystemExit(f"walter-telegram: grant {grant} unavailable (walter-secret grants {grant})")
    return r.stdout.strip()


def notify(tg: Telegram, owners: list[int], text: str, *, plain: bool, silent: bool, buttons: list | None) -> dict:
    """One message (chunked) to each owner account through Walter's bot; buttons on the last chunk."""
    parts = tgformat.chunks(text) or ["(vide)"]
    sent = 0
    for chat in owners:
        for i, part in enumerate(parts):
            payload = {"chat_id": chat, "disable_web_page_preview": True, "disable_notification": silent,
                       **({"reply_markup": {"inline_keyboard": buttons}} if buttons and i == len(parts) - 1 else {})}
            try:
                tg.call("sendMessage", {**payload, "text": part} if plain else
                        {**payload, "text": tgformat.to_html(part), "parse_mode": "HTML"})
            except TelegramError as e:
                if plain or e.code != 400:
                    raise
                tg.call("sendMessage", {**payload, "text": part})
            sent += 1
    return {"ok": True, "messages": sent}


def main() -> int:
    ap = argparse.ArgumentParser(prog="walter-telegram")
    ap.add_argument("command", nargs="?", default="serve", choices=("serve", "check", "send"))
    ap.add_argument("text", nargs="?", help="send: the message (« - » or absent = stdin)")
    ap.add_argument("--check", action="store_true", help="same as the check command")
    ap.add_argument("--plain", action="store_true", help="send: no Markdown conversion")
    ap.add_argument("--silent", action="store_true", help="send: no notification sound")
    ap.add_argument("--buttons", help="send: inline keyboard as JSON rows [[{text, callback_data}]]")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = load_settings()
    if not s["owner_ids"]:
        raise SystemExit("walter-telegram: no owner_ids in telegram.toml — nobody to serve")
    tg = Telegram(token_from_grant(s["grant"]))
    if a.command == "send":
        text = a.text if a.text not in (None, "-") else sys.stdin.read()
        try:
            out = notify(tg, s["owner_ids"], text, plain=a.plain, silent=a.silent,
                         buttons=json.loads(a.buttons) if a.buttons else None)
        except (TelegramError, ValueError) as e:
            print(json.dumps({"ok": False, "error": str(e)[:200]}))
            return 1
        print(json.dumps(out))
        return 0
    engine = Engine(s["engine_url"], Path(s["engine_token_file"]).read_text().strip())
    if a.check or a.command == "check":
        me = tg.call("getMe")
        h = engine.op({"op": "health"})
        print(json.dumps({"bot": me.get("username"), "owners": len(s["owner_ids"]), "engine": h.get("ok"),
                          "state": s["state"]}))
        return 0
    bot = Bot(s, tg, engine, State(s["state"]))
    def _stop(*_):
        bot.stop.set()
        if bot.polling:              # nothing half-handled: leave now rather than wait for the long poll
            raise SystemExit(0)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
