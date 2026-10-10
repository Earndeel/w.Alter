"""The live engine: corpus (store + cards) + the active ranker (registry), behind one search() call.

Resilience: after every successful load, a snapshot (cards + ranker blob + skill list) is written locally; if the
registry is unreachable at start, the engine boots from the snapshot. Reload is cheap and atomic (swap of one object).
"""
from __future__ import annotations

import pickle
import threading
from pathlib import Path

import numpy as np

from . import config, registry, store
from .ranker import Corpus, Encoder, Ranker, _idf, features, score


def corpus_skills(include_archived: bool = False) -> list[dict]:
    return [{"name": s.name, "description": s.description, "tags": s.tags, "domain": s.domain, "state": s.state,
             "path": str(s.path), "owner": s.meta.get("owner"), "kind": s.meta.get("kind") or
             store.frontmatter(s.body[:4000]).get("type", ""), "requires": s.meta.get("requires") or []}
            for s in store.iter_skills(include_archived=include_archived)]


def aliases() -> dict[str, str]:
    out = {}
    for s in store.iter_skills(include_archived=True):
        out[s.name] = s.name
        fm = store.frontmatter(s.body[:6000]).get("name")
        if fm:
            out.setdefault(fm, s.name)
    return out


class Engine:
    def __init__(self):
        snap = Path(config.get("service")["snapshot_dir"]) / "engine.pkl"
        try:
            cards = registry.cards()
            row = registry.ranker()
            ranker = Ranker.loads(bytes(row["blob"])) if row else Ranker(encoder=config.get("retrieval")["encoder"])
            self.version = f"{row['version']}" if row else "untrained"
            self.calibration = ((row or {}).get("metrics") or {}).get("candidate", {})
            self.degraded = False
            snap.parent.mkdir(parents=True, exist_ok=True)
            tmp = snap.with_suffix(".tmp")
            tmp.write_bytes(pickle.dumps({"cards": cards, "ranker": ranker, "version": self.version,
                                          "calibration": self.calibration}))
            tmp.replace(snap)
        except Exception:
            data = pickle.loads(snap.read_bytes())  # registry down: last good snapshot
            cards, ranker, self.version, self.degraded = data["cards"], data["ranker"], data["version"], True
            self.calibration = data.get("calibration", {})
        self.ranker = ranker
        self.cards = cards
        self.skills = corpus_skills()
        self.by_name = {s["name"]: s for s in self.skills}
        self.aliases = aliases()
        self.enc = Encoder.get(ranker.encoder or None)
        self.corpus = Corpus(self.skills, cards, self.enc)
        self._idf = _idf(ranker)
        self._archived: Corpus | None = None
        self._lock = threading.Lock()

    def rank(self, message: str, context: str = "", session: dict | None = None, k: int = 15) -> list[dict]:
        s = score(self.ranker, features(self.corpus, self.ranker, message, context, session, _idf_cache=self._idf))
        order = np.argsort(-s)[:k]
        return [self.row(self.corpus.names[i], float(s[i]), "active") for i in order]

    def symptom_matches(self, text: str, k: int = 5) -> list[tuple[str, float]]:
        s = self.corpus.symptoms.scores(text)
        order = np.argsort(-s)[:k]
        return [(self.corpus.names[i], float(s[i])) for i in order if s[i] > 0]

    def rank_archived(self, message: str, k: int = 3) -> list[dict]:
        with self._lock:
            if self._archived is None:
                arch = [s for s in corpus_skills(include_archived=True) if s["state"] == "archived"]
                self._archived = Corpus(arch, self.cards, self.enc)
        c = self._archived
        vq = self.enc([message])[0]
        s = c.bm25.scores(message) / (1 + c.bm25.scores(message).max()) + c.desc @ vq
        return [self.row(c.names[i], float(s[i]), "archived", c) for i in np.argsort(-s)[:k]]

    def row(self, name: str, score_: float, state: str, c: Corpus | None = None) -> dict:
        c = c or self.corpus
        s = self.by_name.get(name) or next((x for x in c.skills if x["name"] == name), {})
        return {"name": name, "score": round(score_, 4), "state": state, "summary": c.summary.get(name, ""),
                "domain": s.get("domain"), "kind": s.get("kind", ""), "requires": s.get("requires", [])}


_engine: Engine | None = None
_engine_lock = threading.Lock()


def engine(reload: bool = False) -> Engine:
    """The live engine. A reload builds the new engine aside and swaps it in: requests never wait for it."""
    global _engine
    if reload:
        fresh = Engine()
        _engine = fresh
    elif _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = Engine()
    return _engine


def read_skill(name: str, file_path: str | None = None) -> str | None:
    s = store.find(name, include_archived=True)
    if s is None:
        s = {store.frontmatter(x.body[:6000]).get("name"): x for x in store.iter_skills(include_archived=True)}.get(name)
    if s is None:
        return None
    if file_path:
        p = (s.path / file_path).resolve()
        if not str(p).startswith(str(s.path.resolve()) + "/") or not p.is_file():
            return None
        return p.read_text(errors="replace")
    files = [str(p.relative_to(s.path)) for p in sorted(s.path.rglob("*"))
             if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and "__pycache__" not in p.parts]
    head = f"[walter-skills: {s.name} · {s.state} · {s.domain or '-'}]\n"
    tail = ("\n\n[Linked files — read with skill_read(name, file_path): " + ", ".join(files[:60]) + "]") if files else ""
    return head + s.body + tail
