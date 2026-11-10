"""Memory Router (P5, §13–14, A7): L0 rules → L2 local calibrated classifier → abstention/escalation (Jev / LLM).

Destinations (primary): memory (durable fact about Monsieur: profile, projects, decisions, preferences, rules for
W.Alter), social (about other people / relationships → Kardex), index_only (searchable, not memorable: technical
details, task chatter), ignore (no durable content). 'ignore' never deletes: the canonical event stays.
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import numpy as np

from . import search

MODEL_PATH = Path("/walter/cognition/memory/models/router_l2.pkl")
DESTS = ["memory", "social", "index_only", "ignore"]
LUNA_TO_DEST = {"user_profile": "memory", "project": "memory", "agent_rules": "memory", "people": "social",
                "infra_internal": "index_only", "task_log": "index_only", "vacuous": "ignore", "test_junk": "ignore"}
ACK = re.compile(r"^\s*(ok(ay)?|oui|non|merci|thanks?|top|parfait|super|d'accord|ça marche|go|vas-y|yes|no|cool|"
                 r"👍|🙏|❤️|😂|🤣|😊|👌|🔥|💯|✅)[\s!.?]*$", re.I)
VERSION = "router-1"


def l0(event: dict) -> str | None:
    """Deterministic routing: returns a destination or None to defer to L2."""
    text = (event.get("content") or "").strip()
    et = event.get("event_type", "")
    if et in ("tool.called", "skill.used", "conversation.started", "conversation.ended", "reaction.added",
              "message.deleted", "location.sample"):
        return "index_only" if et != "reaction.added" else "ignore"
    if len(text) < 3 or ACK.match(text):
        return "ignore"
    if event.get("privacy_class") == "local_only" and et in ("message.sent", "message.received"):
        return None  # still classified (locally) — only cloud escalation is forbidden
    return None


def features(texts: list[str]) -> np.ndarray:
    emb = search.embed([t[:2000] for t in texts])
    extra = np.array([[min(len(t), 4000) / 4000, t.count("?") > 0, bool(re.search(r"\b(je|j'|mon|ma|mes|I|my)\b", t, re.I)),
                       bool(re.search(r"[{}<>/\\]|```|\.py|\.sh|http", t))] for t in texts], dtype=np.float32)
    return np.hstack([emb, extra])


class Router:
    def __init__(self, clf=None, calibrated=None, threshold: float = 0.6):
        self.clf, self.calibrated, self.threshold = clf, calibrated, threshold

    @classmethod
    def load(cls) -> "Router":
        return pickle.loads(MODEL_PATH.read_bytes())

    def save(self) -> None:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODEL_PATH.write_bytes(pickle.dumps(self))

    def proba(self, texts: list[str]) -> np.ndarray:
        model = self.calibrated or self.clf
        p = model.predict_proba(features(texts))
        out = np.zeros((len(texts), len(DESTS)))
        for j, c in enumerate(model.classes_):
            out[:, DESTS.index(c)] = p[:, j]
        return out

    def route(self, events: list[dict]) -> list[dict]:
        """Returns per event: destination, confidence, decided_by (l0 | l2 | abstain→escalate)."""
        res: list[dict | None] = [None] * len(events)
        todo = []
        for i, e in enumerate(events):
            d = l0(e)
            if d:
                res[i] = {"destination": d, "confidence": 1.0, "decided_by": "l0"}
            else:
                todo.append(i)
        if todo:
            P = self.proba([events[i].get("content") or "" for i in todo])
            for i, p in zip(todo, P):
                k = int(p.argmax())
                res[i] = {"destination": DESTS[k], "confidence": float(p[k]), "probs": dict(zip(DESTS, map(float, p))),
                          "decided_by": "l2" if p[k] >= self.threshold else "abstain"}
        return res


def training_set(limit: int | None = None) -> tuple[list[str], list[str]]:
    from .db import connection
    with connection() as conn:
        rows = conn.execute("""select content, attributes->>'usefulness' u from core.derived_items
                               where derived_by = 'hindsight' and attributes ? 'usefulness'
                               order by item_id """ + (f"limit {int(limit)}" if limit else "")).fetchall()
    return [r["content"] for r in rows], [LUNA_TO_DEST[r["u"]] for r in rows]


def train() -> dict:
    from sklearn.linear_model import LogisticRegression
    texts, y = training_set()
    X = features(texts)
    clf = LogisticRegression(max_iter=2000, C=2.0, class_weight="balanced")
    clf.fit(X, y)
    r = Router(clf)
    r.save()
    return {"trained_on": len(texts), "classes": list(clf.classes_)}


def calibrate(texts: list[str], labels: list[str], threshold_precision: float = 0.85) -> dict:
    """Isotonic calibration on an independent labelled sample; pick the abstention threshold reaching the target
    precision on decided items. Uses the fitted classifier as a frozen estimator."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    r = Router.load()
    X = features(texts)
    cal = CalibratedClassifierCV(FrozenEstimator(r.clf), method="sigmoid")
    cal.fit(X, labels)
    r.calibrated = cal
    P = r.proba(texts)
    best = 0.95
    for t in np.arange(0.30, 0.96, 0.05):
        mask = P.max(1) >= t
        if mask.sum() and np.mean(np.array(DESTS)[P.argmax(1)][mask] == np.array(labels)[mask]) >= threshold_precision:
            best = float(t); break
    r.threshold = best
    r.save()
    return {"threshold": best}
