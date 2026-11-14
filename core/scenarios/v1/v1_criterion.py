"""Walter V1 — the acceptance criterion on Telegram, its 9 steps checked in the traces (2026-11-10).

« Recherche trois options pour accomplir cette tâche, compare-les, choisis la meilleure et prépare le résultat » goes
through the Telegram door's own code (Bot API simulated, engine real, test owner account `e2e`), then the traces show
that Walter Engine alone did each step:
  1 receive      the door submitted the message; the engine opened a run for it (Run Plane)
  2 understand   the preflight plan written on the run (task, level)
  3 context      walter-context's block entered the turn (memory, preferences, owner rules)
  4 choose       Router-chosen model(s) on the run's model calls (models.exec_log), tools called
  5 delegate     the `subagent` tool ran, child runs carry this run as parent
  6 act          the authorised actions ran (tool results, the result file exists), none refused by policy
  7 report       the answer reached Telegram
  8 keep         the conversation is in walter_logs and core.events, the run is closed (its episode follows)
  9 find again   a NEW conversation finds the task and the chosen option
`--session telegram/<account>/chat-<id>` checks a conversation that already happened (the owner's own), read only:
steps 1–8 of its latest V1 run, nothing sent. Costs a few model turns and sub-agents when it runs the request.

    walter-python core/scenarios/v1/v1_criterion.py [--session SID] [--wait-memory 120]
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

PHRASE = "Recherche trois options pour accomplir cette tâche, compare-les, choisis la meilleure et prépare le résultat"


def db():
    from walter_memory import db as d
    return d.connect()


def kernel_of(root: Path, sid: str) -> str:
    b = json.loads((root / "state/core/engine/api/bindings.json").read_text())
    return "dsh/vm/" + b["sessions"][sid]["kernel"]


def trace(root: Path, sid: str) -> dict:
    """Aggregates of the latest V1 run of a door conversation: never the owner's texts."""
    k = kernel_of(root, sid)
    with db() as c:
        run = c.execute("""select run_id, status, routing, level, act from runs.runs where origin->>'session_id' = %s
                           and goal like %s order by started_at desc limit 1""", (k, PHRASE[:40] + "%")).fetchone()
        if not run:
            return {"session": k, "run": None}
        rid = run["run_id"]
        ev = c.execute("""select type, tool, status, text, seq from walter_logs.events where session_id = %s
                          and seq >= (select min(seq) from walter_logs.events where session_id = %s and type = 'user/message'
                                      and text like %s) order by seq""", (k, k, PHRASE[:40] + "%")).fetchall()
        children = c.execute("select run_id, status from runs.runs where parent_run_id = %s and origin->>'channel' = 'machine'",
                             (rid,)).fetchall()
        models = c.execute("""select model_id, provider, task, ok from models.exec_log where run_id = any(%s)""",
                           ([rid, *[ch["run_id"] for ch in children]],)).fetchall()
        core_n = c.execute("""select count(*) n from core.events where source = 'dsh'
                              and (payload->>'session_id' = %s or thread_id = %s)""",
                           (k.split("/")[-1], k.split("/")[-1])).fetchone()["n"]
        episode = c.execute("select count(*) n from runs.links where run_id = %s and kind = 'episode'", (rid,)).fetchone()["n"]
    turn_end = next((i for i, e in enumerate(ev) if e["type"] == "turn/end"), len(ev))
    turn = ev[:turn_end + 1]
    tools = [e["tool"] for e in turn if e["type"] == "tool/call"]
    results = [e for e in turn if e["type"] == "tool/result"]
    refused = [e for e in results if (e["text"] or "").lower().startswith(("denied", "refus", "blocked", "not allowed"))]
    return {"session": k, "run": str(rid), "status": run["status"], "requested": (run["routing"] or {}).get("requested"),
            "level": run["level"], "context": any((e["text"] or "").startswith("<walter-context>\nContexte préparé")
                                                   for e in turn if e["type"] == "user/message"),
            "tools": tools, "results": len(results), "refused": len(refused),
            "children": [{"run": str(ch["run_id"]), "status": ch["status"]} for ch in children],
            "models": sorted({f"{m['model_id']}@{m['provider']}" for m in models if m["ok"]}),
            "model_calls": len(models), "logged": len(ev), "core_events": core_n, "episode": episode}


def found_choice(chosen: str, later: str) -> bool:
    """The option chosen in the first conversation is named again (one of its distinctive words)."""
    import re
    words = {w for w in re.findall(r"[\w.-]{5,}", chosen.lower()) if w not in ("option", "choix", "retenue", "chaîne")}
    return bool(words) and any(w in later.lower() for w in words)


