"""Walter V1 — lot E7: the Telegram door against the REAL engine, Telegram itself simulated (2026-11-10).

The door's own code (core/interfaces/telegram/bot.py) runs in-process with a recording stand-in for the Bot API and
synthetic updates from a test owner account (`e2e`, its own conversations: the owner's chats are never touched):
  identity    « Qui es-tu ? » → Walter's Soul answers (name, the owner's address form)
  continuity  a fact given in one message is found again in the next (same persistent session)
  replay      the same Telegram update delivered twice runs once (idempotency key = message id)
  approval    an action that needs the owner → buttons → « Refuser » → the engine says it was refused
  stop        /stop during a long turn → « Interrompu »
Prints one line per check; exit 0 when all pass. Costs a few model turns.

    walter-python core/scenarios/v1/telegram_door.py [--only identity,stop]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "interfaces" / "telegram"))
import bot as B  # noqa: E402

TEST_USER = 4242


class RecordingTg:
    """Bot API stand-in: every call recorded, sendMessage numbered."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.n = 0
        self.lock = threading.Lock()

    def call(self, method, payload=None, timeout=30):
        with self.lock:
            self.calls.append((method, payload or {}))
            if method == "sendMessage":
                self.n += 1
                return {"message_id": self.n}
            return True

    def texts(self, since=0):
        return [p["text"] for m, p in self.calls[since:] if m == "sendMessage" and not p.get("disable_notification")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    root = Path(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True).stdout.strip())
    engine = B.Engine("http://127.0.0.1:8895", (root / "bootstrap/engine/api.token").read_text().strip())
    run = uuid.uuid4().hex[:6]
    state_dir = Path(f"/tmp/walter-telegram-e2e-{run}")
    tg = RecordingTg()
    door = B.Bot({"owner_ids": [TEST_USER], "account": "e2e", "grant": "-"}, tg, engine, B.State(str(state_dir)))
    chat = int(time.time()) % 10_000_000 + 10_000_000      # a fresh conversation per run
    mid = [0]
    results = []

    def say(text, mid_=None):
        mid[0] += 1
        u = {"update_id": mid[0], "message": {"message_id": mid_ or mid[0], "from": {"id": TEST_USER},
                                              "chat": {"id": chat, "type": "private"}, "text": text}}
        door.handle(u)

    def answer(since, timeout=240, want=1):
        end = time.time() + timeout
        while time.time() < end:
            t = tg.texts(since)
            if len(t) >= want:
                return t
            time.sleep(1)
        return tg.texts(since)

    def check(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001
            ok, info = False, f"{type(e).__name__}: {e}"
        results.append((name, ok))
        print(f"{'ok  ' if ok else 'FAIL'} {name:<11} {time.time() - t0:6.1f}s  {info}", flush=True)

    def c_identity():
        n = len(tg.calls)
        say("Test technique du canal Telegram : qui es-tu, et comment m'appelles-tu ? Une phrase.")
        t = " ".join(answer(n)).lower()
        typing = any(m == "sendChatAction" for m, _ in tg.calls[n:])
        return ("walter" in t or "w.alter" in t) and "monsieur" in t and typing, f"typing={typing} « {t[:90]} »"

    def c_continuity():
        n = len(tg.calls)
        say(f"Retiens ce code de test pour la suite de cette conversation : ORCHIDEE-{run}. Réponds juste « noté ».")
        answer(n)
        n = len(tg.calls)
        say("Quel était le code de test que je viens de te donner ? Donne-le seul.")
        t = " ".join(answer(n))
        return f"ORCHIDEE-{run}".lower() in t.lower(), f"« {t[:60]} »"

    def c_replay():
        submits = []
        orig = engine.op
        engine.op = lambda body, timeout=60: (submits.append(body) if body.get("op") == "turn.submit" else None) or orig(body, timeout)
        n = len(tg.calls)
        say("Réponds seulement « un ».", mid_=990001)
        say("Réponds seulement « un ».", mid_=990001)          # Telegram redelivers the same message
        t = answer(n, want=1)
        time.sleep(20)
        engine.op = orig
        t = tg.texts(n)
        keys = {s["idempotency_key"] for s in submits}
        return len(submits) == 2 and len(keys) == 1 and len(t) == 1, f"submits={len(submits)} keys={len(keys)} answers={len(t)}"

    def c_approval():
        n = len(tg.calls)
        say("Test d'autorisation : ouvre une session navigateur Google avec l'outil browser_session (site google) et "
            "dis-moi seulement si ça a été autorisé ou refusé.")
        end = time.time() + 180
        btn = None
        while time.time() < end and not btn:
            for m, p in tg.calls[n:]:
                if m == "sendMessage" and p.get("reply_markup"):
                    btn = p["reply_markup"]["inline_keyboard"][0][1]["callback_data"]
            time.sleep(1)
        if not btn:
            return False, f"no approval buttons; said: {tg.texts(n)[:2]}"
        door.on_callback({"id": "cb", "from": {"id": TEST_USER}, "data": btn})
        end = time.time() + 180
        while time.time() < end and not [x for x in tg.texts(n) if not x.startswith("🔐")]:
            time.sleep(1)
        t = " ".join(x for x in tg.texts(n) if not x.startswith("🔐")).lower()
        edited = any(m == "editMessageText" and "refusé" in p.get("text", "") for m, p in tg.calls[n:])
        return edited and "refus" in t, f"edited={edited} « {t[:80]} »"

    def c_stop():
        n = len(tg.calls)
        say("Test d'interruption : exécute `sleep 120` dans bash puis réponds « fini ».")
        time.sleep(25)
        say("/stop")
        t = answer(n, timeout=90)
        return any("Interrompu" in x for x in t), f"« {' | '.join(t)[:80]} »"

    for name, fn in (("identity", c_identity), ("continuity", c_continuity), ("replay", c_replay),
                     ("approval", c_approval), ("stop", c_stop)):
        check(name, fn)
    door.stop.set()
    failed = [n for n, ok in results if not ok]
    print(json.dumps({"chat": chat, "session": door.sessions.get(chat), "passed": len(results) - len(failed),
                      "failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    import sys                                             # the objectives this scenario opened are test data
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from e2e_objectives import close
    close("objectif de test du scénario telegram_door")
    raise SystemExit(rc)
