"""Intent → skill ranking. Local and fast (no LLM on the per-message path).

Two objects, cleanly separated:
  Corpus  what is searchable: skills + their trigger cards, as lexical (BM25) and semantic (local embeddings) indexes.
          Rebuilt whenever the store or the cards change; embeddings are cached on disk.
  Ranker  what was learned: fusion model, learned triggers (past messages → skills), usage prior. Keyed by skill
          NAME, so it survives store changes; serialised as one blob in the registry (skills.rankers).
Features per (message, skill), each also on the previous turn (context):
  bm25 (lexical on the card) · trig (closest trigger phrase) · desc (summary+description) · hist / hist_idf (learned
  triggers, rarer skills weigh more) · prior (log usage) · sess (read earlier in this session)
"""
from __future__ import annotations

import hashlib
import math
import pickle
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config

FEATURES = ("bm25", "trig", "desc", "hist", "hist_idf", "bm25_c", "trig_c", "hist_c", "prior", "sess")
STOP = set("""le la les un une des de du d l et ou a au aux en dans sur pour par avec sans ce cet cette ces je tu il
elle on nous vous ils elles me te se mon ma mes ton ta tes son sa ses que qui quoi est sont pas ne plus mais donc car si
fais fait faire peux veux tout tous ca cela ici the a an of to in on for with and or is are be it this that you i we
what how do does can use when""".split())


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", fold(s)) if len(t) > 1 and t not in STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        toks = [tokens(d) for d in docs]
        self.n = len(docs)
        lens = np.array([len(t) for t in toks], dtype=np.float32)
        avg = float(lens.mean()) if len(lens) and lens.mean() else 1.0
        df = Counter(w for t in toks for w in set(t))
        self.post: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        acc: dict[str, list[tuple[int, float]]] = {}
        for i, t in enumerate(toks):
            for w, f in Counter(t).items():
                acc.setdefault(w, []).append((i, f * (k1 + 1) / (f + k1 * (1 - b + b * lens[i] / avg))))
        for w, lst in acc.items():
            idf = math.log(1 + (self.n - df[w] + 0.5) / (df[w] + 0.5))
            self.post[w] = (np.array([i for i, _ in lst]), np.array([v * idf for _, v in lst], dtype=np.float32))

    def scores(self, q: str) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        for w in set(tokens(q)):
            p = self.post.get(w)
            if p is not None:
                out[p[0]] += p[1]
        return out


