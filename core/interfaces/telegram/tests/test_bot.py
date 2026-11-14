"""Lot E7: the Telegram door is a client of the Engine API — owner only, idempotent, events drive what is shown."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot as B  # noqa: E402
import tgformat  # noqa: E402

OWNER, CHAT = 111, 111


class FakeTg:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.n = 100
        self.refuse_html = False

    def call(self, method, payload=None, timeout=30):
        payload = payload or {}
        if method == "sendMessage" and self.refuse_html and payload.get("parse_mode") == "HTML":
            raise B.TelegramError("can't parse entities", 400)
        self.calls.append((method, payload))
        if method == "sendMessage":
            self.n += 1
            return {"message_id": self.n}
        return True

    def sent(self):
        return [p["text"] for m, p in self.calls if m == "sendMessage"]


class FakeEngine:
    base = "http://engine"

    def __init__(self):
        self.ops: list[dict] = []
        self.fail: B.EngineError | None = None

    def op(self, body, timeout=60):
        self.ops.append(body)
        if self.fail:
            raise self.fail
        if body["op"] == "session.open":
            return {"session_id": f"telegram/{body['principal']['id']}/{body['conversation']}", "resumed": False}
        if body["op"] == "approval.list":
            return {"approvals": []}
        return {"accepted": True}


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setattr(B.Bot, "follow", lambda self, chat, sid: None)
    s = {"owner_ids": [OWNER], "account": "monsieur", "grant": "g"}
    b = B.Bot(s, FakeTg(), FakeEngine(), B.State(str(tmp_path)))
    return b


def msg(text, mid=1, user=OWNER, chat_type="private", **extra):
    return {"update_id": mid, "message": {"message_id": mid, "from": {"id": user}, "chat": {"id": CHAT, "type": chat_type},
                                          "text": text, **extra}}


def test_owner_text_is_one_idempotent_turn_in_a_persistent_conversation(door):
    door.handle(msg("Bonjour Walter", 7))
    opened, submit = door.engine.ops
    assert opened == {"op": "session.open", "interface": "telegram", "conversation": f"chat-{CHAT}",
                      "principal": {"kind": "owner", "id": "monsieur"}, "mode": "interactive"}
    assert submit["op"] == "turn.submit" and submit["idempotency_key"] == f"tg-{CHAT}-7"
    assert submit["session_id"] == f"telegram/monsieur/chat-{CHAT}" and submit["channel"] == "owner"
    door.handle(msg("Encore", 8))
    assert [o["op"] for o in door.engine.ops] == ["session.open", "turn.submit", "turn.submit"]   # session cached


def test_strangers_groups_and_edits_are_ignored(door):
    door.handle(msg("hello", 1, user=999))
    door.handle(msg("hello", 2, chat_type="group"))
    door.handle({"update_id": 3, "edited_message": {"message_id": 1, "from": {"id": OWNER},
                                                    "chat": {"id": CHAT, "type": "private"}, "text": "x"}})
    assert door.engine.ops == [] and door.tg.calls == []


def test_stop_new_and_status_commands(door):
    door.handle(msg("/stop", 1))
    assert door.engine.ops[-1] == {"op": "turn.cancel", "session_id": f"telegram/monsieur/chat-{CHAT}",
                                   "reason": "telegram /stop"}
    assert door.tg.sent()[-1] == "Rien en cours."
    door.handle(msg("/nouveau", 2))
    assert door.engine.ops[-1]["conversation"] == f"chat-{CHAT}-1"
    door.handle(msg("/etat", 3))
    assert "Rien en cours" in door.tg.sent()[-1]


def test_events_show_progress_then_the_answer_once(door):
    sid = "telegram/monsieur/chat-1"
    door.on_event(CHAT, sid, {"type": "turn.started", "seq": 1})
    door.on_event(CHAT, sid, {"type": "tool.called", "name": "mcp__walter__memory_search", "seq": 2})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": "**Sagora** est en ligne.", "seq": 3})
    door.on_event(CHAT, sid, {"type": "turn.ended", "status": "ok", "seq": 4})
    sends = [p for m, p in door.tg.calls if m == "sendMessage"]
    assert sends[0]["text"] == "⏳ mémoire" and sends[0]["disable_notification"]
    assert sends[-1]["text"] == "<b>Sagora</b> est en ligne." and sends[-1]["parse_mode"] == "HTML"
    assert ("deleteMessage", {"chat_id": CHAT, "message_id": 101}) in door.tg.calls
    assert sid not in door.turns


def test_failed_and_cancelled_turns_are_said(door):
    sid = "s"
    door.on_event(CHAT, sid, {"type": "turn.started"})
    door.on_event(CHAT, sid, {"type": "turn.ended", "status": "error", "reason": "error"})
    assert "échoué" in door.tg.sent()[-1] and "Rien d'autre" in door.tg.sent()[-1]
    door.on_event(CHAT, sid, {"type": "turn.started"})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": "à moitié"})
    door.on_event(CHAT, sid, {"type": "turn.ended", "status": "cancelled"})
    assert door.tg.sent()[-1] == "à moitié\n\n⏹ Interrompu."


def test_approval_buttons_answer_the_engine_as_the_owner(door):
    door.on_event(CHAT, "s", {"type": "approval.requested", "request_id": "r-1", "tool": "mcp__walter__browser_session",
                              "reason": "ouvrir Google"})
    m, p = [c for c in door.tg.calls if c[0] == "sendMessage"][-1]
    buttons = p["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == ["ap|r-1|a", "ap|r-1|d"]
    door.on_callback({"id": "q", "from": {"id": 999}, "data": "ap|r-1|a"})          # not the owner: nothing
    assert not any(o["op"] == "approval.answer" for o in door.engine.ops)
    door.on_callback({"id": "q", "from": {"id": OWNER}, "data": "ap|r-1|a"})
    assert door.engine.ops[-1] == {"op": "approval.answer", "request_id": "r-1", "decision": "allow_once",
                                   "principal": {"kind": "owner", "id": "monsieur"}}
    door.on_event(CHAT, "s", {"type": "approval.answered", "request_id": "r-1", "outcome": "allowed-once"})
    assert door.tg.calls[-1][0] == "editMessageText" and "autorisé une fois" in door.tg.calls[-1][1]["text"]


def test_engine_down_is_said_never_retried_elsewhere(door):
    door.engine.fail = B.EngineError(0, "engine_unavailable", "URLError")
    door.handle(msg("x", 5))
    assert "indisponible" in door.tg.sent()[-1]


def test_html_refused_falls_back_to_plain_text(door):
    door.tg.refuse_html = True
    door.send(CHAT, "a <b")
    assert door.tg.sent() == ["a <b"]


def test_state_is_durable_and_seq_only_moves_forward(tmp_path):
    s = B.State(str(tmp_path))
    s.set_seq("x", 5); s.set_seq("x", 3); s.d["offset"] = 42; s.save()
    again = B.State(str(tmp_path))
    assert again.seq("x") == 5 and again.d["offset"] == 42
    assert (tmp_path / "state.json").stat().st_mode & 0o777 == 0o600


def test_markdown_to_telegram_html_is_escaped_and_code_protected():
    assert tgformat.to_html("a < b & **c**") == "a &lt; b &amp; <b>c</b>"
    assert tgformat.to_html("`**x**` et [doc](https://e.x/a)") == '<code>**x**</code> et <a href="https://e.x/a">doc</a>'
    assert tgformat.to_html("## Titre\n```py\nprint(1<2)\n```") == "<b>Titre</b>\n<pre>print(1&lt;2)</pre>"


def test_long_answers_are_chunked_with_balanced_fences():
    parts = tgformat.chunks("```\n" + "\n".join("ligne %d" % i for i in range(900)) + "\n```", limit=1000)
    assert len(parts) > 3 and all(len(p) <= 1010 for p in parts) and all(p.count("```") % 2 == 0 for p in parts)
    assert tgformat.tool_label("mcp__walter__walter_browse") == "web" and tgformat.tool_label("subagent") == "sous-agent"


def test_a_module_button_runs_its_command_and_drops_the_answered_row(door, monkeypatch):
    door.s["callbacks"] = {"wr": ["walter-router", "button"]}
    ran = []

    class R:
        returncode, stderr = 0, ""
        stdout = '{"ok": true, "toast": "Enregistré : adopté", "drop": ["wr:a:3", "wr:d:3"]}'
    monkeypatch.setattr(B.subprocess, "run", lambda argv, **k: ran.append(argv) or R())
    monkeypatch.setattr(B.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    kb = [[{"text": "Adopter 3", "callback_data": "wr:a:3"}, {"text": "Ignorer 3", "callback_data": "wr:d:3"}],
          [{"text": "Adopter 4", "callback_data": "wr:a:4"}]]
    q = {"id": "q", "from": {"id": OWNER}, "data": "wr:a:3",
         "message": {"chat": {"id": CHAT}, "message_id": 9, "text": "Alerte", "reply_markup": {"inline_keyboard": kb}}}
    door.on_callback(q)
    assert ran == [["walter-router", "button", "wr:a:3"]]
    edit = [p for m, p in door.tg.calls if m == "editMessageText"][-1]
    assert edit["text"] == "Alerte\n\n→ Adopter 3" and edit["reply_markup"]["inline_keyboard"] == [[kb[1][0]]]
    assert door.tg.calls[-1] == ("answerCallbackQuery", {"callback_query_id": "q", "text": "Enregistré : adopté"})
    door.on_callback({**q, "from": {"id": 999}})                       # a stranger's click runs nothing
    assert len(ran) == 1


def test_send_reaches_each_owner_with_buttons_on_the_last_chunk():
    tg = FakeTg()
    out = B.notify(tg, [1, 2], "a\n\n" + "x" * 5000, plain=True, silent=False, buttons=[[{"text": "ok", "callback_data": "wr:a:1"}]])
    sends = [p for m, p in tg.calls if m == "sendMessage"]
    assert out == {"ok": True, "messages": len(sends)} and {p["chat_id"] for p in sends} == {1, 2}
    assert [bool(p.get("reply_markup")) for p in sends if p["chat_id"] == 1] == [False, False, True]


def test_web_service_command_goes_to_the_service_not_to_an_engine_turn(door, tmp_path, monkeypatch):
    """Lot E6: `/gpt [modèle] …` → `[web] run` with the spec; reply as is; a produced image comes back as a photo."""
    import json as _json
    import threading as _threading
    image = tmp_path / "out.png"
    image.write_bytes(b"\x89PNG fake")
    seen = tmp_path / "spec.json"
    runner = tmp_path / "run.py"
    runner.write_text("import json, sys\n"
                      f"open({str(seen)!r}, 'w').write(sys.stdin.read())\n"
                      f"print(json.dumps({{'ok': True, 'reply': 'Bonjour de ChatGPT', 'files': "
                      f"[{{'path': {str(image)!r}, 'kind': 'image', 'mime': 'image/png'}}, {{'name': 'perdu.pdf'}}]}}))\n")
    door.s["web"] = {"list": [sys.executable, "-c", "print('{\"gpt\": \"chatgpt\"}')"], "run": [sys.executable, str(runner)]}

    class Now(_threading.Thread):           # the exchange runs off the polling thread: here, at once
        def start(self):
            self.run()
    monkeypatch.setattr(B.threading, "Thread", Now)
    uploads = []
    door.tg.upload = lambda method, fields, field, path, mime="": uploads.append((method, field, path.name, mime)) or {}
    door.handle(msg("/gpt [GPT-6 high] Que vois-tu ?\nligne 2", 41))
    assert [o for o in door.engine.ops if o["op"] == "turn.submit"] == []
    spec = _json.loads(seen.read_text())
    assert spec == {"service": "chatgpt", "message": "Que vois-tu ?\nligne 2", "model": "GPT-6 high",
                    "conversation": f"telegram:{CHAT}", "request_id": f"telegram-walter:{CHAT}:41"}
    assert door.tg.sent()[-1].startswith("Bonjour de ChatGPT") and "perdu.pdf" in door.tg.sent()[-1]
    assert uploads == [("sendPhoto", "photo", "out.png", "image/png")]
    door.handle(msg("/gpt", 42))
    assert door.tg.sent()[-1].startswith("Usage : /gpt")
    door.handle(msg("/aide", 43))
    assert "/gpt — écrire directement à chatgpt" in door.tg.sent()[-1]


def test_without_web_services_an_unknown_command_is_an_ordinary_message(door):
    door.handle(msg("/gpt bonjour", 44))
    assert door.engine.ops[-1]["op"] == "turn.submit"


def test_split_model_prefix():
    assert B.split_model("[GPT-6 high] q") == ("GPT-6 high", "q")
    assert B.split_model("q [x]") == (None, "q [x]")


def test_upload_is_a_multipart_form_with_the_file(tmp_path, monkeypatch):
    import http.server
    import json as _json
    import threading as _threading
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got["type"] = self.headers["Content-Type"]
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            got["path"] = self.path
            out = _json.dumps({"ok": True, "result": {"message_id": 5}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    _threading.Thread(target=srv.handle_request, daemon=True).start()
    monkeypatch.setattr(B, "TG_URL", f"http://127.0.0.1:{srv.server_port}/bot{{token}}/{{method}}")
    f = tmp_path / 'image "1".png'
    f.write_bytes(b"\x89PNGDATA")
    assert B.Telegram("T").upload("sendPhoto", {"chat_id": 7}, "photo", f, "image/png") == {"message_id": 5}
    srv.server_close()
    assert got["path"] == "/botT/sendPhoto" and got["type"].startswith("multipart/form-data; boundary=")
    body = got["body"]
    assert b'name="chat_id"\r\n\r\n7\r\n' in body and b'filename="image _1_.png"' in body
    assert b"Content-Type: image/png\r\n\r\n\x89PNGDATA\r\n--" in body


def test_every_message_of_a_long_turn_reaches_telegram_the_last_one_notified(door):
    sid = "s-long"
    door.on_event(CHAT, sid, {"type": "turn.started"})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": "Je lance trois sous-agents."})
    door.on_event(CHAT, sid, {"type": "tool.called", "name": "subagent"})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": "Choix : option C."})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": ""})
    door.on_event(CHAT, sid, {"type": "message.assistant", "text": "Le comparatif est dans le fichier."})
    door.on_event(CHAT, sid, {"type": "turn.ended", "status": "ok"})
    msgs = [(p["text"], bool(p.get("disable_notification"))) for m, p in door.tg.calls
            if m == "sendMessage" and not p["text"].startswith("⏳")]
    assert msgs == [("Je lance trois sous-agents.", True), ("Choix : option C.", True),
                    ("Le comparatif est dans le fichier.", False)]


def test_voice_note_is_transcribed_echoed_silently_and_submitted(door, tmp_path, monkeypatch):
    """Lot E7 (no longer Hermes' STT): a voice note becomes one owner turn holding its transcript."""
    real_call = door.tg.call
    door.tg.call = lambda m, p=None, timeout=30: {"file_path": "voice/f.oga"} if m == "getFile" else real_call(m, p, timeout)
    door.tg.download = lambda fp, dest, limit=0: (dest.write_bytes(b"OggS"), dest)[1]
    door.s["stt"] = {"url": "http://llm", "task": "stt", "token_file": str(tmp_path / "t.env")}
    seen = []
    monkeypatch.setattr(B, "transcribe", lambda stt, path: seen.append(path.suffix) or "rappelle-moi demain")
    door.handle(msg("", 51, voice={"file_id": "F", "duration": 3}))
    turn = [o for o in door.engine.ops if o["op"] == "turn.submit"][-1]
    assert seen == [".oga"] and "rappelle-moi demain" in turn["message"]["text"]
    echo = [p for m, p in door.tg.calls if m == "sendMessage"][-1]
    assert "rappelle-moi demain" in echo["text"] and echo["disable_notification"] is True


def test_voice_note_that_cannot_be_transcribed_is_said_and_never_submitted(door, tmp_path, monkeypatch):
    real_call = door.tg.call
    door.tg.call = lambda m, p=None, timeout=30: {"file_path": "voice/f.oga"} if m == "getFile" else real_call(m, p, timeout)
    door.tg.download = lambda fp, dest, limit=0: (dest.write_bytes(b"OggS"), dest)[1]
    door.s["stt"] = {"url": "http://llm", "task": "stt", "token_file": str(tmp_path / "t.env")}

    def fail(stt, path):
        raise ValueError("no speech")
    monkeypatch.setattr(B, "transcribe", fail)
    door.handle(msg("", 52, voice={"file_id": "F", "duration": 3}))
    assert [o for o in door.engine.ops if o["op"] == "turn.submit"] == []
    assert "pas pu transcrire" in door.tg.sent()[-1]


def test_send_accepts_options_before_its_text_as_every_module_calls_it():
    """2026-11-13: `send --plain -` (Router proposals, alerts, gateway notices) was refused by argparse since 10/11."""
    a = B.parse_cli(["send", "--plain", "--buttons", "[]", "-"])
    assert (a.command, a.text, a.plain, a.buttons) == ("send", "-", True, "[]")
    assert B.parse_cli(["send", "--plain", "bonjour"]).text == "bonjour"
    assert B.parse_cli(["send", "bonjour", "--silent"]).silent is True
    assert B.parse_cli(["--check"]).check is True and B.parse_cli([]).command == "serve"
