"""A7 round 2: train L2 on Luna-labelled RAW messages (disjoint from the 600-item bench), calibrate, test; per-class
metrics + macro-F1 for L2, Jev and the hybrid (L2 decides, abstentions escalate to Jev)."""
import concurrent.futures as cf, json, random, sys
from pathlib import Path
sys.path.insert(0, "/opt/walter-memory"); sys.path.insert(0, "/opt/walter-memory/bench")
import numpy as np
from router_bench import label, OUT
from walter_memory import router
from walter_memory.db import connection
TRAIN = Path("/opt/walter-memory/bench/router_train_labels.jsonl")
bench = [json.loads(l) for l in OUT.open()]
if not TRAIN.exists():
    used = {b["event_id"] for b in bench}
    with connection() as conn:
        rows = conn.execute("""select event_id::text, event_type, content from core.events
                               where source = 'hermes' and event_type in ('message.sent','message.received')
                                 and privacy_class = 'cloud_allowed' and length(content) between 3 and 6000""").fetchall()
    random.seed(1); rows = [r for r in rows if r["event_id"] not in used]; random.shuffle(rows); rows = rows[:6000]
    batches = [rows[i:i + 25] for i in range(0, len(rows), 25)]
    with cf.ThreadPoolExecutor(8) as ex:
        labs = list(ex.map(lambda b: label(b, "openai/gpt-6-luna", "xhigh", "router.train.label"), batches))
    with TRAIN.open("w") as f:
        for b, ls in zip(batches, labs):
            for r, l in zip(b, ls):
                if l: f.write(json.dumps({**r, "label": l}, ensure_ascii=False) + "\n")
train = [json.loads(l) for l in TRAIN.open()]
print("train:", len(train), {d: sum(x["label"] == d for x in train) for d in router.DESTS})
from sklearn.linear_model import LogisticRegression
X = router.features([x["content"] for x in train]); y_tr = [x["label"] for x in train]
clf = LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced").fit(X, y_tr)
router.Router(clf).save()
random.seed(7); random.shuffle(bench); cal, test = bench[:len(bench)//2], bench[len(bench)//2:]
router.calibrate([x["content"] for x in cal], [x["label"] for x in cal], threshold_precision=0.85)
r = router.Router.load(); y = np.array([x["label"] for x in test])
P = r.proba([x["content"] for x in test]); pred = np.array(router.DESTS)[P.argmax(1)]; conf = P.max(1); dec = conf >= r.threshold
def report(name, p):
    f1s = []
    line = []
    for d in router.DESTS:
        tp = np.sum((p == d) & (y == d)); pr = tp / max(1, np.sum(p == d)); rc = tp / max(1, np.sum(y == d))
        f1 = 2 * pr * rc / max(1e-9, pr + rc); f1s.append(f1); line.append(f"{d} P{pr:.2f}/R{rc:.2f}")
    print(f"{name:22} acc {np.mean(p == y):.2f}  macroF1 {np.mean(f1s):.2f} | " + "  ".join(line))
report("L2 (raw-trained, cal.)", pred)
print(f"   threshold {r.threshold:.2f}  coverage {dec.mean():.2f}  precision-on-decided {np.mean(pred[dec]==y[dec]) if dec.any() else 0:.2f}")
batches = [test[i:i + 20] for i in range(0, len(test), 20)]
with cf.ThreadPoolExecutor(6) as ex:
    jp = np.array([l or "index_only" for l in sum(ex.map(lambda b: label(b, "typesafe/jev-router", None, "router.bench.jev2"), batches), [])])
report("Jev", jp)
report("L2 + abstain→Jev", np.where(dec, pred, jp))
report("majority (index_only)", np.array(["index_only"] * len(y)))
with connection() as conn:
    print(conn.execute("""select processor, round(sum(cost_usd)::numeric,3) usd from system.model_calls where processor like 'router.%%' group by 1""").fetchall())
