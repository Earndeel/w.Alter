"""Capability discovery (lot 3e step 3, 2026-11-26): which tool answers a need, in French or English.

One lexical index (BM25, standard library only, no service, no embedding model) over one *card* per tool. A card is
never written by hand: it is derived each time from what the owners of the tool already maintain —
  - the tool's name, description and parameters (what every door shows),
  - its module's D1 line and the lines of the module's manifest (D2) and guide (D3) that name the tool,
  - its declaration in the module contract (effects, what it produces and consumes),
  - optionally, search intents a model wrote from that same source (`intents`), kept in the instance state and
    keyed by the hash of their source: when a description, a parameter or a declaration changes, the intents of
    that tool are stale and ignored until regenerated (`stale()` lists them) — never edited, never trusted stale.
Measured on the lot 3e needs (X0): BM25 over such cards beats the former word match and the hybrid with
embeddings; embeddings stay out until a measure shows they help.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

CARDS_VERSION = 1
INTENTS_PER_TOOL = {"intents_fr": 6, "intents_en": 3, "keywords": 5}

STOP = set("""le la les un une des de du d l et ou a au aux en dans sur pour par avec sans ce cet cette ces je tu il
elle on nous vous ils elles me moi te toi se mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs que qui quoi
quel quelle quels quelles est sont etre ai as avons avez ont pas ne plus mais donc car si fais fait faire peux peut veux
tout tous toute toutes ca cela ici y the a an of to in on for with and or is are be it its this that these those you
your i me my we our what which how do does can could use when from at by as into any all""".split())

# French words of a need → the English vocabulary the tools are described in. A language resource, not a card:
# it names no tool (the tool-specific wording lives in the tools' own descriptions and generated intents).
LEXICON = {
    "fichier": "file", "dossier": "directory folder", "repertoire": "directory", "lire": "read", "relire": "read",
    "relis": "read", "lis": "read", "ecrire": "write", "ecris": "write", "modifier": "edit", "modifie": "edit",
    "corrige": "edit fix", "chercher": "search find", "cherche": "search find", "recherche": "search",
    "rechercher": "search", "trouver": "find search", "trouve": "find search", "retrouve": "find search",
    "retrouver": "find search", "memoire": "memory", "souvenir": "memory remember", "souviens": "memory remember",
    "rappelle": "remember reminder", "retiens": "remember retain", "note": "note remember", "noter": "remember",
    "navigateur": "browser", "page": "web page", "site": "website web", "internet": "web", "ligne": "online",
    "commande": "command", "executer": "run execute", "execute": "run", "lancer": "run start", "lance": "run start",
    "tache": "task", "taches": "tasks", "travail": "job", "envoyer": "send", "envoie": "send", "envoi": "send",
    "message": "message", "messages": "messages", "repondre": "reply", "reponds": "reply", "personne": "person",
    "contact": "person contact", "ami": "person", "amie": "person", "agenda": "calendar", "calendrier": "calendar",
    "rendez": "appointment calendar", "image": "image", "photo": "image photo picture", "photos": "images photos",
    "capture": "screenshot", "ecran": "screen", "affiche": "poster image", "dessine": "draw image",
    "genere": "generate", "generer": "generate", "cree": "create", "creer": "create", "video": "video",
    "secret": "secret", "mot": "password", "passe": "password", "identifiant": "login credential",
    "connexion": "login", "connecte": "login", "agent": "agent", "deleguer": "delegate", "delegue": "delegate",
    "competence": "skill", "procedure": "skill procedure", "journal": "log", "historique": "history log",
    "coffre": "vault", "document": "document", "devis": "document quote", "facture": "document invoice",
    "son": "audio", "audio": "audio", "vocal": "voice audio", "transcris": "transcribe", "transcrire": "transcribe",
    "telegramme": "telegram", "courriel": "mail email", "mail": "mail email", "conversation": "conversation thread",
    "discussion": "conversation thread", "semaine": "week", "hier": "yesterday", "fonctionne": "working health status",
    "marche": "working health status", "etat": "status health state", "sante": "health", "panne": "health failure",
    "verifie": "check verify", "verifier": "check verify", "modele": "model", "cout": "cost price", "prix": "price",
    "abonnement": "subscription plan", "quota": "quota plan", "decide": "decide decision", "choisis": "choose decide",
    "question": "question ask", "demande": "ask", "demander": "ask", "ordinateur": "computer", "mac": "computer mac",
    "clique": "click", "tape": "type", "module": "module", "profil": "profile", "preference": "preference profile",
    "carte": "card", "resume": "summary", "synthese": "synthesis summary", "sais": "know", "savoir": "know",
    "tableau": "board", "telecharge": "download", "telecharger": "download", "enregistre": "save store",
    "range": "store", "garde": "keep store", "sous-agent": "subagent", "arrete": "stop interrupt",
    "interromps": "interrupt", "liste": "list", "lister": "list", "calcule": "compute python", "calcul": "compute",
}


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower()) if not unicodedata.combining(c))


def _stem(w: str) -> str:
    if len(w) > 3 and w.endswith(("s", "x")) and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    return w[:6]                      # light stemming for French and English (measured: 5, 6, 7, none)


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", fold(text).replace("_", " ")) if len(w) > 1 and w not in STOP]


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in words(text)]


def query_tokens(query: str) -> list[str]:
    """The need's words, then the English words they may be written as in the tools' vocabulary."""
    out = []
    for w in words(query):
        out.append(_stem(w))
        en = LEXICON.get(w) or LEXICON.get(w.rstrip("s"))
        if en:
            out += [_stem(x) for x in en.split() if _stem(x) != _stem(w)]
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.n = len(docs)
        avg = (sum(len(d) for d in docs) / self.n) if self.n else 1.0
        df = Counter(w for d in docs for w in set(d))
        self.post: dict[str, list[tuple[int, float]]] = {}
        for i, d in enumerate(docs):
            for w, f in Counter(d).items():
                idf = math.log(1 + (self.n - df[w] + 0.5) / (df[w] + 0.5))
                self.post.setdefault(w, []).append((i, idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / (avg or 1)))))

    def scores(self, q: list[str]) -> list[float]:
        out = [0.0] * self.n
        for w, k in Counter(q).items():
            for i, v in self.post.get(w, ()):
                out[i] += v * (1 + 0.25 * (k - 1))
        return out


# ── the card: everything derived, nothing written for search ─────────────────────────────────────────────────────
def source_text(tool: dict) -> str:
    """What a generated intent is derived from (and keyed on): name (the short one, the same through every door),
    description, parameters, declaration."""
    params = (tool.get("parameters") or {}).get("properties") or {}
    spec = tool.get("spec") or {}
    return json.dumps({"name": tool["name"].removeprefix("mcp__walter__"), "description": tool.get("description") or "",
                       "parameters": {k: (v or {}).get("description", "") for k, v in sorted(params.items())},
                       "effects": spec.get("effects"), "produces": spec.get("produces"),
                       "consumes": spec.get("consumes")}, ensure_ascii=False, sort_keys=True)


def source_hash(tool: dict) -> str:
    return hashlib.sha256(source_text(tool).encode()).hexdigest()[:16]


def module_lines(module_texts: dict[str, str], module: str | None, name: str) -> list[str]:
    """Lines of the module's own presentation (D1 line, manifest, guide) that name the tool."""
    text = module_texts.get(module or "") or ""
    pat = re.compile(rf"`{re.escape(name)}[`(]")
    return [re.sub(r"\s+", " ", ln.strip("-|*# ").strip())[:400] for ln in text.splitlines() if pat.search(ln)]


