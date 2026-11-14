"""Walter V1 — lot E8: failures and resumption on the LIVE engine, through the Telegram door's code (2026-11-10).

Telegram itself is simulated (recording stand-in), the engine is the real one; a test owner account (`e2e`) with its
own conversations, never the owner's.
  door_restart    the door stops in the middle of a turn, a new door takes over from its saved state: the answer is
                  delivered once, by the new door
  engine_restart  the engine (dsh-web) restarts in the middle of a turn: the door says so, the turn is not replayed
                  (one owner message in the log), the same conversation answers the next message with its memory
  tool_failure    a tool fails (missing file): the turn ends normally and says what happened
  model           a model the Router cannot run → explicit refusal (422) before any session, never another loop
  budget          a delegated task over its time budget is interrupted and said so (cancelled, budget_seconds)
  delegate_replay the same delegated task sent twice (same idempotency key) runs once
Restarting dsh-web interrupts whatever runs on it: run this on the development instance only, at a quiet moment.

    walter-python core/scenarios/v1/engine_e8.py [--only door_restart,tool_failure]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "interfaces" / "telegram"))
import bot as B  # noqa: E402
from telegram_door import TEST_USER, RecordingTg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    root = Path(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True).stdout.strip())
    token = (root / "bootstrap/engine/api.token").read_text().strip()
    run = uuid.uuid4().hex[:6]
    state_dir = f"/tmp/walter-e8-{run}"
    results = []
    mid = [int(time.time())]

    def new_door(tg):
        return B.Bot({"owner_ids": [TEST_USER], "account": "e2e", "grant": "-"}, tg,
                     B.Engine("http://127.0.0.1:8895", token), B.State(state_dir))

    def say(door, chat, text):
        mid[0] += 1
        door.handle({"update_id": mid[0], "message": {"message_id": mid[0], "from": {"id": TEST_USER},
                                                      "chat": {"id": chat, "type": "private"}, "text": text}})

    def wait_texts(tg, since, timeout, pred=lambda t: bool(t)):
        end = time.time() + timeout
        while time.time() < end:
            t = tg.texts(since)
            if pred(t):
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
        print(f"{'ok  ' if ok else 'FAIL'} {name:<15} {time.time() - t0:6.1f}s  {info}", flush=True)

    def kernel_of(sid):
        b = json.loads((root / "state/core/engine/api/bindings.json").read_text())
        return b["sessions"][sid]["kernel"]

    def owner_messages(sid, needle):
        from walter_memory import db
        with db.connect() as c:
            return c.execute("""select count(*) n from walter_logs.events where session_id = %s and type = 'user/message'
                                and text like %s""", (f"dsh/vm/{kernel_of(sid)}", f"{needle}%")).fetchone()["n"]

    def c_door_restart():
        chat = 30_000_000 + mid[0] % 1_000_000
        tg_a, tg_b = RecordingTg(), RecordingTg()
        a_ = new_door(tg_a)
        say(a_, chat, f"Test de reprise {run} : cherche sur le web la date de sortie de Python 3.14 et réponds en une "
                      f"ligne qui commence par « reprise-{run} ».")
        time.sleep(4)
        a_.stop.set()                                   # the door goes away mid-turn
        time.sleep(2)
        b_ = new_door(tg_b)                             # a new door: same saved state
        b_.session(chat)
        t = wait_texts(tg_b, 0, 240, lambda t: any(f"reprise-{run}" in x for x in t))
        time.sleep(5)
        b_.stop.set()
        got_a = [x for x in tg_a.texts() if f"reprise-{run}" in x]
        got_b = [x for x in tg_b.texts() if f"reprise-{run}" in x]
        return len(got_b) == 1 and not got_a, f"old door={len(got_a)} new door={len(got_b)} « {(got_b or t or [''])[0][:60]} »"

    def c_engine_restart():
        chat = 31_000_000 + mid[0] % 1_000_000
        tg = RecordingTg()
        d = new_door(tg)
        say(d, chat, f"Retiens le code PIVOINE-{run}. Réponds seulement « noté ».")
        wait_texts(tg, 0, 120)
        n = len(tg.calls)
        say(d, chat, f"Test de panne {run} : cherche sur le web les trois dernières versions de Node.js et détaille "
                     "chacune en un paragraphe.")
        time.sleep(6)
        subprocess.run(["systemctl", "restart", "dsh-web"], check=True)
        said = wait_texts(tg, n, 120, lambda t: any("redémarr" in x or "échoué" in x or "Interrompu" in x for x in t))
        for _ in range(60):                              # engine back
            try:
                d.engine.op({"op": "health"}, timeout=5)
                break
            except B.EngineError:
                time.sleep(2)
        time.sleep(3)
        n2 = len(tg.calls)
        say(d, chat, "Quel est le code que je t'ai demandé de retenir ? Donne-le seul.")
        after = wait_texts(tg, n2, 180)
        sid = d.sessions[chat]
        once = owner_messages(sid, f"Test de panne {run}")
        d.stop.set()
        return any(f"PIVOINE-{run}".lower() in x.lower() for x in after) and once == 1 and bool(said), \
            f"said={said[-1][:50] if said else None!r} replays={once} continuity={after[-1][:30] if after else None!r}"

    def c_tool_failure():
        chat = 32_000_000 + mid[0] % 1_000_000
        tg = RecordingTg()
        d = new_door(tg)
        say(d, chat, f"Lis le fichier /tmp/absent-{run}.txt et dis-moi en une phrase ce qui s'est passé.")
        t = " ".join(wait_texts(tg, 0, 180)).lower()
        d.stop.set()
        return any(w in t for w in ("existe pas", "introuvable", "absent", "n'existe", "aucun fichier", "not found")), f"« {t[:80]} »"

    def c_model():
        api = B.Engine("http://127.0.0.1:8895", token)
        try:
            api.op({"op": "delegate", "caller": "e2e", "delegation": {
                "version": 1, "goal": "x", "model": {"id": "deepseek-v4-1-flash", "provider": "fournisseur-inexistant"},
                "idempotency_key": f"e8-{run}-model", "parent": {"depth": 0}}})
            return False, "accepted"
        except B.EngineError as e:
            return e.status == 422 and e.code == "model_unavailable", f"{e.status} {e.code} {e.detail}"

    def delegate(goal, key, budget, model=None):
        api = B.Engine("http://127.0.0.1:8895", token)
        return api.op({"op": "delegate", "caller": "e2e", "delegation": {
            "version": 1, "goal": goal, "idempotency_key": key, "budget_seconds": budget, "parent": {"depth": 0},
            **({"model": model} if model else {})}}, timeout=budget + 90)

    def c_budget():
        t = time.time()
        # a long answer, no tool (an unattended delegation gets no shell): cut at 60 s, a few thousand tokens at most
        # a legitimate long task: an absurd one (3 000 numbers in letters) is now declined in one sentence
        # (soul rule « Effort proportionné », 2026-11-10), which never reaches the budget
        # 13/11/2026: the plan asked the everyday tier for this sub-agent mission and that model wrote the essay in
        # 12 s — the budget was never reached and nothing was proven. The caller names the model Walter Router gives
        # for the most demanding text tier (asked to the Router here, never a model id of the scenario's own).
        pick = json.loads(subprocess.run(["walter-router", "pick", "general", "--level", "L3"], capture_output=True,
                                         text=True, timeout=60).stdout)
        r = delegate("Sans aucun outil, rédige en une seule réponse un essai complet d'environ 5 000 mots sur "
                     "l'histoire de l'imprimerie, en dix sections détaillées.", f"e8-{run}-budget", 60,
                     model={"id": pick["model_id"], "provider": pick["provider"]})
        r = r.get("result") or r
        took = time.time() - t
        return r.get("status") == "cancelled" and r.get("reason") == "budget_seconds" and took < 120, \
            f"{r.get('status')} {r.get('reason')} en {took:.0f}s"

    def c_delegate_replay():
        key, word = f"e8-{run}-replay", f"double-{run}"
        a_ = delegate(f"Réponds seulement « {word} ».", key, 120)
        b_ = delegate(f"Réponds seulement « {word} ».", key, 120)        # the caller retries the same task
        a_, b_ = a_.get("result") or a_, b_.get("result") or b_
        from walter_memory import db
        bind = json.loads((root / "state/core/engine/api/bindings.json").read_text())["sessions"][a_["session_id"]]
        with db.connect() as c:
            n = c.execute("""select count(*) n from walter_logs.events where session_id = %s and type = 'user/message'
                             and text like %s""", (f"dsh/vm/{bind['kernel']}", f"%{word}%")).fetchone()["n"]
        return word in (a_.get("output") or "") and a_.get("session_id") == b_.get("session_id") and n == 1, \
            f"first={a_.get('status')} again={b_.get('status')} « {(b_.get('output') or '')[:30]} » executed={n}"

    for name, fn in (("model", c_model), ("tool_failure", c_tool_failure), ("door_restart", c_door_restart),
                     ("engine_restart", c_engine_restart), ("budget", c_budget), ("delegate_replay", c_delegate_replay)):
        check(name, fn)
    failed = [n for n, ok in results if not ok]
    print(json.dumps({"run": run, "passed": len(results) - len(failed), "failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    import sys                                             # the objectives this scenario opened are test data
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from e2e_objectives import close
    close("objectif de test du scénario engine_e8")
    raise SystemExit(rc)
