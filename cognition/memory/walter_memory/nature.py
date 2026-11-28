"""Nature × portée of a piece of knowledge (owner 2026-11-25, M1–M5): two independent dimensions, ONE vocabulary for
every mechanism that types, writes, consolidates, re-types or restitutes knowledge. Nothing here is a second store:
both dimensions are attributes of the same core.derived_items rows, written through the same gate (knowledge.Gate).

- nature = attributes.act (the existing field, its rule value refined): consigne `instruction`, `preference`,
  `opinion`, fait `fact`, `decision`, objectif `goal`. The process acts (proposal, hypothesis, action, result, state,
  cancel) are unchanged. A fact correction is a fact (attributes.corrects), a correction of Walter's way of acting is
  a consigne.
- portée = attributes.reach (+ attributes.reach_on, what it is limited to): `universal`, `project`, `domain`
  (a kind of activity or subject), `person`, `situation`, `task`. A real consigne is not necessarily universal:
  only the consignes applicable to the message are given to the general model as instructions (applicable()).

kind (the readers' vocabulary) and domain (the filing: personal / project / task / relation / test) stay. For a new
statement they follow from nature and portée (KIND_OF, DOMAIN_OF). Stock items keep their kind and domain: re-typing
(retype) adds nature and portée through the gate under a tag — knowledge.revert(tag) undoes it field by field —
memoised on its exact inputs (processing.decide_once); nothing is deleted, sources, dates, provenance and privacy
classes are untouched.

Switches (organic.toml): [nature] extraction = "v3" | "v4" (the typed prompt with consigne, opinion and portée),
[nature] restitution = "rules" | "applicable" (M3), [stages] retype = "paused" | "active" (M5, the catch-up loop)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from . import privacy
from .db import connection

log = logging.getLogger("walter.nature")

# ───────────────────────────── vocabulary ─────────────────────────────
# code: (kind of a new statement, word in the prompts, definition in the prompts)
NATURES = {
    "instruction": ("constraint", "consigne",
                    "ce que Walter doit faire, ou comment il doit agir, répondre ou travailler, dit par Monsieur à "
                    "Walter, et qui vaudra encore la prochaine fois que la même situation se présentera (dans les "
                    "limites que dit sa portée) ; une demande ponctuelle est un objectif ; une consigne peut ne valoir "
                    "que pour un projet, un domaine, une personne, une situation ou la tâche en cours"),
    "preference": ("preference", "preference",
                   "un goût ou un choix stable de Monsieur (style, outil, format, manière de faire, priorité) qui "
                   "oriente sans obliger"),
    "opinion": ("fact", "opinion",
                "un jugement, un avis, une appréciation ou une croyance de quelqu'un sur quelque chose ou quelqu'un "
                "(un agacement passager, une critique, un « c'est nul ») : ce n'est ni une règle ni un fait"),
    "fact": ("fact", "fait",
             "une information déclarée sur une vie, une situation, un système, une personne ; une information "
             "corrigée reste un fait"),
    "decision": ("decision", "decision", "un choix tranché sur un point précis (souvent d'un projet)"),
    "goal": ("goal", "objectif", "ce que Monsieur veut atteindre ou faire faire"),
}
REACHES = {
    "universal": ("personal", "universelle",
                  "vaut quel que soit le sujet de la demande ; c'est le cas de ce qui concerne Monsieur lui-même et la "
                  "façon dont Walter lui répond, lui parle ou travaille pour lui en général"),
    "project": ("project", "projet", "ne vaut que pour un projet ou un module précis (sur = son identifiant)"),
    "domain": ("personal", "domaine",
               "ne vaut que pour un type d'activité ou de sujet (sur = lequel : le code, les sous-titres vidéo, "
               "les e-mails, la cuisine…)"),
    "person": ("relation", "personne",
               "ne vaut que pour une autre personne que Monsieur, ou les échanges avec elle (sur = qui)"),
    "situation": ("personal", "situation",
                  "ne vaut que dans une situation donnée (sur = laquelle : en voyage, en réunion, le soir…)"),
    "task": ("task", "tache", "ne vaut que pour le travail en cours"),
}
_FOLD = str.maketrans({**dict(zip("éèêëàâäîïôöûùüç", "eeeeaaaiioouuuc")), "œ": "oe", "æ": "ae"})
NATURE_ALIASES = {**{v[1]: k for k, v in NATURES.items()}, **{k: k for k in NATURES},
                  "fait": "fact", "objectif": "goal", "consignes": "instruction", "avis": "opinion"}
REACH_ALIASES = {**{v[1]: k for k, v in REACHES.items()}, **{k: k for k in REACHES},
                 "tache": "task", "tâche": "task", "universel": "universal", "projet": "project"}
KIND_OF = {k: v[0] for k, v in NATURES.items()}
DOMAIN_OF = {k: v[0] for k, v in REACHES.items()}
# acts written before 2026-11-25 whose nature is not known: « rule » (preference / contrainte mixed), « correction »
# (a fact or a consigne), and no act at all (before the typed statements of 19/11)
UNTYPED_ACTS = {None, "", "rule", "correction"}
RULE_KINDS = ("constraint", "preference", "correction")


def norm_nature(v) -> str | None:
    return NATURE_ALIASES.get(str(v or "").strip().lower().translate(_FOLD))


def norm_reach(v) -> str | None:
    return REACH_ALIASES.get(str(v or "").strip().lower().translate(_FOLD))


OWNER_WORDS = {"monsieur", "owner", "proprietaire", "lui", "meme"}   # « personne : Monsieur (lui-même) » = the owner


def door(nature: str | None, reach: str | None, *, channel: str | None,
         on: str | None = None) -> tuple[str | None, str | None, str | None]:
    """The write door's rule on the two dimensions, the same for extraction and re-typing → (nature, reach, note).
    A conversation with a contact never yields a consigne: Monsieur talks to someone else, not to Walter — it is kept
    as a preference (nothing is dropped). A portée « person » that is Monsieur himself is universal: Walter always
    talks to him, so what holds for him holds for every message (the reach_on is then dropped by the caller)."""
    note = None
    if nature == "instruction" and channel == "contact":
        nature, note = "preference", "canal contact : une consigne à Walter ne vient jamais d'une conversation avec un contact"
    if reach == "person" and on and _words(on) and _words(on) <= OWNER_WORDS:
        reach = "universal"
    return nature, reach, note


def guide(*, contact: bool = False) -> str:
    """The definitions every prompt uses (extraction v4, re-typing): one text, so both type alike."""
    nat = [f"- {NATURES[k][1]} : {NATURES[k][2]} ;" for k in NATURES if not (contact and k == "instruction")]
    reach = [f"- {REACHES[k][1]} : {REACHES[k][2]} ;" for k in REACHES]
    extra = ("Une conversation avec un contact ne contient jamais de consigne à Walter : ce que Monsieur y veut ou "
             "aime est une préférence, ce qu'il y pense est une opinion.\n") if contact else (
             "Une question ou un agacement de Monsieur n'est pas une consigne. Une consigne n'est pas forcément "
             "universelle : sa portée dit où elle s'applique.\n")
    return ("Nature (ce qu'est l'énoncé) :\n" + "\n".join(nat) + "\n" + extra +
            "Portée (où il s'applique, indépendamment de sa nature ; sur = ce à quoi il est limité, null si "
            "universelle) :\n" + "\n".join(reach))


def settings() -> dict:
    from . import organic
    return {**{"extraction": "v3", "restitution": "rules"}, **(organic.settings().get("nature") or {})}


def restitution_on() -> bool:
    return settings().get("restitution") == "applicable"


# ───────────────────────────── restitution (M3) ─────────────────────────────
_WORD = re.compile(r"[a-z0-9]{3,}")          # « walter-router » = « Walter Router », « sous-titres » = « sous titres »
_STOP = {"les", "des", "une", "pour", "dans", "avec", "sur", "par", "son", "ses", "the", "and", "walter"}


def _words(s: str) -> set[str]:
    return {w for w in _WORD.findall((s or "").lower().translate(_FOLD)) if w not in _STOP}


def applicable(item: dict, message: str, *, sim: float | None, threshold: float,
               projects: list[str] | tuple = ()) -> bool:
    """Does this consigne apply to the message? universal → always; project → the message is about that project
    (named, or found by Memory's project catalogue) or close to the consigne; domain, person, situation → the message
    is about what it is limited to (its words) or close to it (local cosine above threshold); task → never here (the
    thread's working state carries the rules of its own work). Model-free."""
    reach = item.get("reach") or "universal"
    if reach == "universal":
        return True
    if reach == "task":
        return False
    on = item.get("reach_on") or ""
    if reach == "project" and on:
        p = _key(on)
        if p and any(p == _key(x) or p.startswith(_key(x)) or _key(x).startswith(p) for x in projects if _key(x)):
            return True
    return mentions(on, message) or (sim or 0) > threshold


def _key(project: str) -> str:
    """« project:walter-router », « Walter Router », « walterrouter » → « walterrouter »."""
    return re.sub(r"[^a-z0-9]", "", str(project or "").split(":", 1)[-1].lower().translate(_FOLD))


def mentions(on: str | None, message: str) -> bool:
    """The message names what a statement is limited to (every significant word of its reach_on)."""
    w = _words(on or "")
    return bool(w) and w <= _words(message)


def reader_kind(kind: str, attributes: dict | None) -> str:
    """The kind a reader files an item under once natures are restituted (M3): its nature when known — an opinion is
    filed with the facts, never with the rules; a consigne with the constraints — else its stored kind (not typed
    yet). The stored kind is never rewritten by re-typing (reversible, production unchanged until the switch)."""
    act = (attributes or {}).get("act")
    return KIND_OF[act] if act in NATURES else kind


def reader_text(content: str, attributes: dict | None) -> str:
    """An opinion is shown as one (never as a rule or a plain fact)."""
    return f"(avis) {content}" if (attributes or {}).get("act") == "opinion" else content


# ───────────────────────────── re-typing (M4 stock, M5 catch-up loop) ─────────────────────────────
NEED, VERSION = "memory.retype", "1"
POSTE = "memory_extraction"          # the poste that types new statements types the old ones (same definitions)
BATCH = 20
PROMPT ="""Tu ranges des connaissances déjà enregistrées dans la mémoire de Walter (l'assistant de Monsieur) selon deux dimensions indépendantes : leur nature et leur portée. Ne réécris rien, ne juge pas si c'est vrai ; seul le texte compte, pas la case où il est rangé aujourd'hui.

{guide}

Énoncés (identifiant · rangé aujourd'hui · qui l'a dit · sujet · canal ; texte ; citation d'origine) :
{items}

Rends UNIQUEMENT un JSON : {{"<identifiant>": {{"nature": "consigne|preference|opinion|fait|decision|objectif|autre", "portee": "universelle|projet|domaine|personne|situation|tache", "sur": "le projet, le domaine, la personne ou la situation ; null si universelle"}}, ...}}"""
PROMPT_HASH = hashlib.sha256((PROMPT + guide()).encode()).hexdigest()[:16]
WHO = {"stated_owner": "Monsieur", "agent_reported": "Walter", "stated_third_party": "un tiers", "inferred": "déduit"}


def pending(conn, limit: int, *, only: list[str] | None = None, rules_only: bool = False) -> list[dict]:
    """Live g1 knowledge whose nature or portée is not known, the kinds the rule layer reads first, newest first.
    An item a re-typing could not settle (typing.status unclear) is not asked again by the same version."""
    return conn.execute("""
        select item_id::text, kind, content, privacy_class, epistemic, attributes
        from core.derived_items
        where derived_by = 'l3.extract' and generation = 'g1' and status in ('derived', 'verified')
          and (valid_to is null or valid_to > now())
          and (coalesce(attributes->>'act', '') in ('', 'rule', 'correction') or not attributes ? 'reach')
          and coalesce(attributes->'typing'->>'version', '') <> %s
          and coalesce(attributes->>'domain', '') <> 'test'
          and (not %s or kind = any(%s))
          and (%s::uuid[] is null or item_id = any(%s::uuid[]))
        order by (kind = any(%s)) desc, created_at desc limit %s""",
                        (VERSION, rules_only, list(RULE_KINDS), only, only, list(RULE_KINDS), limit)).fetchall()


def _line(key: str, r: dict) -> str:
    a = r["attributes"] or {}
    head = " · ".join(x for x in (key, f"{r['kind']}/{a.get('act') or '?'}", WHO.get(r["epistemic"] or "", "?"),
                                  a.get("subject") or "", a.get("channel") or "agent") if x)
    quote = (a.get("quote") or "").strip()
    return f"{head}\n  {r['content'][:500]}" + (f"\n  « {quote[:200]} »" if quote and quote not in r["content"] else "")


def classify(batch: list[dict], *, budget: str = "backfill", chat=None) -> dict[str, dict]:
    """One model call for a batch (same privacy class) → {item_id: {"nature", "reach", "reach_on", "model"}}, memoised
    on its exact inputs: a replay never asks again. Unknown answers are left None (the item stays to type)."""
    from . import llm, processing
    chat = chat or llm.chat
    keys = {f"E{i + 1}": r for i, r in enumerate(batch)}
    cls = privacy.strictest(*(r["privacy_class"] for r in batch))
    inputs = {"prompt": PROMPT_HASH, "items": [[r["item_id"], r["kind"], r["content"], (r["attributes"] or {}).get("act"),
                                                 (r["attributes"] or {}).get("subject"),
                                                 (r["attributes"] or {}).get("channel"), r["epistemic"]] for r in batch]}

    def call():
        res = chat([{"role": "user", "content": PROMPT.format(guide=guide(),
                                                              items="\n".join(_line(k, r) for k, r in keys.items()))}],
                   poste=POSTE, processor=NEED, processor_version=VERSION, privacy_class=cls, budget=budget,
                   purpose=f"retype {len(batch)} items", response_format={"type": "json_object"}, max_tokens=4000,
                   timeout=240)
        c = res["content"] or ""
        data = json.loads(c[c.find("{"):c.rfind("}") + 1])
        return {k: data.get(k) or {} for k in keys}, res.get("model")

    outcome, _ = processing.decide_once(NEED, VERSION, inputs, call, privacy_class=cls,
                                        refs=[r["item_id"] for r in batch])
    out = {}
    for k, r in keys.items():
        o = outcome.get(k) or {}
        reach = norm_reach(o.get("portee"))
        on = o.get("sur") if isinstance(o.get("sur"), str) and o.get("sur").strip().lower() not in ("", "null", "none") else None
        out[r["item_id"]] = {"nature": norm_nature(o.get("nature")), "reach": reach,
                             "reach_on": (on or "").strip()[:120] or None if reach not in (None, "universal") else None}
    return out


def typed_attributes(r: dict, res: dict, now: str) -> tuple[dict, bool]:
    """The attributes a re-typing writes for one stock item (r: item_id, kind, attributes; res: classify()'s answer)
    → (new attributes, typed?). One function for the write (retype) and for any what-if reading (bench).
    A typed act keeps its value (a process act — proposal, action, result… — or a v3 fact, decision, goal); only an
    opinion the typed extraction filed as a fact is refined. An untyped decision, goal or commitment keeps the act its
    kind gave it. Portée is added either way. The write door applies (a contact's consigne is a preference)."""
    a = dict(r["attributes"] or {})
    old_act = a.get("act")
    nature = res["nature"]
    if old_act not in UNTYPED_ACTS or (not old_act and r["kind"] not in RULE_KINDS + ("fact",)):
        known = old_act or {"decision": "decision", "goal": "goal", "commitment": "action"}.get(r["kind"])
        nature = "opinion" if known == "fact" and nature == "opinion" else (known if nature else None)
    nature, reach, note = door(nature, res["reach"], channel=a.get("channel"), on=res["reach_on"])
    if nature is None or reach is None:
        return {**a, "typing": {"version": VERSION, "status": "unclear", "at": now}}, False
    new = {**a, "act": nature, "reach": reach,
           "typing": {"version": VERSION, "from": {"act": old_act}, "at": now, **({"note": note} if note else {})}}
    if res["reach_on"] and reach != "universal":
        new["reach_on"] = res["reach_on"]
    if old_act == "correction" or r["kind"] == "correction":
        new["corrects"] = True
    return new, True


def retype(limit: int = 200, *, apply: bool = False, tag: str | None = None, only: list[str] | None = None,
           rules_only: bool = False, budget: str = "backfill", chat=None) -> dict:
    """Type the nature and portée of stock items (M4) — the same slice runs in the catch-up loop (M5). Dry run unless
    apply: the classification is still made and memoised (a later apply reuses it, no second call). apply writes
    attributes.act / reach / reach_on / corrects and attributes.typing {version, from, model, at} through the gate,
    under tag (default retype-YYYY-MM-DD): knowledge.revert(tag) undoes it. kind, domain, content, sources, dates,
    provenance and privacy are never changed; local_only items are typed only if the privacy door lets them go."""
    from . import knowledge
    tag = tag or f"retype-{datetime.now(timezone.utc):%Y-%m-%d}"
    out = {"tag": tag, "apply": apply, "items": 0, "typed": 0, "unclear": 0, "refused": 0, "changed": 0,
           "natures": {}, "reaches": {}, "moves": {}}
    with connection() as conn:
        rows = pending(conn, limit, only=only, rules_only=rules_only)
    by_cls: dict[str, list[dict]] = {}
    for r in rows:
        by_cls.setdefault(r["privacy_class"], []).append(r)
    results: dict[str, dict] = {}
    for cls, rs in by_cls.items():
        for i in range(0, len(rs), BATCH):
            part = rs[i:i + BATCH]
            try:
                results.update(classify(part, budget=budget, chat=chat))
            except Exception as e:  # noqa: BLE001 — refused (privacy, quota) or failed: these stay to type
                out["refused"] += len(part)
                log.warning("retype batch (%s, %d items) not typed: %s", cls, len(part), type(e).__name__)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        res = results.get(r["item_id"])
        if res is None:
            continue
        out["items"] += 1
        new, typed = typed_attributes(r, res, now)
        if not typed:
            out["unclear"] += 1
        else:
            out["typed"] += 1
            nature, reach = new["act"], new["reach"]
            out["natures"][nature] = out["natures"].get(nature, 0) + 1
            out["reaches"][reach] = out["reaches"].get(reach, 0) + 1
            mv = f"{r['kind']}/{(r['attributes'] or {}).get('act') or '∅'}→{nature}"
            out["moves"][mv] = out["moves"].get(mv, 0) + 1
        if not apply:
            continue
        with connection() as conn:
            gate = knowledge.Gate(conn, generation="g1", tag=tag, segment=None)
            st = gate.change(r["item_id"], {"attributes": new}, op="attribute", key=f"retype:{VERSION}:{r['item_id']}",
                             decided_by=f"{NEED}:{POSTE}", reason="nature × portée (M4/M5, 2026-11-25)")
            out["changed"] += st == "applied"
    if apply:
        with connection() as conn:
            out["remaining"] = len(pending(conn, 100000, rules_only=rules_only))
    return out