def card(tool: dict, module_texts: dict[str, str] | None = None, intents: dict | None = None) -> dict:
    name = tool["name"]
    short = name.removeprefix("mcp__walter__")
    params = (tool.get("parameters") or {}).get("properties") or {}
    spec = tool.get("spec") or {}
    mod = tool.get("module")
    fields = {
        "name": short.replace("_", " "),
        "description": tool.get("description") or "",
        "module": " ".join([mod or "", (module_texts or {}).get(f"{mod}:d1", "")]),
        "guide": " ".join(module_lines(module_texts or {}, mod, short)),
        "declaration": " ".join([" ".join(spec.get("effects") or []).replace("_", " "),
                                 " ".join(spec.get("produces") or []), " ".join(spec.get("consumes") or [])]),
        "parameters": " ".join(f"{k.replace('_', ' ')} {(v or {}).get('description', '')}" for k, v in params.items()),
    }
    fresh = bool(intents) and intents.get("source") == source_hash(tool)
    if fresh:
        fields["intents"] = " ".join(intents.get("intents_fr", []) + intents.get("intents_en", [])
                                     + intents.get("keywords", []))
    return {"name": name, "module": mod, "fields": fields, "intents": "fresh" if fresh else
            ("stale" if intents else "none")}


WEIGHTS = {"name": 3, "description": 1, "module": 1, "guide": 1, "declaration": 1, "parameters": 1, "intents": 1}


def _doc(c: dict) -> list[str]:
    out = []
    for f, w in WEIGHTS.items():
        out += tokens(c["fields"].get(f, "")) * w
    return out


