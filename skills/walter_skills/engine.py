"""The production retriever: store + cards + history → trained Index, saved under index/model/ and loaded by the service.

train(): rebuilds the learned parts from walter_logs (usage prior, learned triggers, fusion model). Nightly + on demand.
load():  fast path for the service (embeddings cached, model unpickled).
"""
from __future__ import annotations

import json
import pickle

import numpy as np
import time
from collections import Counter

from . import cards as cards_mod
from . import history, store
from .retrieve import Encoder, Index

MODEL_DIR = store.ROOT / "index" / "model"
ENCODER = "minishlab/potion-multilingual-128M"   # chosen on the bench (P10.3); see bench/README
VERSION_FILE = MODEL_DIR / "version.json"


def corpus(include_archived: bool = False) -> list[dict]:
    return [{"name": s.name, "description": s.description, "tags": s.tags, "domain": s.domain, "state": s.state,
             "path": str(s.path), "owner": s.meta.get("owner"), "origin": s.meta.get("origin")}
            for s in store.iter_skills(include_archived=include_archived)]


def aliases(skills: list[dict]) -> dict[str, str]:
    out = {s["name"]: s["name"] for s in skills}
    for s in store.iter_skills(include_archived=True):
        fm = store.frontmatter(s.body[:6000]).get("name")
        if fm and s.name in out:
            out.setdefault(fm, s.name)
    return out


def _cards(skills: list[dict]) -> dict[str, dict]:
    return {s["name"]: cards_mod.load(s["name"]) or {} for s in skills}


JUDGED = store.ROOT / "index" / "judged"  # labels from poste skills.judge: {"id": qid, "labels": {skill: 0|1|2}}


def judged_labels() -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for f in sorted(JUDGED.glob("*.jsonl")) if JUDGED.exists() else []:
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                labels.setdefault(r["id"], {}).update(r["labels"])
    return labels


def train(encoder_name: str = ENCODER, kind: str = "hgb", log_weight: float = 0.0) -> dict:
    """Fusion trained on judged cases (skills.judge); raw log cases only feed the learned triggers and the prior
    (they encode Hermes' loading habits — see DECISIONS 2026-10-09), unless log_weight > 0."""
    t0 = time.time()
    skills = corpus()
    al = aliases(skills)
    past = history.cases(al)
    labels = judged_labels()
    enc = Encoder(encoder_name)
    idx = Index(skills, _cards(skills), enc, prior=Counter(g for c in past for g in c["gold"]))
    idx.set_memory(past)
    judged = [c | {"labels": labels[c["qid"]]} for c in past if c["qid"] in labels]
    train_set = judged + ([c | {"weight": log_weight} for c in past if c["qid"] not in labels] if log_weight else [])
    idx.fit(train_set or past, kind=kind)
    gate, gate_info = train_gate(idx, al, labels)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    state = {"weights": idx.weights, "bias": idx.bias, "model": idx.model, "gate": gate,
             "memory": idx.memory, "prior": idx.prior, "names": idx.names}
    with open(MODEL_DIR / "model.pkl", "wb") as f:
        pickle.dump(state, f)
    info = {"version": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), "encoder": encoder_name, "learner": kind,
            "skills": len(skills), "history_cases": len(past), "judged_cases": len(judged), "weights": idx.weights,
            "gate": gate_info, "train_seconds": round(time.time() - t0, 1)}
    VERSION_FILE.write_text(json.dumps(info, indent=1))
    return info


def train_gate(idx: Index, al: dict[str, str], labels: dict[str, dict], negatives: int = 3000):
    """P(this message needs a skill): messages after which an agent opened a skill (and judged-relevant cases) vs
    messages after which none was opened (and judged cases with no relevant skill). Time-ordered 80/20 check."""
    import random
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    allc = history.cases(al, negatives=True)
    pos = [c for c in allc if c["gold"] and not (c["qid"] in labels and not any(v == 2 for v in labels[c["qid"]].values()))]
    neg = [c for c in allc if not c["gold"]] + [c for c in allc if c["qid"] in labels
                                                and not any(v == 2 for v in labels[c["qid"]].values())]
    random.Random(5).shuffle(neg)
    data = sorted([(c, 1) for c in pos] + [(c, 0) for c in neg[:negatives]], key=lambda x: x[0]["ts"])
    X, y = [], []
    for c, lab in data:
        idx.features(c["query"], c.get("ctx", ""), before=c["ts"], exclude=c["id"], session=c.get("session_skills"))
        X.append(idx.last_raw.copy()); y.append(lab)
    X, y = np.array(X), np.array(y)
    cut = int(0.8 * len(y))
    check = LogisticRegression(max_iter=2000, class_weight="balanced").fit(X[:cut], y[:cut])
    p = check.predict_proba(X[cut:])[:, 1]
    info = {"auc_holdout": round(float(roc_auc_score(y[cut:], p)), 3), "n_pos": int(y.sum()), "n_neg": int(len(y) - y.sum())}
    for thr in (0.3, 0.4, 0.5, 0.6):
        sel = p >= thr
        info[f"thr{thr}"] = {"inject_rate_need": round(float(sel[y[cut:] == 1].mean()), 3),
                             "inject_rate_noneed": round(float(sel[y[cut:] == 0].mean()), 3)}
    gate = LogisticRegression(max_iter=2000, class_weight="balanced").fit(X, y)
    return gate, info


