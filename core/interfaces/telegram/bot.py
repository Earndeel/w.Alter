"""Walter Telegram — the engine's Telegram door (lot E7, 2026-11-10).

A client of the Engine API and nothing else: it owns no loop, no session store, no model choice. One Telegram chat of
the owner = one engine conversation `telegram/<account>/chat-<id>[-n]` (persistent, `/nouveau` starts the next one).
Messages are submitted with the Telegram message id as idempotency key (a replayed update never runs twice); the
session's events (SSE) drive what the owner sees: « écrit… », the tools at work, the answer, approval buttons, the end
of an interrupted or failed turn. Only the owner's Telegram accounts are served; anything else is ignored and logged.

    walter-python /walter/core/interfaces/telegram/bot.py            (service walter-telegram)
    walter-python /walter/core/interfaces/telegram/bot.py --check    (configuration, bot and engine reachable)

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
    cfg = tomllib.loads(Path(_walter("instance", "config", "core", "telegram.toml")).read_text())
    root = Path(_walter("instance", "path"))
    expand = lambda v: str(root / v[len("@instance/"):]) if isinstance(v, str) and v.startswith("@instance/") else v  # noqa: E731
    t = cfg.get("telegram", {})
    e = cfg.get("engine", {})
    return {"grant": t.get("grant", "telegram-walter-bot"), "owner_ids": [int(x) for x in t.get("owner_ids", [])],
            "account": str(t.get("account") or "owner"), "state": expand(t.get("state", "@instance/state/core/telegram")),
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
                self.send(chat, HELP)
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
        if m.get("photo"):
            f, kind, name = m["photo"][-1], "photo", f"photo-{m['message_id']}.jpg"
        elif m.get("document"):
            d = m["document"]
            f, kind = d, "document"
            name = re.sub(r"[^A-Za-z0-9._-]", "_", d.get("file_name") or f"document-{m['message_id']}")[:120]
        elif m.get("voice") or m.get("audio") or m.get("video") or m.get("video_note"):
            return None
        else:
            return None
        if (f.get("file_size") or 0) > 20 << 20:
            return f"[{kind} reçu mais trop lourd pour le bot Telegram (> 20 Mo)]"
        info = self.tg.call("getFile", {"file_id": f["file_id"]})
        inbox = self.state.dir / "inbox" / str(chat)
        inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest = self.tg.download(info["file_path"], inbox / f"{m['message_id']}-{name}")
        return f"[{kind} reçu de Monsieur sur Telegram, enregistré ici : {dest}]"

    def on_callback(self, q: dict) -> None:
        if not self.owner(q.get("from")):
            return
        data = q.get("data") or ""
        answer = "?"
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = load_settings()
    if not s["owner_ids"]:
        raise SystemExit("walter-telegram: no owner_ids in telegram.toml — nobody to serve")
    tg = Telegram(token_from_grant(s["grant"]))
    engine = Engine(s["engine_url"], Path(s["engine_token_file"]).read_text().strip())
    if a.check:
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