def judge(t: dict, delivered: bool, result_file: bool | None) -> list[tuple[str, bool, str]]:
    req = t.get("requested") or {}
    acts = [x for x in t.get("tools", []) if x not in ("subagent",)]
    return [
        ("1 reçu", bool(t.get("run")), f"run {t.get('run')}"),
        ("2 compris", bool(req.get("task")), f"plan {req.get('task')}/{req.get('level')} niveau {t.get('level')}"),
        ("3 contexte", bool(t.get("context")), "bloc walter-context dans le tour" if t.get("context") else "absent"),
        ("4 modèles+outils", bool(t.get("models")) and bool(t.get("tools")),
         f"{', '.join(t.get('models', [])) or '—'} ; outils {sorted(set(t.get('tools', [])))}"),
        ("5 sous-agents", "subagent" in t.get("tools", []) and bool(t.get("children")),
         f"{t.get('tools', []).count('subagent')} appels, {len(t.get('children', []))} runs enfants"),
        ("6 actions", bool(acts) and t.get("refused", 0) == 0 and result_file is not False,
         f"{len(acts)} actions, {t.get('refused')} refusées, fichier résultat {result_file}"),
        ("7 résultat", delivered, "réponse livrée sur Telegram" if delivered else "aucune réponse"),
        ("8 garder", t.get("logged", 0) > 0 and t.get("core_events", 0) > 0 and t.get("status") != "open",
         f"walter_logs {t.get('logged')}, core.events {t.get('core_events')}, run {t.get('status')}, épisode {t.get('episode')}"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="check an existing door conversation (read only)")
    ap.add_argument("--wait-memory", type=int, default=120, help="seconds before step 9 (ingestion)")
    a = ap.parse_args()
    root = Path(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True).stdout.strip())
    if a.session:
        t = trace(root, a.session)
        steps = judge(t, delivered=t.get("status") == "ended", result_file=None)
        for name, ok, info in steps:
            print(f"{'ok  ' if ok else 'FAIL'} {name:<17} {info}")
        print(json.dumps({"session": a.session, "passed": sum(ok for _, ok, _ in steps), "of": len(steps)}))
        return 0 if all(ok for _, ok, _ in steps) else 1

    token = (root / "bootstrap/engine/api.token").read_text().strip()
    run = uuid.uuid4().hex[:6]
    tg = RecordingTg()
    door = B.Bot({"owner_ids": [TEST_USER], "account": "e2e", "grant": "-"}, tg,
                 B.Engine("http://127.0.0.1:8895", token), B.State(f"/tmp/walter-v1-{run}"))
    chat = 40_000_000 + int(time.time()) % 1_000_000
    mid = [int(time.time())]

    def say(text):
        mid[0] += 1
        door.handle({"update_id": mid[0], "message": {"message_id": mid[0], "from": {"id": TEST_USER},
                                                      "chat": {"id": chat, "type": "private"}, "text": text}})

    def final(since, timeout):
        """The turn's answer: the first non-status text after the turn ended."""
        end = time.time() + timeout
        while time.time() < end:
            sid = door.sessions.get(chat)
            if sid and sid not in door.turns and tg.texts(since):
                return tg.texts(since)
            time.sleep(2)
        return tg.texts(since)

    out_file = f"{root}/workspace/e2e/resultat-v1-{run}.md"     # inside the engine's workspace: no approval
    t0 = time.time()
    say(f"{PHRASE}. Tâche : convertir des notes Markdown en PDF sur ce serveur, avec un outil libre, sans rien "
        f"installer pour l'instant. Fais étudier les trois options en parallèle par des sous-agents. Prépare le résultat "
        f"dans le fichier {out_file} (comparatif court + choix motivé). Commence ta réponse par « Choix : <nom de "
        f"l'option retenue> ».")
    final(0, 900)
    answer = [p["text"] for m, p in tg.calls if m == "sendMessage" and not p["text"].startswith("⏳")]
    sid = door.sessions[chat]
    delivered = any(x.strip() for x in answer)
    chosen = next((x.split("Choix", 1)[1].strip(" :*")[:60] for x in answer if "Choix" in x), "")
    print(f"  tour V1 : {time.time() - t0:.0f}s, réponse « {' '.join(answer)[:100]} »", flush=True)
    time.sleep(10)
    t = trace(root, sid)
    steps = judge(t, delivered, Path(out_file).is_file())

    # 9: later, in a new conversation, the task and the choice are found again
    time.sleep(a.wait_memory)
    n = len(tg.calls)
    say("/nouveau")
    n = len(tg.calls)
    say("Tout à l'heure, dans une autre conversation, je t'ai demandé de comparer trois options pour une tâche. "
        "Quelle était la tâche, et quelle option as-tu retenue ? Deux lignes.")
    later = " ".join(final(n, 300)).lower()
    found = "pdf" in later and found_choice(chosen, later)
    steps.append(("9 retrouver", found, f"choix « {chosen[:30]} » ; réponse « {later[:90]} »"))
    door.stop.set()
    for name, ok, info in steps:
        print(f"{'ok  ' if ok else 'FAIL'} {name:<17} {info}", flush=True)
    print(json.dumps({"run": run, "session": sid, "trace": {k: v for k, v in t.items() if k != "tools"},
                      "passed": sum(ok for _, ok, _ in steps), "of": len(steps)}, ensure_ascii=False, default=str))
    return 0 if all(ok for _, ok, _ in steps) else 1


if __name__ == "__main__":
    rc = main()
    import sys                                             # the objectives this scenario opened are test data
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from e2e_objectives import close
    close("objectif de test du scénario v1_criterion")
    raise SystemExit(rc)
