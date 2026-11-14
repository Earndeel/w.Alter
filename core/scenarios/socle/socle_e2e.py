"""Socle — end-to-end validation of the foundation on the LIVE engine (mission of 2026-11-11, `docs/SOCLE.md`).

The real path, nothing mocked but Telegram's own servers: the door's code (core/interfaces/telegram/bot.py) and the
Engine API talk to the engine in service, which runs the real preflight, Memory, Router and models. A test owner
account (`e2e`, its own conversations) is used: the owner's chats are never touched and every text is synthetic.

  window      A  a conversation that carried heavy tool output: at the next owner message walter-context rewrites the
                 window (measured before/after), the model call is smaller, and what was said is still found
  intent      A  a short follow-up (« vas-y ») is understood inside its conversation: same thread, not a new request
  task        B/D/E  a three-step objective: step 1 done (file written), the engine restarts in the middle of step 2
                 (run closed `interrupted`, objective `suspended`), another interface (Engine API) takes the task up
                 again in a new session and finishes it; the objective follows the thread, not the session
  experience  B  an operation fails; its failure is an execution experience Memory serves to a later conversation
  subagents   C  two delegated subagents in parallel: child runs linked to their parent, results gathered
  degraded    E  the preflight is down: the turn is answered, the context is declared degraded to the model and on the
                 bus (`context.degraded`), never a silent downgrade; the preflight comes back
  deploy      F  every service runs the code on disk, the kernel is the frozen one, contracts hold
Each scenario prints one line; a JSON summary with the measures of every turn (model calls, tool calls, input tokens,
first window, seconds) ends the run. `task` and `degraded` restart services: development instance, quiet moment.

    walter-python core/scenarios/socle/socle_e2e.py [--only window,task] [--out measures.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "v1"))
sys.path.insert(0, str(HERE.parents[2] / "interfaces" / "telegram"))
import bot as B  # noqa: E402
from telegram_door import TEST_USER, RecordingTg  # noqa: E402

API = "http://127.0.0.1:8895"


def sh(*cmd, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--out", default=None, help="write the JSON summary there too")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    root = Path(sh("walter", "instance", "path").stdout.strip())
    token = (root / "bootstrap/engine/api.token").read_text().strip()
    run = uuid.uuid4().hex[:6]
    state_dir = f"/tmp/walter-socle-{run}"
    work = Path(f"/tmp/socle-{run}")
    results: list[tuple[str, bool, str]] = []
    measures: dict[str, list] = {}
    mid = [int(time.time())]
    from walter_memory import db

    # ── the two interfaces ────────────────────────────────────────────────────────────────────────────────────────
    class Chat:
        """One Telegram conversation of the test account, through the door's own code."""

        def __init__(self, base: int):
            self.tg = RecordingTg()
            self.door = B.Bot({"owner_ids": [TEST_USER], "account": "e2e", "grant": "-"}, self.tg,
                              B.Engine(API, token), B.State(f"{state_dir}-{base}"))
            self.chat = base + mid[0] % 1_000_000

        def say(self, text: str, timeout: float = 240, pred=lambda t: bool(t)) -> list[str]:
            n = len(self.tg.calls)
            mid[0] += 1
            self.door.handle({"update_id": mid[0], "message": {"message_id": mid[0], "from": {"id": TEST_USER},
                                                               "chat": {"id": self.chat, "type": "private"}, "text": text}})
            end = time.time() + timeout
            while time.time() < end and not pred(self.tg.texts(n)):
                time.sleep(1)
            return self.tg.texts(n)

        def send(self, text: str) -> int:
            n = len(self.tg.calls)
            mid[0] += 1
            self.door.handle({"update_id": mid[0], "message": {"message_id": mid[0], "from": {"id": TEST_USER},
                                                               "chat": {"id": self.chat, "type": "private"}, "text": text}})
            return n

        @property
        def kernel(self) -> str:
            b = json.loads((root / "state/core/engine/api/bindings.json").read_text())
            return f"dsh/vm/{b['sessions'][self.door.sessions[self.chat]]['kernel']}"

        def close(self):
            self.door.stop.set()

    def api(body: dict, timeout: float = 400) -> tuple[int, dict]:
        req = urllib.request.Request(API + "/v1", data=json.dumps({"version": 1, **body}).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def engine_up(timeout=120) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if api({"op": "health"}, timeout=5)[0] == 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(2)
        return False

    # ── what the engine and Memory recorded (never the test's own opinion) ────────────────────────────────────────
    def q(sql: str, args: tuple = ()) -> list[dict]:
        with db.connect() as c:
            return c.execute(sql, args).fetchall()

    def observations(session: str, kind: str) -> list[dict]:
        out = []
        for day in {dt.datetime.now(dt.timezone.utc).date(), (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).date()}:
            f = root / f"state/core/engine/intake/observations-{day}.jsonl"
            if f.exists():
                for line in f.read_text().splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("session") == session and row.get("kind") == kind:
                        out.append(row)
        return sorted(out, key=lambda r: r.get("at") or "")

    def turns(session: str, settle: float = 6) -> list[dict]:
        """Per turn of a kernel session, from walter_logs: model calls, tool calls, input tokens (new + cached),
        first window, seconds."""
        time.sleep(settle)                                # walter-logs-watch syncs within seconds
        rows = q("""select turn, type, occurred_at, data->'usage' u, status from walter_logs.events
                    where session_id = %s and type in ('assistant/message','tool/call','tool/result','turn/start','turn/end')
                    order by seq""", (session,))
        out: dict[int, dict] = {}
        opened = None                                     # `turn/start` is written before its turn has a number
        for r in rows:
            if r["type"] == "turn/start":
                opened = r["occurred_at"]
                continue
            if r["turn"] is None:                         # the session's opening events
                continue
            t = out.setdefault(r["turn"], {"turn": r["turn"], "calls": 0, "tools": 0, "input": 0, "first_window": None,
                                           "last_window": None, "start": opened, "end": None})
            if r["type"] == "assistant/message":
                u = r["u"] or {}
                size = int(u.get("inputTokens") or 0) + int(u.get("cacheReadTokens") or 0)
                t["calls"] += 1
                t["input"] += size
                t["first_window"] = t["first_window"] if t["first_window"] is not None else size
                t["last_window"] = size
            elif r["type"] == "tool/call":
                t["tools"] += 1
            elif r["type"] == "turn/end":
                t["end"] = r["occurred_at"]
        for t in out.values():
            t["seconds"] = round((t["end"] - t["start"]).total_seconds(), 1) if t["start"] and t["end"] else None
            del t["start"], t["end"]
        return [out[k] for k in sorted(out)]

    def runs_of(session: str) -> list[dict]:
        return q("""select run_id::text, thread_id, act, level, status, outcome, routing->'requested' requested,
                           origin->>'interface' interface, origin->>'request_id' request_id, left(goal, 80) goal
                    from runs.runs where origin->>'session_id' = %s and origin->>'channel' = 'owner'
                    order by started_at""", (session,))

    def objective(marker: str) -> dict | None:
        r = q("""select t.task_id::text, t.status, t.thread_id, t.progress, t.last_outcome,
                        (select count(*) from runs.task_runs tr where tr.task_id = t.task_id) attempts,
                        (select array_agg(distinct r.origin->>'interface') from runs.task_runs tr
                           join runs.runs r on r.run_id = tr.run_id where tr.task_id = t.task_id) interfaces
                 from runs.tasks t where t.kind = 'objective' and t.goal like %s order by t.started_at desc limit 1""",
              (f"%{marker}%",))
        return r[0] if r else None

    def check(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001 - a scenario that crashes is a failed scenario
            ok, info = False, f"{type(e).__name__}: {e}"
        results.append((name, bool(ok), info))
        print(f"{'ok  ' if ok else 'FAIL'} {name:<11} {time.time() - t0:6.1f}s  {info}", flush=True)

    # ── A. the window the model really receives ───────────────────────────────────────────────────────────────────
    def s_window():
        # a controlled heavy tool output: a generated file, its last word asked (the whole output must be read)
        work.mkdir(parents=True, exist_ok=True)

        def attempt(n: int):
            big = work / f"gros-{n}.txt"
            word = f"mirabelle{uuid.uuid4().hex[:4]}"
            big.write_text("".join(f"ligne {i:04d} du jeu d'essai {run} : la fenêtre du tour doit contenir cette sortie en entier\n"
                                   for i in range(1, 801)) + f"dernier mot : {word}\n")
            c = Chat(40_000_000 + n)
            try:
                c.say(f"Test socle {run}. Le but est de remplir ta fenêtre : exécute exactement cette commande bash, sans la "
                      f"modifier, sans autre commande ni autre outil (pas de read, head, tail, grep) : `cat {big}`. "
                      f"Puis réponds seulement « lu-{run} » suivi du dernier mot de la sortie.", timeout=300)
                k = c.kernel
                t2 = " ".join(c.say("Autre sujet, sans rapport et sans outil : combien font 17 × 23 ? Le nombre seul."))
                t3 = " ".join(c.say("Reviens au premier message de cette conversation : quel mot commençant par « lu- » "
                                    "avais-tu répondu, et quelle commande avais-tu exécutée ? Une ligne, sans outil."))
                return k, t2, t3, turns(k)
            finally:
                c.close()

        k, t2, t3, m = attempt(1)
        tries = 1
        if not m or (m[0]["last_window"] or 0) <= 12_000:   # the model did not produce the heavy turn: not exercised
            k, t2, t3, m = attempt(2)
            tries = 2
        measures["window"] = m
        w = [o for o in observations(k, "window") if o.get("turn") == 2]
        w = w[-1] if w else {}
        tok = w.get("tokens") or {}
        heavy, after = (m[0]["last_window"] or 0), (m[1]["first_window"] or 0)
        ok = (bool(w.get("applied")) and tok.get("after", 1e9) < tok.get("before", 0)
              and heavy > 12_000 and after < heavy - 6_000
              and "391" in t2 and f"lu-{run}" in t3.lower() and "cat" in t3.lower())
        return ok, (f"window applied={w.get('applied')} reason={w.get('reason')} record {tok.get('before')}→{tok.get('after')} tok ; "
                    f"model window {heavy}→{after} tok ; 17×23 « {t2[:12]} » ; recalled={f'lu-{run}' in t3.lower()} ; tries={tries}")

    def s_intent():
        c = Chat(41_000_000)
        try:
            c.say(f"Test socle {run} : propose-moi un plan en trois étapes numérotées pour ranger un dossier de photos. "
                  "Ne fais rien, propose seulement, quatre lignes au plus.")
            t = " ".join(c.say("ok vas-y pour la première seulement : décris-la en une phrase, sans outil"))
            k = c.kernel
            time.sleep(3)
            r = runs_of(k)
            measures["intent"] = turns(k)
            o = [x for x in observations(k, "intake")]
            second = r[1] if len(r) > 1 else {}
            # a plain exchange gets its subject from Memory after the fact: when a thread is known it must be the same
            same = second.get("thread_id") == r[0].get("thread_id") if len(r) == 2 else False
            ok = (len(r) == 2 and r[0].get("act") == "new"
                  and second.get("act") in ("continue", "approve", "validate", "correct") and same
                  and bool(o) and o[-1].get("previous_sent") is True and o[-1].get("context_source") == "pack" and bool(t))
            return ok, (f"acts={[x.get('act') for x in r]} same_thread={same} "
                        f"previous_sent={o[-1].get('previous_sent') if o else None} source={o[-1].get('context_source') if o else None}")
        finally:
            c.close()

    # ── B / D / E. a durable task: executed, interrupted by a restart, taken up from another interface ────────────
    def s_task():
        marker = f"tâche-socle-{run}"
        c = Chat(42_000_000)
        try:
            t1 = c.say(f"{marker} : une tâche en trois étapes. 1) écris trois noms d'arbres, un par ligne, dans "
                       f"{work}/arbres.txt ; 2) écris-les triés par ordre alphabétique dans {work}/tries.txt ; "
                       f"3) écris le nombre de lettres de chacun dans {work}/longueurs.txt. Fais seulement l'étape 1 "
                       "maintenant puis arrête-toi : je te dirai quand continuer.", timeout=300)
            k = c.kernel
            step1 = (work / "arbres.txt").exists() and len((work / "arbres.txt").read_text().split()) >= 3
            time.sleep(3)
            o1 = objective(marker)
            # the engine restarts in the middle of step 2
            n = c.send(f"Continue la {marker} : avant l'étape 2, exécute `sleep 90` dans bash, puis fais l'étape 2.")
            time.sleep(25)
            sh("systemctl", "restart", "dsh-web")
            up = engine_up()
            end = time.time() + 90
            while time.time() < end and not c.tg.texts(n):
                time.sleep(1)
            said = c.tg.texts(n)
            time.sleep(8)                                   # the new process closes the orphan run
            r = runs_of(k)
            interrupted = r[-1] if r else {}
            o2 = objective(marker)
            # another interface, a new session: the task is found by its thread, not by the session
            sid = f"api/e2e/socle-{run}"
            api({"op": "session.open", "interface": "api", "conversation": f"socle-{run}",
                 "principal": {"kind": "owner", "id": "e2e"}, "mode": "interactive"})
            # the API door asks its client before a write or a shell command (policy preset `api`): the owner of this
            # session answers, as a real client does — the tools of the errand and its own task state, nothing else
            answered, box = [], {}
            th = threading.Thread(target=lambda: box.update(zip(("s", "body"), api(
                {"op": "turn.submit", "session_id": sid, "channel": "owner", "idempotency_key": f"socle-{run}-resume",
                 "message": {"text": f"Reprends la {marker} là où elle s'est arrêtée et termine-la : fais ce "
                                     "qui reste, puis dis en une ligne ce qui a été fait."}, "wait_ms": 300000}))), daemon=True)
            th.start()
            while th.is_alive():
                for a in (api({"op": "approval.list", "session_id": sid}, timeout=10)[1].get("approvals") or []):
                    verdict = "allow_once" if a.get("tool") in ("bash", "write", "edit", "mcp__walter__task_update") else "deny"
                    api({"op": "approval.answer", "request_id": a["request_id"], "decision": verdict,
                         "principal": {"kind": "owner", "id": "e2e"}}, timeout=10)
                    answered.append(f"{a.get('tool')}:{verdict}")
                th.join(2)
            s, body = box.get("s"), box.get("body") or {}
            res = body.get("result") or {}
            done = (work / "tries.txt").exists() and (work / "longueurs.txt").exists()
            end = time.time() + 240                         # the run's episode closes the objective
            o3 = objective(marker)
            while time.time() < end and (o3 or {}).get("status") not in ("done",):
                time.sleep(5)
                o3 = objective(marker)
            b = json.loads((root / "state/core/engine/api/bindings.json").read_text())
            k2 = f"dsh/vm/{b['sessions'][sid]['kernel']}"
            measures["task"] = turns(k) + turns(k2, settle=0)
            out = interrupted.get("outcome") or {}
            ok = (step1 and o1 and o1["status"] == "open" and up
                  and out.get("status") == "interrupted" and (o2 or {}).get("status") == "suspended"
                  and s == 200 and done and o3 and o3["task_id"] == o1["task_id"]
                  and set(o3["interfaces"] or []) >= {"telegram", "api"} and o3["status"] == "done")
            return ok, (f"step1={step1} objective={o1 and o1['status']} ; restart: said={bool(said)} run={out.get('status')}/"
                        f"{(out.get('error') or {}).get('kind')} objective={(o2 or {}).get('status')} ; api: {res.get('status')} "
                        f"approvals={answered} "
                        f"files={done} same_objective={bool(o3 and o1 and o3['task_id'] == o1['task_id'])} "
                        f"interfaces={o3 and o3['interfaces']} attempts={o3 and o3['attempts']} final={o3 and o3['status']}")
        finally:
            c.close()

    # ── B. execution experience ───────────────────────────────────────────────────────────────────────────────────
    def s_experience():
        target = f"/tmp/socle-absent-{run}.dat"
        ask = f"Opération de test {run} : lis le fichier {target} avec bash (cat) et donne-moi son contenu."
        c = Chat(43_000_000)
        try:
            c.say(ask)
            k = c.kernel
            time.sleep(3)
            first = runs_of(k)[-1]
            end = time.time() + 240                         # the episode of the failed run (bus-driven)
            ep = []
            while time.time() < end and not ep:
                ep = q("select outcome from runs.episodes where run_id = %s order by version desc limit 1", (first["run_id"],))
                time.sleep(5)
            outcome = (ep[0]["outcome"] if ep else None) or {}
            exp = json.loads(sh("walter-memory", "experience", "--thread", first["thread_id"] or "-", "--query", ask
                                ).stdout or "{}")
            items = exp.get("items") if isinstance(exp, dict) else exp
            mine = [i for i in (items or []) if i.get("run_id") == first["run_id"]]
        finally:
            c.close()
        c2 = Chat(44_000_000)                               # later, another conversation asks for the same operation
        try:
            t = " ".join(c2.say(ask + " Si tu sais déjà quelque chose sur cette opération, dis-le en premier."))
            k2 = c2.kernel
            pack = q("""select text from walter_logs.events where session_id = %s and type = 'user/message'
                        and text like '%%Expérience%%' limit 1""", (k2,))
            measures["experience"] = turns(k) + turns(k2, settle=0)
            knows = any(w in t.lower() for w in ("déjà", "précédent", "tout à l'heure", "auparavant", "dernière fois", "tentative"))
            # the kernel does not flag a non-zero exit as a tool error: the failure is read from the traces (episode)
            ok = (outcome.get("status") in ("failed", "partial", "blocked") and bool(outcome.get("errors")) and bool(mine)
                  and bool(pack) and knows)
            return ok, (f"run tool_errors={(first['outcome'] or {}).get('tool_errors')} episode={outcome.get('status')} "
                        f"errors={len(outcome.get('errors') or [])} served={bool(mine)} in_pack={bool(pack)} said_known={knows}")
        finally:
            c2.close()

    # ── C. orchestration ──────────────────────────────────────────────────────────────────────────────────────────
    def s_subagents():
        c = Chat(45_000_000)
        try:
            t = " ".join(c.say(f"Test socle {run} : délègue à deux sous-agents en parallèle, sans rien chercher toi-même : "
                               "l'un donne la capitale de l'Australie, l'autre la capitale du Canada. Rassemble leurs "
                               f"deux réponses en une ligne qui commence par « capitales-{run} ».", timeout=420,
                               pred=lambda t: any(f"capitales-{run}" in x for x in t)))
            k = c.kernel
            time.sleep(5)
            parent = runs_of(k)[-1]
            kids = q("""select run_id::text, status, origin->>'channel' channel, outcome->>'status' outcome
                        from runs.runs where parent_run_id = %s""", (parent["run_id"],))
            measures["subagents"] = turns(k)
            ok = ("canberra" in t.lower() and "ottawa" in t.lower() and len(kids) >= 2
                  and all(x["status"] in ("ended", "ok") or x["outcome"] == "ok" for x in kids))
            return ok, f"children={len(kids)} {sorted({str(x['outcome']) for x in kids})} « {t[:70]} »"
        finally:
            c.close()

    # ── E. the preflight is down: explicit degraded context ───────────────────────────────────────────────────────
    def s_degraded():
        c = Chat(46_000_000)
        since = dt.datetime.now(dt.timezone.utc)
        try:
            sh("systemctl", "stop", "walter-context-preflight")
            t = " ".join(c.say(f"Test socle {run} : réponds seulement « dégradé-{run} », sans outil."))
            k = c.kernel
        finally:
            sh("systemctl", "start", "walter-context-preflight")
            c.close()
        time.sleep(3)
        o = observations(k, "intake")
        r = runs_of(k)
        bus = q("select count(*) n from bus.events where type = 'context.degraded' and at >= %s and payload->>'run_id' = %s",
                (since, r[-1]["run_id"] if r else "-"))
        told = q("""select count(*) n from walter_logs.events where session_id = %s and type = 'user/message'
                    and text ilike '%%dégradé%%' and text not like 'Test socle%%'""", (k,))
        back = False
        for _ in range(30):                                 # the preflight answers again
            try:
                with urllib.request.urlopen("http://127.0.0.1:8897/health", timeout=3) as h:
                    back = h.status == 200
                    break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        measures["degraded"] = turns(k)
        src = o[-1].get("context_source") if o else None
        ok = (f"dégradé-{run}" in t.lower() and str(src).endswith("_degraded") and bus[0]["n"] >= 1 and told[0]["n"] >= 1 and back)
        return ok, f"answered={f'dégradé-{run}' in t.lower()} source={src} bus={bus[0]['n']} told_model={told[0]['n']} preflight_back={back}"

    # ── F. what runs is what is on disk ───────────────────────────────────────────────────────────────────────────
    def s_deploy():
        d = json.loads(sh("walter", "deploy", "check", "--json").stdout or "{}")
        kern = sh("walter", "engine", "kernel")
        try:
            kernel_ok = bool(json.loads(kern.stdout).get("ok"))
        except ValueError:
            kernel_ok = kern.returncode == 0
        chk = sh("walter", "check", timeout=300).returncode
        con = sh("walter", "contracts", "check", timeout=300).returncode
        ok = d.get("ok") is True and not d.get("stale") and kernel_ok and chk == 0 and con == 0
        return ok, (f"services={len(d.get('services') or [])} stale={[s if isinstance(s, str) else s.get('unit') for s in d.get('stale') or []]} "
                    f"kernel={kernel_ok} check={chk} contracts={con}")

    for name, fn in (("deploy", s_deploy), ("window", s_window), ("intent", s_intent), ("experience", s_experience),
                     ("subagents", s_subagents), ("degraded", s_degraded), ("task", s_task)):
        check(name, fn)
    # the objectives this run opened are test data: closed (cancelled, never deleted) so they are not proposed to
    # the owner's real conversations (shared with the V1 scenarios: core/scenarios/e2e_objectives.py)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from e2e_objectives import close
    close(f"objectif de test de la suite socle ({run})")
    failed = [n for n, ok, _ in results if not ok]
    summary = {"run": run, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "passed": len(results) - len(failed), "failed": failed,
               "results": [{"name": n, "ok": ok, "info": i} for n, ok, i in results], "measures": measures}
    print(json.dumps(summary, ensure_ascii=False, default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