class Engine:
    """Loaded once per service process. Archived skills are searched only on demand (separate index)."""

    def __init__(self):
        info = json.loads(VERSION_FILE.read_text())
        self.version = f"{info['version']}/{info['encoder'].split('/')[-1]}/{info['learner']}"
        self.enc = Encoder(info["encoder"])
        with open(MODEL_DIR / "model.pkl", "rb") as f:
            st = pickle.load(f)
        self.skills = corpus()
        self.by_name = {s["name"]: s for s in self.skills}
        self.cards = _cards(self.skills)
        self.aliases = aliases(self.skills)
        self.idx = Index(self.skills, self.cards, self.enc)
        if self.idx.names == st["names"]:
            self.idx.prior, self.idx.memory = st["prior"], st["memory"]
            self.idx.weights, self.idx.bias, self.idx.model = st["weights"], st["bias"], st["model"]
            self.gate = st.get("gate")
        else:  # store changed since training: keep the learned fusion, remap prior/memory by name
            pos = {n: i for i, n in enumerate(st["names"])}
            self.idx.prior = st["prior"][[pos[n] for n in self.idx.names]] if all(
                n in pos for n in self.idx.names) else self.idx.prior
            self.idx.weights, self.idx.bias, self.idx.model = st["weights"], st["bias"], st["model"]
            self.gate = st.get("gate")
            if st["memory"] is not None:
                m = st["memory"]
                m.golds = [[self.idx.pos[st["names"][g]] for g in gl if st["names"][g] in self.idx.pos]
                           for gl in m.golds]
                self.idx.memory = m
        self._archived: Index | None = None

    def archived_index(self) -> Index:
        if self._archived is None:
            arch = [s for s in corpus(include_archived=True) if s["state"] == "archived"]
            self.archived = {s["name"]: s for s in arch}
            self._archived = Index(arch, _cards(arch), self.enc)
            self._archived.weights.update(hist=0.0, hist_c=0.0, prior=0.0, sess=0.0)
        return self._archived

    def search(self, message: str, context: str = "", session: dict[str, int] | None = None, k: int = 5,
               include_archived: bool = False) -> list[dict]:
        feats = self.idx.features(message, context, session=session)
        self.last_need = float(self.gate.predict_proba(self.idx.last_raw[None, :])[0, 1]) if self.gate is not None else None
        s = self.idx.score(feats)
        order = s.argsort()[::-1][:k]
        out = [self._row(self.idx.names[i], float(s[i]), "active") for i in order]
        if include_archived:
            ai = self.archived_index()
            sa = ai.linear(ai.features(message, context))
            for i in sa.argsort()[::-1][:3]:
                out.append(self._row(ai.names[i], float(sa[i]), "archived"))
        return out

    def _row(self, name: str, score: float, state: str) -> dict:
        card = cards_mod.load(name) or {}
        s = self.by_name.get(name) or getattr(self, "archived", {}).get(name) or {}
        return {"name": name, "score": round(score, 4), "state": state, "summary": card.get("summary") or
                s.get("description", "")[:160], "domain": s.get("domain"), "path": s.get("path")}


CHOOSER_MODEL = "google/gemini-3.5-flash-lite"  # provisional holder of poste skills.chooser (bench P10.3)
CHOOSER_ASK = ("Skills are procedural guides the agent loads before acting. Below: the conversation, then candidate "
               "skills (name — when to use — example requests). List the skills the agent should load to handle the "
               "CURRENT user message, most useful first (at most 3; [] if none applies — e.g. chit-chat, thanks, a "
               "personal question). Prefer the specific skill over a generic one. Answer with JSON only: "
               '{"skills": ["name", ...]}')


def choose(message: str, context: str, shortlist: list[dict], privacy_class: str = "cloud_allowed",
           timeout: float = 4.0) -> list[str] | None:
    """Stage 2 (poste skills.chooser): a fast LLM picks among the local shortlist, or none. None = unavailable."""
    import re
    import sys as _sys
    _sys.path.insert(0, "/opt/walter-memory")
    from walter_memory import llm
    from walter_memory.logs import mask
    lines = []
    for r in shortlist:
        c = cards_mod.load(r["name"]) or {}
        ex = "; ".join((c.get("intents_fr") or [])[:3])
        lines.append(f"- {r['name']} — {r['summary'][:160]}" + (f" | e.g. {ex}" if ex else ""))
    prompt = (f"[previous turn]\n{mask(context[-800:])}\n[current user message]\n{mask(message[:1500])}\n\n"
              f"[candidate skills]\n" + "\n".join(lines) + f"\n\n{CHOOSER_ASK}")
    try:
        res = llm.chat([{"role": "user", "content": prompt}], model=CHOOSER_MODEL, processor="skills.chooser",
                       privacy_class=privacy_class, budget="recurring", timeout=timeout, purpose="skill choice")
        m = re.search(r"\{.*\}", res["content"], re.S)
        names = {r["name"] for r in shortlist}
        return [n for n in json.loads(m.group(0)).get("skills", []) if n in names][:3] if m else []
    except Exception:
        return None


def load_engine() -> Engine:
    return Engine()


def read_skill(name: str, file_path: str | None = None, include_archived: bool = True) -> str | None:
    s = store.find(name, include_archived=include_archived)
    if s is None:
        al = {store.frontmatter(x.body[:6000]).get("name"): x for x in store.iter_skills(include_archived=True)}
        s = al.get(name)
    if s is None:
        return None
    if file_path:
        p = (s.path / file_path).resolve()
        if not str(p).startswith(str(s.path.resolve())) or not p.is_file():
            return None
        return p.read_text(errors="replace")
    files = [str(p.relative_to(s.path)) for p in sorted(s.path.rglob("*"))
             if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and "__pycache__" not in p.parts]
    head = f"[walter-skills: {s.name} · {s.state} · {s.domain or '-'}]\n"
    tail = ("\n\n[Linked files — read with skill_read(name, file_path): " + ", ".join(files[:60]) + "]") if files else ""
    return head + s.body + tail
