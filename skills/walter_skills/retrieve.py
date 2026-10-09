"""Intent → skill retrieval. Local, no LLM on the per-message path.

Features per (message, skill), each computed for the message and, separately, for the previous turn (context):
  bm25    lexical match on the skill's card (name, description, summary, intents, entities, symptoms)
  trig    max cosine between the message and the card's trigger formulations (intents, summary, description)
  desc    cosine with name + summary + description
  hist    learned triggers: similarity-weighted votes of past messages that led to this skill (strictly earlier)
  prior   log usage of the skill before the cut-off
Fusion = logistic regression trained on past cases (see `fit`), default hand weights before training.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE = Path("/opt/walter-skills/index/cache")
MODEL_DIR = "/opt/walter-voice-memory/models"
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
        avg = float(lens.mean()) or 1.0
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
    def __init__(self, model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", threads: int = 4):
        self.model_name = model
        from fastembed import TextEmbedding
        self.m = TextEmbedding(model, cache_dir=MODEL_DIR, threads=threads)

    def __call__(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        v = np.array(list(self.m.embed(texts, batch_size=64)), dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-9)

    def cached(self, texts: list[str], tag: str) -> np.ndarray:
        CACHE.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1((self.model_name + "\0" + "\0".join(texts)).encode()).hexdigest()[:16]
        p = CACHE / f"{tag}-{key}.npy"
        if p.exists():
            return np.load(p)
        v = self(texts)
        np.save(p, v)
        return v


FEATURES = ("bm25", "trig", "desc", "hist", "hist_idf", "bm25_c", "trig_c", "hist_c", "prior", "sess")


@dataclass
class Memory:
    """Past messages that led to a skill (the learner's triggers). times = epoch seconds."""
    vecs: np.ndarray
    golds: list[list[int]]
    times: np.ndarray
    ids: list[str]
    idf: np.ndarray | None = None  # per skill: rarer skills weigh more (generic "habit" skills weigh little)


class Index:
    def __init__(self, skills: list[dict], cards: dict[str, dict], encoder: Encoder,
                 prior: dict[str, float] | None = None):
        self.names = [s["name"] for s in skills]
        self.pos = {n: i for i, n in enumerate(self.names)}
        self.enc = encoder
        docs, trig_texts, trig_owner, desc_texts = [], [], [], []
        for i, s in enumerate(skills):
            c = cards.get(s["name"]) or {}
            words = s["name"].replace("-", " ")
            docs.append(" ".join([words, words, s.get("description", ""), c.get("summary", ""),
                                  " ".join(c.get("intents_fr", [])), " ".join(c.get("intents_en", [])),
                                  " ".join(c.get("entities", [])), " ".join(c.get("symptoms", []))]))
            desc_texts.append(f"{words}: {c.get('summary') or ''} {s.get('description', '')}".strip())
            for t in [f"{words}: {s.get('description', '')}", c.get("summary", "")] + \
                    list(c.get("intents_fr", [])) + list(c.get("intents_en", [])) + list(c.get("symptoms", [])):
                if t:
                    trig_texts.append(t)
                    trig_owner.append(i)
        self.bm25 = BM25(docs)
        self.desc = encoder.cached(desc_texts, "desc")
        self.trig = encoder.cached(trig_texts, "trig")
        self.trig_owner = np.array(trig_owner)
        self.prior = np.array([math.log1p((prior or {}).get(n, 0.0)) for n in self.names], dtype=np.float32)
        self.memory: Memory | None = None
        self.weights = {"bm25": 1.0, "trig": 1.5, "desc": 0.7, "hist": 1.5, "hist_idf": 0.5, "bm25_c": 0.3,
                        "trig_c": 0.4, "hist_c": 0.4, "prior": 0.3, "sess": 1.0}
        self.bias = 0.0
        self.model = None  # optional non-linear learner (fit(kind="hgb"))

    # --- features ---------------------------------------------------------------------------------------
    def _trig_max(self, v: np.ndarray) -> np.ndarray:
        sims = self.trig @ v
        out = np.full(len(self.names), -1.0, dtype=np.float32)
        np.maximum.at(out, self.trig_owner, sims)
        return out

    def _hist(self, v: np.ndarray, before: float | None, exclude: str | None, k: int = 15,
              idf: bool = False) -> np.ndarray:
        out = np.zeros(len(self.names), dtype=np.float32)
        m = self.memory
        if m is None or not len(m.ids):
            return out
        sims = m.vecs @ v
        if before is not None:
            sims = np.where(m.times < before, sims, -1)
        if exclude is not None:
            sims = np.where(np.array([i == exclude for i in m.ids]), -1, sims)
        top = np.argsort(-sims)[:k]
        for j in top:
            if sims[j] <= 0.3:
                break
            for g in m.golds[j]:
                out[g] += float(sims[j]) ** 3 * (float(m.idf[g]) if idf and m.idf is not None else 1.0)
        return out

    @staticmethod
    def _z(x: np.ndarray) -> np.ndarray:
        sd = float(x.std())
        return (x - float(x.mean())) / sd if sd > 1e-9 else np.zeros_like(x)

    def _sess(self, session: dict[str, int] | None) -> np.ndarray:
        """Skills opened earlier in this session: 1 for the previous turn, decaying with turns ago."""
        out = np.zeros(len(self.names), dtype=np.float32)
        for n, ago in (session or {}).items():
            i = self.pos.get(n)
            if i is not None:
                out[i] = math.exp(-max(0, ago) / 4)
        return out

    def features(self, message: str, context: str = "", before: float | None = None,
                 exclude: str | None = None, session: dict[str, int] | None = None) -> np.ndarray:
        vq, vc = self.enc([message, context or " "])
        f = {
            "bm25": self.bm25.scores(message), "trig": self._trig_max(vq), "desc": self.desc @ vq,
            "hist": self._hist(vq, before, exclude),
            "hist_idf": self._hist(vq, before, exclude, idf=True),
            "bm25_c": self.bm25.scores(context) if context else np.zeros(len(self.names), np.float32),
            "trig_c": self._trig_max(vc) if context else np.zeros(len(self.names), np.float32),
            "hist_c": self._hist(vc, before, exclude) if context else np.zeros(len(self.names), np.float32),
            "prior": self.prior,
        }
        sess = self._sess(session)
        # absolute evidence (before per-query normalisation) for the "does this message need a skill?" gate
        self.last_raw = np.array([math.log1p(float(f["bm25"].max())), float(f["trig"].max()), float(f["desc"].max()),
                                  math.log1p(float(f["hist"].max())), math.log1p(float(f["hist_idf"].max())),
                                  float(sess.max()), math.log1p(len(message.split())),
                                  float(np.sort(f["trig"])[-1] - np.sort(f["trig"])[-5])], dtype=np.float32)
        z = [self._z(np.asarray(f[k], dtype=np.float32)) for k in FEATURES if k != "sess"]
        return np.stack(z + [sess], axis=1)

    def linear(self, feats: np.ndarray) -> np.ndarray:
        return feats @ np.array([self.weights[k] for k in FEATURES], dtype=np.float32) + self.bias

    def score(self, feats: np.ndarray) -> np.ndarray:
        if self.model is None:
            return self.linear(feats)
        lin = self.linear(feats)
        cand = np.argsort(-lin)[:40]  # the learner reranks the linear shortlist (cheap, keeps tails sane)
        out = lin - 1e3
        out[cand] = self.model.predict_proba(self._rows(feats, lin, cand))[:, 1]
        return out

    @staticmethod
    def _rows(feats: np.ndarray, lin: np.ndarray, idx) -> np.ndarray:
        rank = np.empty(len(lin)); rank[np.argsort(-lin)] = np.arange(len(lin))
        return np.column_stack([feats[idx], lin[idx], np.log1p(rank[idx])])

    def search(self, message: str, context: str = "", k: int = 5, before: float | None = None,
               exclude: str | None = None, session: dict[str, int] | None = None) -> list[tuple[str, float]]:
        s = self.score(self.features(message, context, before, exclude, session))
        top = np.argsort(-s)[:k]
        return [(self.names[i], float(s[i])) for i in top]

    # --- learning ---------------------------------------------------------------------------------------
    def set_memory(self, cases: list[dict], gold_key: str = "gold") -> None:
        keep = [c for c in cases if any(g in self.pos for g in c[gold_key])]
        vecs = self.enc.cached([c["query"][:1000] for c in keep], "memq") if keep else np.zeros((0, 1))
        golds = [[self.pos[g] for g in c[gold_key] if g in self.pos] for c in keep]
        freq = np.bincount([g for gl in golds for g in gl], minlength=len(self.names)).astype(np.float32)
        idf = np.log((len(keep) + 1) / (freq + 1)).astype(np.float32)
        self.memory = Memory(vecs=vecs, golds=golds, times=np.array([c["ts"] for c in keep], dtype=np.float64),
                             ids=[c["id"] for c in keep], idf=idf)

    def fit(self, cases: list[dict], gold_key: str = "gold", negatives: int = 30, C: float = 1.0,
            kind: str = "lr") -> dict:
        """Learn the fusion from past cases. lr: logistic regression on (case, skill) pairs, gold = 1, top-scoring
        non-gold = 0 (hard negatives). hgb: then a gradient-boosted reranker on the linear top-40."""
        from sklearn.linear_model import LogisticRegression
        feats = []  # (positives, known negatives, case weight, features)
        for c in cases:
            lab = c.get("labels")  # judged case: {skill: 0|1|2}; label 1 = neither positive nor negative
            if lab:
                gold = {self.pos[n] for n, v in lab.items() if v == 2 and n in self.pos}
                neg = {self.pos[n] for n, v in lab.items() if v == 0 and n in self.pos}
            else:
                gold = {self.pos[g] for g in c[gold_key] if g in self.pos}
                neg = set()
            if gold:
                feats.append((gold, neg, float(c.get("weight", 1.0)),
                              self.features(c["query"], c.get("ctx", ""), before=c["ts"], exclude=c["id"],
                                            session=c.get("session_skills"))))
        self.model = None
        X, y, w = [], [], []
        for gold, neg, cw, f in feats:
            order = np.argsort(-self.linear(f))
            labelled = {i for i in order[:negatives] if i not in gold} if not neg else neg
            unjudged = [] if not neg else [i for i in order[:negatives] if i not in gold and i not in neg]
            for i in gold:
                X.append(f[i]); y.append(1); w.append(cw)
            for i in labelled:
                X.append(f[i]); y.append(0); w.append(cw)
            for i in unjudged:  # outside the judged pool: probably irrelevant, weak negative
                X.append(f[i]); y.append(0); w.append(0.3 * cw)
        lr = LogisticRegression(C=C, max_iter=2000, class_weight="balanced").fit(
            np.array(X), np.array(y), sample_weight=np.array(w))
        self.weights = {k: float(w) for k, w in zip(FEATURES, lr.coef_[0])}
        self.bias = float(lr.intercept_[0])
        if kind == "hgb":
            from sklearn.ensemble import HistGradientBoostingClassifier
            X, y, w = [], [], []
            for gold, neg, cw, f in feats:
                lin = self.linear(f)
                cand = np.argsort(-lin)[:40]
                X.append(self._rows(f, lin, cand)); y.append(np.isin(cand, list(gold)).astype(int))
                known = np.isin(cand, list(gold | neg)) if neg else np.ones(len(cand), bool)
                w.append(np.where(known, cw, 0.3 * cw))
            self.model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                        l2_regularization=1.0, class_weight="balanced",
                                                        random_state=0).fit(np.vstack(X), np.concatenate(y),
                                                                            sample_weight=np.concatenate(w))
        return self.weights

    def save_weights(self, path: Path) -> None:
        path.write_text(json.dumps({"weights": self.weights, "bias": self.bias, "encoder": self.enc.model_name},
                                   indent=1))

    def load_weights(self, path: Path) -> None:
        d = json.loads(path.read_text())
        self.weights, self.bias = d["weights"], d["bias"]
