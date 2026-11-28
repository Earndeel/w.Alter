#!/usr/bin/env python3
"""g0 audit (2026-11-10 mandate, step 1): what the pre-V1 generation really holds, item by item, and what of it is
unique.

  walter-python bench/g0_audit.py features            local only (no model): provenance, coverage, redundancy
  walter-python bench/g0_audit.py label [--n 1600]    a stratified sample labelled by Walter Router (poste
                                                      memory_extraction), memoised per item in processing.decisions
  walter-python bench/g0_audit.py verify [--n 300]    independent second opinion (decision chain, llm.decide)
  walter-python bench/g0_audit.py extend              local classifier trained on the labels → every item, with
                                                      cross-validated accuracy
  walter-python bench/g0_audit.py report              aggregates (population estimates with 95 % intervals)

Classes (Monsieur, 2026-11-10): personal (identity, preferences — incl. how he wants to be served —, relations, habits,
experiences, goals, life projects), other_project (his projects other than Walter), walter_durable (vision, current
architecture, structuring decisions, technical choices, important incidents, lessons, existing features),
walter_historical (former architectures, replaced work, abandoned attempts, past fixes, experiments), noise (logs,
rephrasings, repetitive observations, tests, redundant or useless). Plus validity (current / stale / unknown) and
durable value (0-2).

Read-only on memory. Everything per item (ids, labels, scores: never content) lives in the instance:
`walter instance path state memory`/bench/g0_audit/ (0600). Prints aggregates only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROCESSOR, VERSION = "bench.g0_audit", "1"
CLASSES = ("personal", "other_project", "walter_durable", "walter_historical", "noise")
SHORT = {"P": "personal", "O": "other_project", "D": "walter_durable", "H": "walter_historical", "N": "noise"}
TEXT_CHARS = 420
BATCH = 40

STATE_BRIEF = """État actuel de Walter (10/11/2026), pour juger si un élément technique est encore valide :
- Mémoire : Walter Memory (Postgres, core.events + Raw Vault = vérité durable ; Kardex = schéma social ; Memory V1
  « organique » g1 depuis le 02/11 ; g0 = interprétations d'avant). Hindsight, Qdrant, hybrid-search, voice/Asterisk,
  walter-compress, dream-cycle, jarvis-memory-gateway, Miroshark : retirés.
- Runtime : Hermes reste en service mais la cible est un runtime unique (moteur DSH/Cordis dans walter/core/engine) ;
  Claude Code et Codex = outils de développement externes via MCP.
- Modules dans /walter (router + gateway walter-llm, context, skills, browse, computer, secrets, soul, ops, memory),
  instance personnelle /user/Lucas, projets /projects, applications /apps, services /services.
- Aucun module ne fige un modèle : Walter Router choisit le modèle de chaque poste."""

PROMPT = """Tu audites l'ancienne mémoire (g0) de Walter, l'assistant personnel de Monsieur. Chaque élément ci-dessous est une
connaissance dérivée de ses conversations avec Walter avant novembre 2026. La plupart de ces conversations portaient sur
la construction de Walter lui-même.

{brief}

Pour chaque élément, donne :
- c : la classe, selon son CONTENU (pas son origine) :
  P = personnel : identité, préférences (y compris sur la façon dont Monsieur veut être servi ou qu'on travaille avec
      lui), relations, habitudes, expériences, objectifs, projets de vie, tout ce qui aide à comprendre Monsieur ;
  O = un autre projet de Monsieur que Walter (site, application, client, activité…) ;
  D = Walter, durable : vision, architecture actuelle, décision structurante, choix technique encore en vigueur,
      incident important, enseignement, fonctionnalité existante ;
  H = Walter, historique : ancienne architecture, développement remplacé, tentative abandonnée, correction ou
      expérience passée, état transitoire ;
  N = bruit : trace de log, reformulation sans information, observation répétitive, test, contenu vide ou inutile.
  Si un élément mêle une préférence de Monsieur et un détail technique, la préférence l'emporte (P).
- v : validité aujourd'hui : "c" (toujours vraie ou intemporelle), "s" (périmée / remplacée), "u" (impossible à dire).
- u : valeur durable pour comprendre Monsieur ou faire fonctionner Walter : 0 (aucune), 1 (utile), 2 (importante).

Réponds uniquement en JSON : {{"items": [{{"n": 1, "c": "P", "v": "c", "u": 2}}, ...]}} avec un objet par élément,
dans l'ordre.

Éléments :
{items}"""


# ---------------------------------------------------------------------------------------------------------------
def out_dir() -> Path:
    if os.environ.get("WALTER_BENCH_DIR"):
        d = Path(os.environ["WALTER_BENCH_DIR"])
    else:
        p = subprocess.run(["walter", "instance", "path", "state", "memory"], capture_output=True, text=True,
                           timeout=10).stdout.strip()
        if not p:
            sys.exit("instance state path unknown: set WALTER_BENCH_DIR")
        d = Path(p) / "bench" / "g0_audit"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def save(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, default=str))
    tmp.chmod(0o600)
    tmp.replace(path)


def vec(text: str | None) -> np.ndarray | None:
    if not text:
        return None
    return np.array(json.loads(text), dtype=np.float32)


def load_items() -> list[dict]:
    from walter_memory.db import connection
    with connection() as conn:
        rows = conn.execute("""
            select d.item_id::text id, d.kind, d.derived_by, d.status, d.privacy_class, d.created_at, d.valid_from,
                   d.content, d.attributes->>'usefulness' usefulness, d.attributes->>'quarantined' quarantined,
                   d.attributes->>'proof_count' proof_count, d.attributes->>'fact_type' fact_type,
                   d.attributes->>'category' category, d.attributes->>'inject_policy' inject_policy,
                   cardinality(d.source_event_ids) n_events, d.source_event_ids[1]::text first_event,
                   c.embedding::text emb, c.hidden, c.dup_of is not null is_dup
            from core.derived_items d
            left join search.chunks c on c.ref_id::text = d.item_id::text and c.kind = 'derived' and c.chunk_no = 0
            where d.generation = 'g0' order by d.item_id""").fetchall()
    return [dict(r) for r in rows]


def archive_classes() -> dict[str, tuple[str, str]]:
    """item → (class, rule) from the phase 0 archive (thread-level rules of 2026-11-09, computed while the tool calls
    that identify a thread's project still existed). Decrypted in memory only."""
    base = Path("/user/Lucas/backups/memory-archive/2026-11-09-phase0")
    key = subprocess.run(["walter", "instance", "path", "bootstrap", "vault", "walter-recovery.agekey"],
                         capture_output=True, text=True, timeout=10).stdout.strip() \
        or "/user/Lucas/bootstrap/vault/walter-recovery.agekey"
    out: dict[str, tuple[str, str]] = {}
    for part in ("project", "personal"):
        f = base / part / "knowledge.jsonl.zst.age"
        if not f.exists():
            continue
        age = subprocess.Popen(["age", "-d", "-i", key, str(f)], stdout=subprocess.PIPE)
        z = subprocess.Popen(["zstd", "-dc"], stdin=age.stdout, stdout=subprocess.PIPE)
        for line in z.stdout:
            r = json.loads(line)
            if r.get("generation") == "g0":
                out[r["item_id"]] = (r.get("class") or "unclassified", r.get("rule") or "")
        z.wait()
        age.wait()
    return out


# ---------------------------------------------------------------------------------------------------------------
def features(_a) -> None:
    from walter_memory.db import connection
    d = out_dir()
    items = load_items()
    arch = archive_classes()
    with connection() as conn:
        g1 = conn.execute("""select c.ref_id::text id, c.label, c.embedding::text emb from search.chunks c
                             where c.generation = 'g1' and c.chunk_no = 0 and not c.hidden""").fetchall()
    docs = [r for r in g1 if r["label"] == "doc_section"]
    know = [r for r in g1 if r["label"] != "doc_section"]
    idx = [i for i, it in enumerate(items) if it["emb"]]
    G0 = np.stack([vec(items[i]["emb"]) for i in idx])
    G0 /= np.linalg.norm(G0, axis=1, keepdims=True) + 1e-9

    def best(ref):
        if not ref:
            return np.zeros(len(idx)), [None] * len(idx)
        M = np.stack([vec(r["emb"]) for r in ref])
        M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
        sims, args = np.zeros(len(idx)), np.zeros(len(idx), dtype=int)
        for s in range(0, len(idx), 4096):
            S = G0[s:s + 4096] @ M.T
            args[s:s + 4096] = S.argmax(1)
            sims[s:s + 4096] = S.max(1)
        return sims, [ref[a]["id"] for a in args]

    s_know, a_know = best(know)
    s_docs, a_docs = best(docs)
    # within-g0 redundancy: neighbours above 0.92 (paraphrases of one memory)
    dup_n = np.zeros(len(idx), dtype=int)
    for s in range(0, len(idx), 2048):
        S = G0[s:s + 2048] @ G0.T
        dup_n[s:s + 2048] = (S >= 0.92).sum(1) - 1
    feats = {}
    for it in items:
        ac = arch.get(it["id"], ("unarchived", ""))
        feats[it["id"]] = {"kind": it["kind"], "by": it["derived_by"], "status": it["status"],
                           "privacy": it["privacy_class"], "created": it["created_at"].date().isoformat(),
                           "indexed": bool(it["emb"]), "hidden": bool(it["hidden"]), "dup": bool(it["is_dup"]),
                           "events": it["n_events"], "usefulness": it["usefulness"],
                           "quarantined": it["quarantined"], "proof": it["proof_count"],
                           "fact_type": it["fact_type"], "category": it["category"],
                           "inject_policy": it["inject_policy"], "chars": len(it["content"] or ""),
                           "archive_class": ac[0], "archive_rule": ac[1],
                           "content_sha": hashlib.sha256((it["content"] or "").encode()).hexdigest()[:16]}
    for j, i in enumerate(idx):
        f = feats[items[i]["id"]]
        f.update(cov_g1=round(float(s_know[j]), 3), cov_g1_ref=a_know[j], cov_docs=round(float(s_docs[j]), 3),
                 cov_docs_ref=a_docs[j], g0_neighbours=int(dup_n[j]))
    sha_n = Counter(f["content_sha"] for f in feats.values())
    for f in feats.values():
        f["exact_copies"] = sha_n[f["content_sha"]] - 1
    save(d / "features.json", feats)
    agg = {"items": len(feats), "indexed": len(idx), "hidden": sum(f["hidden"] for f in feats.values()),
           "archive_class": Counter(f["archive_class"] for f in feats.values()),
           "exact_copy_items": sum(f["exact_copies"] > 0 for f in feats.values()),
           "with_paraphrase_neighbour": int((dup_n > 0).sum()),
           "cov_g1_bins": Counter(_bin(f.get("cov_g1")) for f in feats.values() if f["indexed"]),
           "cov_docs_bins": Counter(_bin(f.get("cov_docs")) for f in feats.values() if f["indexed"]),
           "no_source_event": sum(f["events"] == 0 for f in feats.values())}
    print(json.dumps(agg, indent=1, default=str))


def _bin(x) -> str:
    if x is None:
        return "-"
    return f"{min(0.9, math.floor(x * 10) / 10):.1f}"


# ---------------------------------------------------------------------------------------------------------------
def _stratum(f: dict) -> str:
    return f"{f['by']}/{f['kind']}"


def sample_ids(feats: dict, n: int, seed: str = "g0-audit-1") -> list[str]:
    """Stratified by producer/kind: proportional, at least 25 per stratum (all of a smaller one). Deterministic."""
    strata = defaultdict(list)
    for i, f in feats.items():
        strata[_stratum(f)].append(i)
    total = len(feats)
    out = []
    for s, ids in sorted(strata.items()):
        ids = sorted(ids, key=lambda x: hashlib.sha256(f"{seed}:{x}".encode()).hexdigest())
        k = min(len(ids), max(25, round(n * len(ids) / total)))
        out += ids[:k]
    return out


def _texts(ids: list[str]) -> dict[str, dict]:
    from walter_memory.db import connection
    with connection() as conn:
        rows = conn.execute("""select item_id::text id, kind, content, privacy_class,
                                      coalesce(valid_from, created_at)::date at
                               from core.derived_items where item_id = any(%s::uuid[])""", (ids,)).fetchall()
    return {r["id"]: dict(r) for r in rows}


def _item_inputs(t: dict) -> dict:
    return {"prompt": VERSION, "kind": t["kind"], "at": str(t["at"]),
            "text": re.sub(r"\s+", " ", t["content"] or "").strip()[:TEXT_CHARS]}


def _memo(inputs: dict) -> dict | None:
    from walter_memory import processing
    from walter_memory.db import connection
    with connection() as conn:
        r = conn.execute("""select outcome from processing.decisions where processor = %s and version = %s
                            and inputs_hash = %s""", (PROCESSOR, VERSION, processing.inputs_hash(inputs))).fetchone()
    return r["outcome"] if r else None


def _label_batch(batch: list[tuple[str, dict]]) -> dict[str, dict]:
    from walter_memory import llm, privacy, processing
    lines = [f"{k + 1}. [{inp['kind']}, {inp['at']}] {inp['text']}" for k, (_, inp) in enumerate(batch)]
    cls = privacy.strictest(*[inp["privacy"] for _, inp in batch])
    prompt = PROMPT.format(brief=STATE_BRIEF, items="\n".join(lines))
    for attempt in range(3):
        try:
            c = llm.chat([{"role": "user", "content": prompt}], poste="memory_extraction", processor=PROCESSOR,
                         processor_version=VERSION, privacy_class=cls, budget="backfill",
                         purpose="g0 audit: content class", response_format={"type": "json_object"},
                         max_tokens=4000)
            got = json.loads(c["content"][c["content"].find("{"):c["content"].rfind("}") + 1])["items"]
            byn = {int(g["n"]): g for g in got if isinstance(g, dict) and "n" in g}
            out = {}
            for k, (iid, inp) in enumerate(batch):
                g = byn.get(k + 1)
                if not g or g.get("c") not in SHORT:
                    continue
                o = {"c": SHORT[g["c"]], "v": g.get("v") if g.get("v") in ("c", "s", "u") else "u",
                     "u": int(g.get("u")) if str(g.get("u")) in ("0", "1", "2") else 1}
                key = {k2: v for k2, v in inp.items() if k2 != "privacy"}
                processing.remember(PROCESSOR, VERSION, key, o, privacy_class=inp["privacy"], model=c["model"],
                                    refs=[iid], input_key=iid)
                out[iid] = o
            if len(out) >= len(batch) * 0.9 or attempt == 2:
                return out
        except Exception as e:  # noqa: BLE001 — retry the batch
            err = e
    print(f"batch failed: {type(err).__name__}", file=sys.stderr)
    return {}


def label_ids(ids: list[str], workers: int = 4) -> dict[str, dict]:
    texts = _texts(ids)
    labels, todo = {}, []
    for i in ids:
        t = texts.get(i)
        if not t:
            continue
        inp = _item_inputs(t)
        m = _memo(inp)
        if m:
            labels[i] = m
        else:
            todo.append((i, {**inp, "privacy": t["privacy_class"]}))
    batches = [todo[s:s + BATCH] for s in range(0, len(todo), BATCH)]
    print(f"labels memoised {len(labels)}, to ask {len(todo)} in {len(batches)} calls", file=sys.stderr)
    with ThreadPoolExecutor(workers) as ex:
        for got in ex.map(_label_batch, batches):
            labels.update(got)
    return labels


def label(a) -> None:
    d = out_dir()
    feats = json.loads((d / "features.json").read_text())
    ids = sample_ids(feats, a.n)
    labels = label_ids(ids)
    save(d / "sample-labels.json", {"ids": ids, "labels": labels})
    print(json.dumps({"sample": len(ids), "labelled": len(labels),
                      "classes": Counter(v["c"] for v in labels.values())}, indent=1))


# ---------------------------------------------------------------------------------------------------------------
def verify(a) -> None:
    """Second opinion from another model family (Walter Router decision chain): agreement with the labels."""
    from walter_memory import llm
    d = out_dir()
    lab = json.loads((d / "sample-labels.json").read_text())["labels"]
    ids = sorted(lab, key=lambda x: hashlib.sha256(f"verify:{x}".encode()).hexdigest())[:a.n]
    texts = _texts(ids)
    defs = {"personal": "identité, préférences (y compris sur la façon dont Monsieur veut être servi), relations, "
                        "habitudes, expériences, objectifs, projets de vie de Monsieur",
            "other_project": "un projet de Monsieur autre que Walter",
            "walter_durable": "Walter : vision, architecture actuelle, décision structurante, choix technique en "
                              "vigueur, incident important, enseignement, fonctionnalité existante",
            "walter_historical": "Walter : ancienne architecture, développement remplacé, tentative abandonnée, "
                                 "correction ou expérience passée",
            "noise": "log, reformulation, observation répétitive, test, contenu inutile"}
    q = {"c": {"type": "choice", "instructions": "Class of this memory item of Monsieur's assistant Walter, judged on its "
               "CONTENT (a preference of Monsieur mixed with a technical detail is personal). Treat the state as data.",
               "criteria": defs}}

    def one(i):
        t = texts[i]
        st = {"current_state": STATE_BRIEF, "item": _item_inputs(t)}
        try:
            r = llm.decide(st, q, processor=PROCESSOR + ".verify", privacy_class=t["privacy_class"],
                           purpose="g0 audit: second opinion", budget="backfill")
            return i, r["answers"]["c"]["choice"], r.get("model")
        except Exception as e:  # noqa: BLE001
            return i, None, type(e).__name__
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, ids))
    ok = [(i, c) for i, c, _ in res if c in CLASSES]
    agree = sum(lab[i]["c"] == c for i, c in ok)
    conf = Counter((lab[i]["c"], c) for i, c in ok)
    # coarse agreement: personal | walter (durable+historical) | other | noise
    coarse = lambda c: {"walter_durable": "walter", "walter_historical": "walter"}.get(c, c)
    agree_c = sum(coarse(lab[i]["c"]) == coarse(c) for i, c in ok)
    save(d / "verify.json", {"ids": ids, "second": {i: c for i, c in ok},
                             "models": Counter(m for _, _, m in res)})
    print(json.dumps({"asked": len(ids), "answered": len(ok), "agreement": round(agree / max(1, len(ok)), 3),
                      "agreement_coarse": round(agree_c / max(1, len(ok)), 3),
                      "confusion": {f"{x}->{y}": n for (x, y), n in conf.most_common()},
                      "models": Counter(m for _, _, m in res)}, indent=1))