class Index:
    """Search over the given tools: [{name, description, parameters, module, spec}]."""

    def __init__(self, tools: list[dict], module_texts: dict[str, str] | None = None,
                 intents: dict[str, dict] | None = None):
        intents = intents or {}
        self.tools = tools
        self.cards = [card(t, module_texts, intents.get(t["name"].removeprefix("mcp__walter__"))) for t in tools]
        self.bm = BM25([_doc(c) for c in self.cards])

    def search(self, query: str, limit: int = 8) -> list[dict]:
        q = query_tokens(query)
        limit = max(1, min(50, int(limit or 8)))
        if not q:
            ranked = sorted(range(len(self.tools)), key=lambda i: self.tools[i]["name"])
            return [self._row(i, 0.0) for i in ranked[:limit]]
        s = self.bm.scores(q)
        ranked = sorted((i for i in range(len(s)) if s[i] > 0), key=lambda i: (-s[i], self.tools[i]["name"]))
        return [self._row(i, s[i]) for i in ranked[:limit]]

    def _row(self, i: int, score: float) -> dict:
        t = self.tools[i]
        spec = t.get("spec") or {}
        row = {"name": t["name"], "description": (t.get("description") or "")[:240]}
        if t.get("module"):
            row["module"] = t["module"]
        if spec.get("effects"):
            row["effects"] = spec["effects"]
        row["score"] = round(score, 2)
        return row


# ── module texts: the owners' own presentation files, read through the presentation layer ───────────────────────
def module_texts() -> dict[str, str]:
    """{module: manifest + guide text, "<module>:d1": D1 line} for every module with a presentation. Fail-soft: a
    module whose files cannot be read only loses its lines."""
    from . import presentation
    out: dict[str, str] = {}
    for m in presentation._entries(None):
        mid, parts = m["id"], []
        for fn in (presentation.manifest, presentation.guide):
            try:
                parts.append(fn(mid))
            except Exception:  # noqa: BLE001 — a missing file never breaks discovery
                pass
        out[mid] = "\n".join(parts)
        try:
            out[f"{mid}:d1"] = presentation.summary(mid)
        except Exception:  # noqa: BLE001
            out[f"{mid}:d1"] = ""
    return out


# ── generated intents: cache keyed by source, regenerated, never edited ─────────────────────────────────────────
def cards_path() -> Path:
    from . import instance
    return Path(instance.state("core", "capabilities", "cards.json"))


def load_intents(path: Path | None = None) -> dict[str, dict]:
    try:
        doc = json.loads(Path(path or cards_path()).read_text())
    except (OSError, ValueError):
        return {}
    if doc.get("version") != CARDS_VERSION:
        return {}
    out = {}
    for name, entry in (doc.get("tools") or {}).items():
        if not isinstance(entry, dict) or entry.get("card") != _entry_hash(entry):
            continue                              # edited by hand (or torn): ignored, like a stale one
        out[name] = entry
    return out


def _entry_hash(entry: dict) -> str:
    body = {k: entry.get(k) for k in ("source", *INTENTS_PER_TOOL)}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def stale(tools: list[dict], intents: dict[str, dict]) -> list[str]:
    """Tools whose intents are missing or were derived from another version of their source."""
    return sorted(t["name"].removeprefix("mcp__walter__") for t in tools
                  if (intents.get(t["name"].removeprefix("mcp__walter__")) or {}).get("source") != source_hash(t))


def generation_prompt(tools: list[dict]) -> str:
    body = "\n".join(f"### {t['name'].removeprefix('mcp__walter__')}\n{source_text(t)[:1500]}" for t in tools)
    return ("For each tool below, write its search card: 6 intents in everyday French (how a person would phrase the "
            "need, without the tool's name), 3 in English, and 5 keywords. Answer only with one JSON object "
            "{\"cards\": {\"<name>\": {\"intents_fr\": [...], \"intents_en\": [...], \"keywords\": [...]}}}.\n\n" + body)


def parse_generated(text: str, tools: list[dict]) -> dict[str, dict]:
    """A model's answer → entries for the tools it was asked about (anything else is dropped)."""
    try:
        cards = json.loads(text[text.find("{"): text.rfind("}") + 1]).get("cards") or {}
    except (ValueError, AttributeError):
        return {}
    out = {}
    for t in tools:
        short = t["name"].removeprefix("mcp__walter__")
        c = cards.get(short)
        if not isinstance(c, dict):
            continue
        entry = {"source": source_hash(t)}
        for k, n in INTENTS_PER_TOOL.items():
            entry[k] = [str(x)[:200] for x in (c.get(k) or []) if isinstance(x, str)][: n + 2]
        entry["card"] = _entry_hash(entry)
        out[short] = entry
    return out


def save_intents(entries: dict[str, dict], path: Path | None = None, *, keep: set[str] | None = None) -> Path:
    """Merge regenerated entries into the cache; `keep` (the live tool names) drops entries of removed tools."""
    p = Path(path or cards_path())
    current = load_intents(p)
    current.update(entries)
    if keep is not None:
        current = {k: v for k, v in current.items() if k in keep}
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": CARDS_VERSION, "tools": dict(sorted(current.items()))},
                              ensure_ascii=False, indent=1) + "\n")
    tmp.chmod(0o600)
    tmp.replace(p)
    return p
