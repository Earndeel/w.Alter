"""Eval of decision models on Walter Router's intent task (eval/intents_fr.json: request, expected task, expected video
role or null). Usage: venv/bin/python eval/decision_models.py MODEL [MODEL...]  → accuracy, latency, cost per model."""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_router import db, intent  # noqa: E402

CASES = json.loads((Path(__file__).parent / "intents_fr.json").read_text())


def run(model: str) -> dict:
    intent.ACCEPTED_PREFIXES = (model.split(":")[0].lstrip("~").rsplit("-latest", 1)[0], model)
    ok_task = ok_role = n_role = errors = 0
    ms, costs, misses = [], [], []
    with db.connect() as conn:
        for request, task, role in CASES:
            try:
                r = intent.classify(conn, request, timeout=20, models=(model,))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                misses.append(f"ERR {request[:40]}: {exc}"[:120])
                continue
            ms.append(r["ms"]); costs.append(r["cost"] or 0)
            if r["task"] == task:
                ok_task += 1
            else:
                misses.append(f"{request[:50]} → {r['task']} (attendu {task}, conf {r['task_confidence']:.2f})")
            if role:
                n_role += 1
                ok_role += r["video_role"] == role
            time.sleep(0.2)
    return {"model": model, "task": f"{ok_task}/{len(CASES)}", "video_role": f"{ok_role}/{n_role}", "errors": errors,
            "median_ms": statistics.median(ms) if ms else None, "cost_30": round(sum(costs), 6), "misses": misses}


if __name__ == "__main__":
    for m in sys.argv[1:]:
        print(json.dumps(run(m), ensure_ascii=False), flush=True)