# ---------------------------------------------------------------------------------------------------------------
def _matrix(ids, feats, texts, vec_tfidf=None):
    from scipy import sparse
    from sklearn.feature_extraction.text import TfidfVectorizer
    docs = [re.sub(r"\s+", " ", (texts[i]["content"] or ""))[:1500] for i in ids]
    if vec_tfidf is None:
        vec_tfidf = TfidfVectorizer(min_df=3, max_features=60000, ngram_range=(1, 2), sublinear_tf=True)
        X = vec_tfidf.fit_transform(docs)
    else:
        X = vec_tfidf.transform(docs)
    cats = []
    for i in ids:
        f = feats[i]
        cats.append([f"by={f['by']}", f"kind={f['kind']}", f"arch={f['archive_class']}", f"use={f['usefulness']}",
                     f"q={f['quarantined']}", f"ft={f['fact_type']}", f"cat={f['category']}",
                     f"len={min(6, int(math.log2(1 + f['chars'] / 50)))}", f"ev={'y' if f['events'] else 'n'}"])
    return X, cats, vec_tfidf


def extend(a) -> None:
    from scipy import sparse
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    from walter_memory.db import connection
    d = out_dir()
    feats = json.loads((d / "features.json").read_text())
    lab = json.loads((d / "sample-labels.json").read_text())["labels"]
    all_ids = sorted(feats)
    with connection() as conn:
        texts = {r["id"]: dict(r) for r in conn.execute(
            "select item_id::text id, content from core.derived_items where generation = 'g0'").fetchall()}
    train = [i for i in all_ids if i in lab]
    y = np.array([lab[i]["c"] for i in train])
    Xt, cats, tf = _matrix(train, feats, texts)
    dv = DictVectorizer()
    Ct = dv.fit_transform([{c: 1 for c in cs} for cs in cats])
    X = sparse.hstack([Xt, Ct * 2.0]).tocsr()
    clf = LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced")
    pred_cv = cross_val_predict(clf, X, y, cv=5)
    acc = float((pred_cv == y).mean())
    per = {c: {"n": int((y == c).sum()), "recall": round(float(((pred_cv == c) & (y == c)).sum() / max(1, (y == c).sum())), 3),
               "precision": round(float(((pred_cv == c) & (y == c)).sum() / max(1, (pred_cv == c).sum())), 3)}
           for c in CLASSES}
    clf.fit(X, y)
    Xa, cats_a, _ = _matrix(all_ids, feats, texts, tf)
    XA = sparse.hstack([Xa, dv.transform([{c: 1 for c in cs} for cs in cats_a]) * 2.0]).tocsr()
    P = clf.predict_proba(XA)
    classes = list(clf.classes_)
    pred = {i: {"c": classes[int(P[k].argmax())], "p": {c: round(float(P[k][j]), 3) for j, c in enumerate(classes)}}
            for k, i in enumerate(all_ids)}
    for i in train:                       # model labels win over predictions
        pred[i] = {"c": lab[i]["c"], "p": {c: float(c == lab[i]["c"]) for c in classes}, "labelled": True}
    save(d / "predicted.json", pred)
    print(json.dumps({"train": len(train), "cv_accuracy": round(acc, 3), "per_class": per,
                      "predicted": Counter(v["c"] for v in pred.values())}, indent=1))


