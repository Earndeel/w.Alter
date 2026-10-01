"""P5 / A7 — independent router benchmark on raw events (not the Hindsight facts the L2 model is trained on).

1. sample 600 W.Alter conversation messages (cloud_allowed only; third-party sources wait for D5 validation)
2. label them with a strong model (GPT-6 Luna) → bench/router_labels.jsonl
3. train L2 on Luna fact labels, calibrate on half of the bench, evaluate on the other half; compare with Jev.
"""
import concurrent.futures as cf, json, random, sys, time
from pathlib import Path
sys.path.insert(0, "/opt/walter-memory")
import numpy as np
from walter_memory import llm, router
from walter_memory.db import connection

OUT = Path("/opt/walter-memory/bench/router_labels.jsonl")
DEFS = """Destinations possibles pour un message d'une conversation entre Monsieur (l'utilisateur) et son assistant W.Alter :
- memory : contient un fait durable sur Monsieur (identité, lieu, santé, goûts, habitudes), ses projets/entreprises (objectif, statut, décisions et raisons) ou une règle/préférence sur la façon dont W.Alter doit agir.
- social : contient une information substantielle sur une autre personne (qui elle est, relation avec Monsieur, événement marquant).
- index_only : utile seulement pour retrouver plus tard (détails techniques, configs, code, comptes rendus d'exécution, discussion de tâche ponctuelle) mais pas à mémoriser.
- ignore : aucun contenu durable (politesse, accusé de réception, bavardage, message vide de sens)."""


def sample(n=600):
    with connection() as conn:
        rows = conn.execute("""select event_id::text, event_type, content from core.events
                               where source = 'hermes' and event_type in ('message.sent','message.received')
                                 and privacy_class = 'cloud_allowed' and length(content) between 3 and 6000""").fetchall()
    random.seed(42)
    sent = [r for r in rows if r["event_type"] == "message.sent"]
    recv = [r for r in rows if r["event_type"] == "message.received"]
    return random.sample(sent, n // 2) + random.sample(recv, n // 2)


def label(batch, model, effort=None, processor="router.bench.label"):
    txt = "\n".join(f"{i+1}. [{'Monsieur' if r['event_type']=='message.sent' else 'W.Alter'}] {r['content'][:700]}" for i, r in enumerate(batch))
    prompt = DEFS + "\n\nClasse chaque message dans UNE destination. Réponds uniquement en JSON {\"labels\": [\"...\", ...]} dans l'ordre.\n\n" + txt
    kw = {"reasoning": {"effort": effort}} if effort else {"temperature": 0}
    for _ in range(3):
        try:
            c = llm.chat([{"role": "user", "content": prompt}], model=model, processor=processor, privacy_class="cloud_allowed",
                         budget="backfill", response_format={"type": "json_object"}, max_tokens=12000, **kw)["content"]
            labs = json.loads(c[c.find("{"):c.rfind("}") + 1])["labels"]
            if len(labs) == len(batch):
                return [l if l in router.DESTS else "index_only" for l in labs]
        except Exception as e:
            err = e
    return [None] * len(batch)


if __name__ == "__main__":
    if not OUT.exists():
        rows = sample()
        batches = [rows[i:i + 20] for i in range(0, len(rows), 20)]
        with cf.ThreadPoolExecutor(6) as ex:
            labs = list(ex.map(lambda b: label(b, "openai/gpt-6-luna", "xhigh"), batches))
        with OUT.open("w") as f:
            for b, ls in zip(batches, labs):
                for r, l in zip(b, ls):
                    if l:
                        f.write(json.dumps({**r, "label": l}, ensure_ascii=False) + "\n")
    data = [json.loads(l) for l in OUT.open()]
    random.seed(7); random.shuffle(data)
    cal, test = data[: len(data) // 2], data[len(data) // 2:]
    print("bench:", len(data), {d: sum(x["label"] == d for x in data) for d in router.DESTS})

    t0 = time.time(); info = router.train(); print("L2 trained:", info, f"{time.time()-t0:.0f}s")
    r = router.Router.load()
    y = np.array([x["label"] for x in test]); texts = [x["content"] for x in test]
    P = r.proba(texts); pred = np.array(router.DESTS)[P.argmax(1)]
    print(f"L2 raw (trained on facts only): acc {np.mean(pred == y):.2f}")
    thr = router.calibrate([x["content"] for x in cal], [x["label"] for x in cal]); r = router.Router.load()
    P = r.proba(texts); pred = np.array(router.DESTS)[P.argmax(1)]; conf = P.max(1)
    bins = np.linspace(0, 1, 11); ece = sum(abs(np.mean(pred[(conf >= lo) & (conf < hi)] == y[(conf >= lo) & (conf < hi)]) -
                                                np.mean(conf[(conf >= lo) & (conf < hi)])) * np.mean((conf >= lo) & (conf < hi))
                                            for lo, hi in zip(bins[:-1], bins[1:]) if np.any((conf >= lo) & (conf < hi)))
    dec = conf >= r.threshold
    print(f"L2 calibrated: acc {np.mean(pred == y):.2f}  ECE {ece:.3f}  threshold {r.threshold:.2f}  "
          f"coverage {np.mean(dec):.2f}  precision-on-decided {np.mean(pred[dec] == y[dec]) if dec.any() else 0:.2f}")
    for d in router.DESTS:
        tp = np.sum((pred == d) & (y == d)); print(f"   {d:10} P {tp / max(1, np.sum(pred == d)):.2f}  R {tp / max(1, np.sum(y == d)):.2f}")
    t0 = time.time()
    batches = [test[i:i + 20] for i in range(0, len(test), 20)]
    with cf.ThreadPoolExecutor(6) as ex:
        jl = sum(ex.map(lambda b: label(b, "typesafe/jev-router", None, "router.bench.jev"), batches), [])
    jp = np.array([l or "index_only" for l in jl])
    print(f"Jev: acc {np.mean(jp == y):.2f}  ({time.time()-t0:.0f}s wall for {len(test)} items, batched)")
    with connection() as conn:
        cost = conn.execute("""select processor, round(sum(cost_usd)::numeric, 3) usd, count(*) calls from system.model_calls
                               where processor like 'router.bench%%' group by 1""").fetchall()
    print("cost:", cost)
    hybrid = np.where(dec, pred, jp)
    print(f"L2 + abstention→Jev: acc {np.mean(hybrid == y):.2f}  (Jev called on {np.mean(~dec):.0%} of items)")