class Encoder:
    _cache: dict[str, "Encoder"] = {}

    def __init__(self, model: str):
        from fastembed import TextEmbedding
        cfg = config.get("retrieval")
        self.model_name = model
        self.m = TextEmbedding(model, cache_dir=cfg["model_dir"], threads=4)
        self.cache = Path(cfg["cache_dir"])

    @classmethod
    def get(cls, model: str | None = None) -> "Encoder":
        model = model or config.get("retrieval")["encoder"]
        if model not in cls._cache:
            cls._cache[model] = cls(model)
        return cls._cache[model]

    def __call__(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        v = np.array(list(self.m.embed(texts, batch_size=64)), dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-9)

    def cached(self, texts: list[str], tag: str) -> np.ndarray:
        self.cache.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1((self.model_name + "\0" + "\0".join(texts)).encode()).hexdigest()[:16]
        p = self.cache / f"{tag}-{key}.npy"
        if p.exists():
            return np.load(p)
        v = self(texts)
        np.save(p, v)
        return v


class Corpus:
    """What is searchable. skills: [{name, description, ...}], cards: {name: card}."""

    def __init__(self, skills: list[dict], cards: dict[str, dict], encoder: Encoder):
        self.skills = skills
        self.names = [s["name"] for s in skills]
        self.pos = {n: i for i, n in enumerate(self.names)}
        self.enc = encoder
        docs, trig, owner, desc, symptoms = [], [], [], [], []
        for i, s in enumerate(skills):
            c = cards.get(s["name"]) or {}
            words = s["name"].replace("-", " ")
            docs.append(" ".join([words, words, s.get("description", ""), c.get("summary", ""),
                                  " ".join(c.get("intents_fr", [])), " ".join(c.get("intents_en", [])),
                                  " ".join(c.get("entities", [])), " ".join(c.get("symptoms", []))]))
            desc.append(f"{words}: {c.get('summary') or ''} {s.get('description', '')}".strip())
            symptoms.append(" ".join(c.get("symptoms", [])))
            for t in [f"{words}: {s.get('description', '')}", c.get("summary", "")] + list(c.get("intents_fr", [])) \
                    + list(c.get("intents_en", [])) + list(c.get("symptoms", [])):
                if t:
                    trig.append(t)
                    owner.append(i)
        self.bm25 = BM25(docs)
        self.symptoms = BM25(symptoms)
        self.desc = encoder.cached(desc, "desc")
        self.trig = encoder.cached(trig, "trig")
        self.trig_owner = np.array(owner)
        self.summary = {s["name"]: (cards.get(s["name"]) or {}).get("summary") or s.get("description", "")[:160]
                        for s in skills}


@dataclass
class Ranker:
    """What was learned. Everything keyed by skill name."""
    weights: dict = field(default_factory=lambda: {"bm25": 1.0, "trig": 1.5, "desc": 0.7, "hist": 1.5, "hist_idf": 0.5,
                                                   "bm25_c": 0.3, "trig_c": 0.4, "hist_c": 0.4, "prior": 0.3,
                                                   "sess": 1.0})
    bias: float = 0.0
    model: object = None                       # HistGradientBoosting reranker of the linear top-40
    prior: dict = field(default_factory=dict)  # name → usage count
    mem_vecs: np.ndarray | None = None         # learned triggers: past message embeddings …
    mem_golds: list = field(default_factory=list)  # … → skill names that message needed
    mem_times: np.ndarray | None = None
    mem_ids: list = field(default_factory=list)
    encoder: str = ""

    def dumps(self) -> bytes:
        return pickle.dumps(self)

    @staticmethod
    def loads(blob: bytes) -> "Ranker":
        return pickle.loads(blob)


# ── scoring ───────────────────────────────────────────────────────────────────────────────────────────

def _z(x: np.ndarray) -> np.ndarray:
    sd = float(x.std())
    return (x - float(x.mean())) / sd if sd > 1e-9 else np.zeros_like(x)


def _trig_max(c: Corpus, v: np.ndarray) -> np.ndarray:
    out = np.full(len(c.names), -1.0, dtype=np.float32)
    np.maximum.at(out, c.trig_owner, c.trig @ v)
    return out


def _hist(c: Corpus, r: Ranker, v: np.ndarray, before: float | None, exclude: str | None, idf: dict | None,
          k: int = 15) -> np.ndarray:
    out = np.zeros(len(c.names), dtype=np.float32)
    if r.mem_vecs is None or not len(r.mem_ids):
        return out
    sims = r.mem_vecs @ v
    if before is not None:
        sims = np.where(r.mem_times < before, sims, -1)
    if exclude is not None:
        sims = np.where(np.array([i == exclude for i in r.mem_ids]), -1, sims)
    for j in np.argsort(-sims)[:k]:
        if sims[j] <= 0.3:
            break
        for g in r.mem_golds[j]:
            i = c.pos.get(g)
            if i is not None:
                out[i] += float(sims[j]) ** 3 * (idf.get(g, 1.0) if idf else 1.0)
    return out


def _idf(r: Ranker) -> dict:
    df = Counter(g for gl in r.mem_golds for g in gl)
    n = len(r.mem_golds) + 1
    return {g: math.log(n / (f + 1)) for g, f in df.items()}


def features(c: Corpus, r: Ranker, message: str, context: str = "", session: dict | None = None,
             before: float | None = None, exclude: str | None = None, _idf_cache: dict | None = None) -> np.ndarray:
    vq, vc = c.enc([message, context or " "])
    idf = _idf_cache if _idf_cache is not None else _idf(r)
    zero = np.zeros(len(c.names), np.float32)
    f = {"bm25": c.bm25.scores(message), "trig": _trig_max(c, vq), "desc": c.desc @ vq,
         "hist": _hist(c, r, vq, before, exclude, None), "hist_idf": _hist(c, r, vq, before, exclude, idf),
         "bm25_c": c.bm25.scores(context) if context else zero, "trig_c": _trig_max(c, vc) if context else zero,
         "hist_c": _hist(c, r, vc, before, exclude, None) if context else zero,
         "prior": np.array([math.log1p(r.prior.get(n, 0)) for n in c.names], dtype=np.float32)}
    sess = np.zeros(len(c.names), dtype=np.float32)
    for n, ago in (session or {}).items():
        if n in c.pos:
            sess[c.pos[n]] = math.exp(-max(0, ago) / 4)
    return np.stack([_z(np.asarray(f[k], dtype=np.float32)) for k in FEATURES if k != "sess"] + [sess], axis=1)


def _linear(r: Ranker, feats: np.ndarray) -> np.ndarray:
    return feats @ np.array([r.weights[k] for k in FEATURES], dtype=np.float32) + r.bias


def _rows(feats: np.ndarray, lin: np.ndarray, idx) -> np.ndarray:
    rank = np.empty(len(lin))
    rank[np.argsort(-lin)] = np.arange(len(lin))
    return np.column_stack([feats[idx], lin[idx], np.log1p(rank[idx])])


def score(r: Ranker, feats: np.ndarray) -> np.ndarray:
    """Probability-like scores (HGB on the linear top-40; the tail keeps a large negative linear score)."""
    lin = _linear(r, feats)
    if r.model is None:
        return lin
    cand = np.argsort(-lin)[:40]
    out = lin - 1e3
    out[cand] = r.model.predict_proba(_rows(feats, lin, cand))[:, 1]
    return out


# ── learning ──────────────────────────────────────────────────────────────────────────────────────────

def train(c: Corpus, cases: list[dict], examples: list[dict], encoder: str, negatives: int = 30) -> Ranker:
    """cases: past real messages (history) → learned triggers + prior (what agents opened).
    examples: labelled cases {query, ctx, ts, id, session_skills, labels: {skill: (label, weight)}} → the fusion.
    Label 2 = positive, 0 = negative, 1 = ignored; unlabelled top candidates = weak negatives."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    keep = [x for x in cases if x.get("gold")]
    r = Ranker(prior=dict(Counter(g for x in keep for g in x["gold"])), encoder=encoder,
               mem_vecs=c.enc.cached([x["query"][:1000] for x in keep], "memq") if keep else None,
               mem_golds=[list(x["gold"]) for x in keep], mem_times=np.array([x["ts"] for x in keep], dtype=np.float64),
               mem_ids=[x["id"] for x in keep])
    idf = _idf(r)
    feats = []
    for x in examples:
        pos = {c.pos[s] for s, (v, _) in x["labels"].items() if v == 2 and s in c.pos}
        neg = {c.pos[s] for s, (v, _) in x["labels"].items() if v == 0 and s in c.pos}
        if pos:
            w = max(wt for s, (v, wt) in x["labels"].items() if v == 2)
            feats.append((pos, neg, w, features(c, r, x["query"], x.get("ctx", ""), x.get("session_skills"),
                                                before=x.get("ts"), exclude=x.get("id"), _idf_cache=idf)))
    X, y, sw = [], [], []
    for pos, neg, w, f in feats:
        order = np.argsort(-_linear(r, f))
        unl = [i for i in order[:negatives] if i not in pos and i not in neg]
        for i in pos:
            X.append(f[i]); y.append(1); sw.append(w)
        for i in neg:
            X.append(f[i]); y.append(0); sw.append(w)
        for i in unl:
            X.append(f[i]); y.append(0); sw.append(0.3 * w)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced").fit(np.array(X), np.array(y), sample_weight=np.array(sw))
    r.weights, r.bias = {k: float(v) for k, v in zip(FEATURES, lr.coef_[0])}, float(lr.intercept_[0])
    X, y, sw = [], [], []
    for pos, neg, w, f in feats:
        lin = _linear(r, f)
        cand = np.argsort(-lin)[:40]
        X.append(_rows(f, lin, cand))
        y.append(np.isin(cand, list(pos)).astype(int))
        sw.append(np.where(np.isin(cand, list(pos | neg)), w, 0.3 * w))
    r.model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0,
                                             class_weight="balanced", random_state=0).fit(
        np.vstack(X), np.concatenate(y), sample_weight=np.concatenate(sw))
    return r