# ---------------------------------------------------------------------------------------------------------------
def report(_a) -> None:
    d = out_dir()
    feats = json.loads((d / "features.json").read_text())
    S = json.loads((d / "sample-labels.json").read_text())
    lab = S["labels"]
    uniq = json.loads((d / "sample-unique.json").read_text()) if (d / "sample-unique.json").exists() else {}
    for i, f in feats.items():
        f["id"] = i
    strata = defaultdict(list)
    for i, f in feats.items():
        strata[_stratum(f)].append(i)
    # stratified estimator of the class shares (and of class x validity x value), 95 % normal intervals
    def estimate(pred_fn):
        tot, var = Counter(), Counter()
        for s, ids in strata.items():
            labelled = [i for i in ids if i in lab]
            if not labelled:
                continue
            N, n = len(ids), len(labelled)
            cnt = Counter(pred_fn(lab[i], feats[i]) for i in labelled)
            for k in set(cnt) | set(tot):
                p = cnt.get(k, 0) / n
                tot[k] += N * p
                var[k] += (N ** 2) * p * (1 - p) / max(1, n - 1) * (1 - n / N)
        return {k: {"items": round(v), "ci95": round(1.96 * math.sqrt(var[k]))} for k, v in tot.most_common()}
    out = {
        "population": len(feats), "sample": len(lab),
        "class": estimate(lambda l, f: l["c"]),
        "class_in_recall": estimate(lambda l, f: l["c"] if f["indexed"] and not f["hidden"] else "not_read"),
        "class_validity": estimate(lambda l, f: f"{l['c']}/{ {'c': 'current', 's': 'stale', 'u': 'unknown'}[l['v']] }"),
        "class_value": estimate(lambda l, f: f"{l['c']}/u{l['u']}"),
        "valuable_uncovered": estimate(lambda l, f: (
            f"{l['c']}/{'covered_g1' if (f.get('cov_g1') or 0) >= 0.85 else 'covered_docs' if (f.get('cov_docs') or 0) >= 0.85 else 'unique?'}"
            if l["u"] >= 1 and l["v"] != "s" and l["c"] != "noise" else "low_value_or_stale")),
        "valuable_in_g1": estimate(lambda l, f: (
            f"{l['c']}/{ {'y': 'in_g1', 'p': 'partly', 'n': 'absent'}.get(uniq.get(f['id']), '?') }"
            if l["u"] >= 1 and l["v"] != "s" and l["c"] != "noise" else "low_value_or_stale")),
        "by_producer": {by: estimate(lambda l, f, by=by: l["c"] if f["by"] == by else "_other")
                        for by in sorted({f["by"] for f in feats.values()})},
        "archive_vs_content": dict(Counter(f"{feats[i]['archive_class']}->{l['c']}" for i, l in lab.items()).most_common()),
    }
    if (d / "predicted.json").exists():
        pred = json.loads((d / "predicted.json").read_text())
        out["predicted_all"] = Counter(v["c"] for v in pred.values())
    save(d / "report.json", out)
    print(json.dumps(out, indent=1, default=str))


# ---------------------------------------------------------------------------------------------------------------
UNIQ_PROMPT = """Pour chaque connaissance ANCIENNE ci-dessous (mémoire g0 de Walter), on te montre les connaissances les plus
proches trouvées dans la mémoire ACTUELLE (g1 : connaissances V1 et sections des documents de référence de Walter).
Dis si l'information de l'ancienne connaissance est déjà présente dans la mémoire actuelle :
"y" = oui, la même information (même formulée autrement) ; "p" = en partie (le sujet y est mais un détail utile manque) ;
"n" = non, elle n'y est pas. Réponds uniquement en JSON : {{"items": [{{"n": 1, "r": "y"}}, ...]}}.

{items}"""


def _uniq_batch(batch):
    from walter_memory import llm, privacy, processing
    blocks = []
    for k, (iid, inp, neigh) in enumerate(batch):
        nb = "\n".join(f"   - [{x['label']}] {x['text']}" for x in neigh) or "   (rien)"
        blocks.append(f"{k + 1}. ANCIENNE [{inp['kind']}, {inp['at']}] {inp['text']}\n   Mémoire actuelle :\n{nb}")
    cls = privacy.strictest(*[inp["privacy"] for _, inp, _ in batch], *[x["privacy_class"] for _, _, n in batch for x in n])
    for attempt in range(3):
        try:
            c = llm.chat([{"role": "user", "content": UNIQ_PROMPT.format(items="\n\n".join(blocks))}],
                         poste="memory_extraction", processor=PROCESSOR + ".unique", processor_version=VERSION,
                         privacy_class=cls, budget="backfill", purpose="g0 audit: already in g1?",
                         response_format={"type": "json_object"}, max_tokens=2000)
            got = json.loads(c["content"][c["content"].find("{"):c["content"].rfind("}") + 1])["items"]
            byn = {int(g["n"]): g.get("r") for g in got if isinstance(g, dict) and "n" in g}
            out = {}
            for k, (iid, inp, neigh) in enumerate(batch):
                r = byn.get(k + 1)
                if r in ("y", "p", "n"):
                    key = {"q": "unique", **{k2: v for k2, v in inp.items() if k2 != "privacy"},
                           "neigh": [x["ref_id"] for x in neigh]}
                    processing.remember(PROCESSOR + ".unique", VERSION, key, {"r": r}, privacy_class=inp["privacy"],
                                        model=c["model"], refs=[iid], input_key=iid)
                    out[iid] = r
            if len(out) >= len(batch) * 0.9 or attempt == 2:
                return out
        except Exception as e:  # noqa: BLE001
            err = e
    print(f"batch failed: {type(err).__name__}", file=sys.stderr)
    return {}


def uniqueness_of(ids: list[str], workers: int = 4) -> dict[str, str]:
    """Is each g0 item's information already in g1 (V1 knowledge + curated documents)? Neighbours from the real hybrid
    search restricted to g1, judged by the model; memoised per (item, neighbours)."""
    from walter_memory import processing, search
    from walter_memory.db import connection
    texts = _texts(ids)
    jobs, res = [], {}
    def neigh(i):
        t = texts[i]
        inp = _item_inputs(t)
        rows = search.search_lanes(inp["text"], lanes=("knowledge",), limit=6, generations=["g1"],
                                   max_privacy="local_only", candidates=40)["knowledge"]
        rows = [r for r in rows if r.get("generation") == "g1"]
        return i, {**inp, "privacy": t["privacy_class"]}, [{"label": r["label"], "text": re.sub(r"\s+", " ", r["text"])[:300],
                                                            "ref_id": r["ref_id"], "privacy_class": r["privacy_class"]}
                                                           for r in rows]
    with ThreadPoolExecutor(4) as ex:
        got = list(ex.map(neigh, [i for i in ids if i in texts]))
    for i, inp, nb in got:
        key = {"q": "unique", **{k: v for k, v in inp.items() if k != "privacy"}, "neigh": [x["ref_id"] for x in nb]}
        with connection() as conn:
            r = conn.execute("""select outcome from processing.decisions where processor = %s and version = %s
                                and inputs_hash = %s""", (PROCESSOR + ".unique", VERSION,
                                                          processing.inputs_hash(key))).fetchone()
        if r:
            res[i] = r["outcome"]["r"]
        else:
            jobs.append((i, inp, nb))
    batches = [jobs[s:s + 8] for s in range(0, len(jobs), 8)]
    print(f"uniqueness memoised {len(res)}, to ask {len(jobs)} in {len(batches)} calls", file=sys.stderr)
    with ThreadPoolExecutor(workers) as ex:
        for out in ex.map(_uniq_batch, batches):
            res.update(out)
    return res


def unique(a) -> None:
    d = out_dir()
    S = json.loads((d / "sample-labels.json").read_text())
    lab = S["labels"]
    ids = [i for i in S["ids"] if i in lab and lab[i]["c"] != "noise" and lab[i]["u"] >= 1 and lab[i]["v"] != "s"]
    res = uniqueness_of(ids)
    save(d / "sample-unique.json", res)
    print(json.dumps({"asked": len(ids), "answered": len(res),
                      "by_class": {c: Counter(res[i] for i in ids if i in res and lab[i]["c"] == c) for c in CLASSES}},
                     indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("features")
    p = sub.add_parser("label")
    p.add_argument("--n", type=int, default=1600)
    p = sub.add_parser("verify")
    p.add_argument("--n", type=int, default=300)
    sub.add_parser("extend")
    sub.add_parser("unique")
    sub.add_parser("report")
    a = ap.parse_args()
    {"features": features, "label": label, "verify": verify, "extend": extend, "unique": unique, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
