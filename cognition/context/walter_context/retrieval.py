"""retrieval: what the ContextPlan asks for, fetched from the modules that own it, as blocks (lot 4, step D).

Every source is reached through its public interface: Walter Memory's library (views, context: same process,
warm), the `walter present` command for module capabilities (core), walter_logs through Walter Memory's logs API.
A block knows its layer (stable → volatile), whether the host already shows it natively (Claude Code keeps its own
history: the recent exchanges are then counted, not injected) and its sources. Nothing here calls a cloud model
except Walter Memory's context assembly at L3/L4, which applies its own privacy rules (cloud-safe, rerank).
Fail-open per block: a source that fails gives no block and a note, never an exception.
Budgets and bounds: [pack] in config/walter-context.toml (the only place). Tasks and execution experience (SOCLE A3/A4)
come from Walter Memory's gateway routes `POST /v1/tasks/list` and `POST /v1/experience`; Memory's context assembly is
asked for those layers at 0 so the pack never shows them twice.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .config import dedupe_settings, pack_settings
from .plan import ContextPlan
from .preflight import _words

# capability → module whose brief (M1) the model gets in full; every module's one line (M0) is always there
CAPABILITY_MODULES = {"skills": ["skills"], "memory": ["memory"], "web": ["browse"], "browser": ["browse", "computer"],
                      "delegation": ["router"], "secrets": ["secrets"]}
DOMAIN_MODULES = {"relations": ["memory"], "agenda": ["memory"], "profile": ["memory"], "activities": ["memory"],
                  "decisions": ["memory"], "goals": ["memory"],
                  "walter": ["walter"]}      # lot 3d: W.Alter's own D2 (its organisation and every module's D1)
NO_MEMORY_DOMAINS = {"projects", "walter"}     # domains that alone do not open the owner's memory at L1/L2
SUBJECT_DEPTH = {"L0": None, "L1": "index", "L2": "overview", "L3": "synthesis", "L4": "synthesis"}
PACK = pack_settings()
DEDUPE = dedupe_settings()                       # payload lot 1 (23/11): said once
MEMORY_BUDGET = PACK["memory_budget"]           # L3 / L4 sections of Memory's context assembly
RECORDS_BUDGET = PACK["records_budget"]
STATE_BUDGET = PACK["state_budget"]             # layer 2 (Memory V1 P1.1): every level but L0 without a thread
UNSURE_PLAN = PACK["unsure_plan"]               # below this plan confidence, the cheap records lookup is added
BOARD_TOKENS = PACK["board_tokens"]
RECENT_EXCHANGES = PACK["recent_exchanges"]
NOT_HERE = {"tasks": 0, "experience": 0}        # served by their own blocks, never twice through Memory's assembly
GATEWAY = os.environ.get("WALTER_MEMORY_URL", "http://127.0.0.1:8890")


@dataclass
class Block:
    id: str
    layer: int                  # 0 stable (session) … 5 volatile (this message)
    text: str
    injected: bool = True       # False: the host already shows it (counted for the comparison only)
    sources: list = field(default_factory=list)
    ms: float = 0.0

    @property
    def tokens(self) -> int:
        return len(self.text) // 4 + 1 if self.text else 0

    def summary(self) -> dict:
        return {**{k: v for k, v in asdict(self).items() if k != "text"}, "tokens": self.tokens}


_NOTES: list = []                               # [(fetched at, notes)]
_NOTES_LOCK = threading.Lock()
_NOTES_REFRESH: list = []                       # the background refresh running, if any


def _fetch_notes() -> list[dict]:
    mods = sorted({m for table in (CAPABILITY_MODULES, DOMAIN_MODULES, TOOL_CARD_MODULES)
                   for ms in table.values() for m in ms})
    out = json.loads(subprocess.run(["walter", "present", "notes", "--form", "m0", "--m1", ",".join(mods)],
                                    capture_output=True, text=True, timeout=20).stdout)
    return out.get("notes") or []


def _refresh_notes() -> None:
    try:
        notes = _fetch_notes()
        with _NOTES_LOCK:
            _NOTES[:] = [(time.time(), notes)]
    except Exception:  # noqa: BLE001 — the notes in hand stay; the next message past the ttl tries again
        pass
    finally:
        _NOTES_REFRESH.clear()


def _notes(ttl: float = 600) -> list[dict]:
    """Every module's M0 and the M1 of every module a plan can name, from ONE `walter present` call per ttl
    (2026-11-16). One call per module set, each with its own 10-minute cache, cost a subprocess at most messages
    (0.6–1.5 s measured in the service). Filtering the full call gives exactly the notes a call for a subset gives
    (42 sets compared on 2026-11-16).
    Past the ttl the notes in hand are answered and ONE refresh runs beside (17/11, critical path §9: the owner's
    messages are often more than 10 minutes apart, so the expired cache put the 1.2 s subprocess on most turns —
    tool cards p50 1.19 s in the 16–17/11 records). A module's presentation changes with a deployment, rarely: it is
    at most one message late. Only the very first call of the process waits for the subprocess."""
    with _NOTES_LOCK:                           # sources asking together wait for one call, not one each
        if _NOTES:
            if time.time() - _NOTES[0][0] >= ttl and not _NOTES_REFRESH:
                t = threading.Thread(target=_refresh_notes, name="notes-refresh", daemon=True)
                _NOTES_REFRESH.append(t)
                t.start()
            return _NOTES[0][1]
        notes = _fetch_notes()
        _NOTES[:] = [(time.time(), notes)]
        return notes


def _subset(notes: list[dict], m1: set[str]) -> list[dict]:
    """What `walter present notes --form m0 --m1 <m1>` gives: every M0 note, and the M1 (manifest) of m1 only."""
    return [n for n in notes if not str(n.get("id", "")).endswith(".manifest") or n.get("module") in m1]


def capabilities(plan: ContextPlan, ttl: float = 600) -> Block | None:
    """M0 of every module, one line each (session layer: the same for every message, so the provider's prefix cache
    keeps it). The M1 briefs of the modules a message needs come once, in tool_cards (layer 4). Until 18/11 this block
    also carried them: every memory, web or secrets request had the same brief twice (memory 440 tokens, browse 292),
    and the cached prefix changed with each plan's capabilities."""
    notes = _subset(_notes(ttl), set())
    text = "\n\n".join(n["content"].strip() for n in notes if n.get("content"))
    return Block("capabilities", 0, text, sources=[n.get("id") for n in notes])


# capability → modules whose agent brief (M1) is shown *for this message* (tool cards, layer 4): the host lists only a
# core toolset and every module's one line (M0), so the plan says which modules' tools fit the request (07/11: a web
# question answered with `curl` from the VM because nothing pointed at walter_browse). Delegation has none: the engine
# delegates through its own `subagent` tool; which modules' guide helps a message is question set 3's D question (P4).
TOOL_CARD_MODULES = {"web": ["browse"], "browser": ["browse", "computer"], "secrets": ["secrets"],
                     "memory": ["memory"], "skills": ["skills"]}


def _card(module: str, ttl: float = 600) -> str:
    return "\n\n".join(n["content"].strip() for n in _subset(_notes(ttl), {module})
                       if n.get("module") == module and str(n.get("id", "")).endswith(".manifest") and n.get("content"))


def tool_cards(plan: ContextPlan) -> Block | None:
    """The briefs of the modules the plan's capabilities need, in the volatile layer (the cached prefix stays the same)."""
    mods = list(dict.fromkeys([*(m for c in plan.capabilities for m in TOOL_CARD_MODULES.get(c, [])),
                               *(m for d in plan.domains for m in DOMAIN_MODULES.get(d, []))]))
    texts = [(m, _card(m)) for m in mods]
    texts = [(m, t) for m, t in texts if t]
    if not texts:
        return None
    return Block("tool_cards", 4, "W.Alter modules for this request:\n\n" + "\n\n".join(t for _, t in texts),
                 sources=[m for m, _ in texts])


RECENT_BY_HORIZON = {"instant": 6, "day": 24}   # hours: a plan about right now shows only what moved right now
_BOARD_LINE = re.compile(r"^- (?P<key>\S+) · (?P<body>.*?)(?: — (?P<state>[\w_]+))? · (?P<d>\d\d)/(?P<m>\d\d) (?P<hm>\d\d:\d\d)$")


def board(plan: ContextPlan | None = None, at: datetime | None = None) -> Block | None:
    """The subjects that matter now, one line each: the plan's own thread (and its alternates) first, then subjects
    still open (board_states) active within board_recent_hours (6 h / 24 h when the plan's horizon is instant / day),
    at most board_max_lines. Before 11/11 it was the whole table (17 lines, mostly done or unrelated)."""
    from walter_memory import views
    at = at or datetime.now(timezone.utc)
    r = views.read({"depth": "index", "domain": "projects", "horizon": "medium", "max_tokens": 4000})
    mine = [k for k in ([plan.thread.id] + list(plan.thread.alternates) if plan else []) if k]
    hours = min([RECENT_BY_HORIZON[h] for h in (plan.horizons if plan else []) if h in RECENT_BY_HORIZON]
                or [PACK["board_recent_hours"]])
    first, rest = [], []
    for line in (r.get("content") or "").splitlines():
        m = _BOARD_LINE.match(line.strip())
        if not m:
            continue
        key = m["key"]
        if key in mine or key.removeprefix("g1:") in mine:
            first.append((mine.index(key) if key in mine else 0, line, key))
            continue
        when = datetime(at.year, int(m["m"]), int(m["d"]), *map(int, m["hm"].split(":")), tzinfo=timezone.utc)
        if when > at + timedelta(days=1):
            when = when.replace(year=at.year - 1)
        if (m["state"] in PACK["board_states"]) and at - when <= timedelta(hours=hours):
            rest.append((0, line, key))
    rows = [*sorted(first), *rest][:PACK["board_max_lines"]]
    lines, used = [], 0
    for _, line, _ in rows:
        t = len(line) // 4 + 1
        if used + t > BOARD_TOKENS:
            break
        lines.append(line)
        used += t
    if not lines:
        return None
    return Block("subjects_board", 1, "Sujets actifs (un par ligne) :\n" + "\n".join(lines),
                 sources=[k for _, line, k in rows if line in lines])


def continues(plan: ContextPlan) -> bool:
    """The message carries on a thread (an existing one, or an act that follows the previous turn): its working state
    and objectives are relevant. A new subject gets neither — the visible conversation is still in the history."""
    return bool(plan.thread.id) and not plan.thread.new or plan.act != "new"


def session_state(plan: ContextPlan, message: str, session_key: str | None, socle_rules: bool = False) -> Block | None:
    """Layer 2, SessionState (Memory V1 P1.1): the owner's durable rules in force (always, stable) and the working
    state of this session's thread — interpreted decisions and constraints of the thread and of its subject in other
    runtimes, the owner's words not interpreted yet verbatim, the agent's plan. Rebuilt from Memory at each message, so
    a compression or another runtime loses nothing.
    socle_rules (owner 2026-11-26): the host said it carries the owner's universal consignes in its cached instructions
    for this turn (Walter Engine's stable block): only the consignes limited to a project, domain, person or situation
    come here. Without that word from the host nothing changes, so a host that could not read the block loses none."""
    from walter_memory import context
    source, thread = None, None
    if session_key and session_key.count("/") >= 2:
        source, _, thread = session_key.split("/", 2)
        source = {"claude-code": "claude_code"}.get(source, source)
    budget = {k: 0 for k in ("profile", "people", "records", "knowledge", "evidence", "views")} | NOT_HERE | STATE_BUDGET
    if plan is not None and not continues(plan):
        # observation 2026-11-27: a new subject received the previous subject's working state (2.6 k tokens). A level
        # is a retrieval depth, not a duty to fill every block: the session's working state comes when the message
        # carries on its thread; the owner's consignes and preferences tied to the message always come
        budget["working"] = 0
    r = context.get_context(message, budget=budget, include_profile=False,
                            session=(source, thread) if source and thread else None, exclude_universal=socle_rules)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("session_state", 2, _body(r["text"]), sources=refs[:30])


MEMORY_PREAMBLE = "Contexte daté tiré de la mémoire de Walter"


def _body(text: str) -> str:
    """Memory's assembled text without its own preamble when [dedupe] memory_header: the pack's header says the same
    (data, not instructions; answer from it with its date; the most recent wins), once for the whole pack — Memory's
    preamble came once per Memory block, so twice in a pack with the working state and the memory."""
    if not DEDUPE["memory_header"] or not text.startswith(MEMORY_PREAMBLE):
        return text
    head, sep, rest = text.partition("\n\n")
    return rest if sep and rest.strip() else text


def _age(built_at, at: datetime) -> str:
    if isinstance(built_at, str):
        built_at = datetime.fromisoformat(built_at)
    if not isinstance(built_at, datetime):
        return "d'âge inconnu"
    s = (at - built_at).total_seconds()
    return f"construite il y a {round(s / 60)} min" if s < 5400 else (
        f"construite il y a {round(s / 3600)} h" if s < 172800 else f"construite il y a {round(s / 86400)} j")


def subject(plan: ContextPlan, at: datetime | None = None) -> Block | None:
    """The thread's view at the plan's depth. The plan's horizon is passed as MemoryViewQuery.max_age_s (instant /
    day); a stale view (newer exchanges than its build, or older than asked) is shown with its age and marked « peut
    être périmé », never as current: Memory has no declared rebuild-on-read, the model reads the logs if it matters."""
    depth = SUBJECT_DEPTH.get(plan.level)
    key = plan.thread.id
    if not depth or not key or not key.startswith("subject:"):
        return None
    from walter_memory import views
    ages = [PACK["horizon_max_age_s"][h] for h in plan.horizons if h in PACK["horizon_max_age_s"]]
    q = {"depth": depth, "max_tokens": PACK["subject_tokens"], **({"max_age_s": int(min(ages))} if ages else {})}
    r = views.read({**q, "key": "g1:" + key})     # V1 view, rebuilt from knowledge
    if "error" in r:
        r = views.read({**q, "key": key})
    if "error" in r:
        return None
    key = r.get("key") or key
    head = f"Sujet {key} ({r['depth']})"
    if r.get("stale"):
        head += (f", vue {_age(r.get('built_at'), at or datetime.now(timezone.utc))} : peut être périmé, des échanges "
                 "plus récents existent (logs_search, memory_view)")
    return Block(f"subject:{r['depth']}", 3, f"{head} :\n{r['content']}",
                 sources=[{"view": key, "version": r.get("version"), "stale": r.get("stale")}])


class RouteAbsent(RuntimeError):
    """The Memory gateway route does not exist (yet): the block is dropped with a note."""


def _gateway(path: str, body: dict) -> dict:
    """POST to Walter Memory's gateway (Bearer from Memory's public client), within [pack] gateway_timeout_s."""
    from walter_memory import client
    req = urllib.request.Request(GATEWAY + path, method="POST", data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + client.token()})
    try:
        with urllib.request.urlopen(req, timeout=PACK["gateway_timeout_s"]) as res:
            out = json.loads(res.read(512 * 1024))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 405):
            raise RouteAbsent(f"{path} {exc.code}") from None
        raise RuntimeError(f"{path} HTTP {exc.code}") from None
    return out if isinstance(out, dict) else {}


def _clip(text, n: int) -> str:
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


def _when(value, at: datetime) -> tuple[str, float | None]:
    try:
        t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "", None
    s = (at - t).total_seconds()
    ago = f"{round(s / 60)} min" if s < 5400 else f"{round(s / 3600)} h" if s < 172800 else f"{round(s / 86400)} j"
    return ago, s


def _outcome(o) -> str:
    if isinstance(o, dict):
        return _clip(" ".join(str(x) for x in (o.get("status"), o.get("summary") or o.get("result")) if x), 120)
    return _clip(o, 120)


def tasks(plan: ContextPlan, fetch=_gateway, at: datetime | None = None, session_key: str | None = None) -> Block | None:
    """The owner's objectives (Run Plane, SOCLE A3): those of the plan's thread, open or suspended, with progress,
    last outcome, age and id — a task is never continued without its state; then, only when the answer depends on
    the owner's tasks (plan.personal has `tasks`, 2026-11-27: a level is a depth, not a duty to fill every block), up
    to tasks_others other active objectives in one line each, of the asking session's channel only (a test session
    never sees the owner's objectives, the owner never sees a test's)."""
    at = at or datetime.now(timezone.utc)
    thread = plan.thread.id
    mine = (fetch("/v1/tasks/list", {"thread_id": thread, "limit": 5}).get("tasks") or []) if thread else []
    mine = [t for t in mine if t.get("status") in ("open", "suspended")]
    want_others = plan.level != "L0" and "tasks" in (plan.personal or [])
    others = [] if not want_others else [
        t for t in fetch("/v1/tasks/list", {"limit": 3 + PACK["tasks_others"],
                                            **({"asking_session": session_key} if session_key else {})}).get("tasks") or []
        if t.get("status") in ("open", "suspended") and t.get("task_id") not in {m.get("task_id") for m in mine}
        and (not thread or t.get("thread_id") != thread)][:PACK["tasks_others"]]
    if not mine and not others:
        return None
    lines = []
    for t in mine:
        ago, _ = _when(t.get("updated_at"), at)
        parts = [f"- [{t.get('status')}] {_clip(t.get('goal'), 160)}"]
        if t.get("progress"):
            parts.append(f"progrès : {_clip(t['progress'], 120)}")
        if t.get("last_outcome"):
            parts.append(f"dernier résultat : {_outcome(t['last_outcome'])}")
        if t.get("attempts"):
            parts.append(f"tentatives : {t['attempts']}")
        if ago:
            parts.append(f"il y a {ago}")
        if t.get("task_id"):
            parts.append(f"id {t['task_id']}")          # what task_update needs
        lines.append(" ; ".join(parts))
    text = ("Objectifs de ce fil :\n" + "\n".join(lines)) if lines else ""
    if others:
        text += ("\n" if text else "") + "Autres objectifs en cours (détail : tasks_list) : " + " ; ".join(
            f"{_clip(t.get('goal'), 80)} ({'suspendu, ' if t.get('status') == 'suspended' else ''}"
            f"{_when(t.get('updated_at'), at)[0] or '?'})" for t in others)
    text = "Tâches du propriétaire (Run Plane) :\n" + text
    if len(text) // 4 + 1 > PACK["tasks_tokens"]:
        text = text[: PACK["tasks_tokens"] * 4].rsplit("\n", 1)[0]
    return Block("tasks", 3, text, sources=[t.get("task_id") for t in [*mine, *others]])


FAILED = ("failed", "partial", "cancelled", "error")


def experience(plan: ContextPlan, message: str, fetch=_gateway, at: datetime | None = None) -> Block | None:
    """What was already tried on this thread or on the same request (SOCLE A4): failures, partial results, validated solutions, from Memory's
    execution episodes. At L2+ whenever there is one; below, only for a failed/partial attempt in the last
    experience_recent_days days (the model must not retry blindly what just failed)."""
    at = at or datetime.now(timezone.utc)
    # A new request has no thread yet (Memory attaches it after the exchange): Memory then serves, by the request
    # alone, the past attempts about the same thing — a failed operation is never retried blind from a new session.
    items = fetch("/v1/experience", {"thread_id": plan.thread.id or None, "query": message[:500],
                                     "limit": PACK["experience_items"]}).get("items") or []
    if not items:
        return None
    recent_fail = any(i.get("status") in FAILED and (_when(i.get("at"), at)[1] or 1e12)
                      <= PACK["experience_recent_days"] * 86400 for i in items)
    if plan.level in ("L0", "L1") and not recent_fail:
        return None
    lines = []
    for i in items[:PACK["experience_items"]]:
        try:
            t = i["at"] if isinstance(i.get("at"), datetime) else datetime.fromisoformat(str(i.get("at")))
            day = f"{t:%d/%m}"
        except (TypeError, ValueError, KeyError):
            day = "?"
        what = _clip(i.get("summary"), 160)
        if i.get("status") in FAILED:
            line = f"- Déjà tenté le {day} : {what} — {'échec' if i['status'] != 'partial' else 'partiel'}"
            if i.get("errors"):
                line += " : " + _clip("; ".join(map(str, i["errors"][:2])), 160)
        else:
            line = f"- Fait le {day} : {what} — {i.get('status') or 'terminé'}"
        if i.get("solutions"):
            line += ". Solution validée : " + _clip("; ".join(map(str, i["solutions"][:2])), 140)
        if i.get("lessons"):
            line += ". Leçon : " + _clip("; ".join(map(str, i["lessons"][:2])), 140)
        if i.get("pending"):
            line += ". Reste : " + _clip("; ".join(map(str, i["pending"][:2])), 120)
        lines.append(line + ".")
    text = "Expérience (tentatives passées sur ce sujet, à ne pas refaire à l'aveugle) :\n" + "\n".join(lines)
    if len(text) // 4 + 1 > PACK["experience_tokens"]:
        text = text[: PACK["experience_tokens"] * 4].rsplit("\n", 1)[0]
    return Block("experience", 4, text, sources=[i.get("run_id") for i in items])


def _gets_memory(plan: ContextPlan) -> bool:
    return _memory_budget(plan) is not None


def _memory_budget(plan: ContextPlan) -> dict | None:
    """The sections Memory's context assembly is asked for, or None when the plan gets no memory block.
    Proportionate (2026-11-27, Monsieur): the memory a message needs no longer comes with its subject's history —
    L3/L4 plans read their level's sections; « memory needed » reads the L3 sections at any level, L0 included,
    without the threads; a personal domain at L1/L2 as before; a taste of the owner alone (personal « preferences »)
    gets a targeted lookup, `[pack.memory_budget.targeted]`. A chronological question (`chronological`, 27/11) reads
    only the owner's latest exchanges, in order: `[pack.memory_budget.chronological]`, whatever the level."""
    if chronological(plan) and "chronological" in MEMORY_BUDGET:
        return {**MEMORY_BUDGET["chronological"], **NOT_HERE}
    if plan.level in MEMORY_BUDGET and plan.level.startswith("L"):
        return {**MEMORY_BUDGET[plan.level], **NOT_HERE}
    if "memory" in plan.capabilities or (plan.level != "L0" and set(plan.domains) - NO_MEMORY_DOMAINS):
        return {**MEMORY_BUDGET["L3"], **NOT_HERE}
    if "preferences" in (plan.personal or []) and "targeted" in MEMORY_BUDGET:
        return {**MEMORY_BUDGET["targeted"], **NOT_HERE}
    return None


RECORDS_HEAD = "## Décisions et règles consignées"


def _memory_block(message: str, budget: dict, *, recent_hours: float | None = None,
                  before_rerank=None) -> list[Block] | None:
    """Memory's assembly for the message, as blocks: the curated records it matched (decisions register, consignes
    written in the records) become the `records` block, cut first over the budget like the records block itself, and
    the rest stays `memory`. Until 27/11 they were one block: at L0 the records (600 tokens, partly unrelated: a
    2026-10-04 Router rule matched on « message reçu ») came first in it, so the budget dropped the memory tool card
    and the relevant memory instead of them."""
    from walter_memory import context
    kw = {"recent_hours": recent_hours} if recent_hours else {}
    if before_rerank is not None:
        kw["before_rerank"] = before_rerank
    r = context.get_context(message, budget=budget, include_profile=False, **kw)
    if not r.get("text"):
        return None
    secs = (r.get("trace") or {}).get("sections", {})
    body = _body(r["text"])
    head, sep, rest = ("\n\n" + body).partition("\n\n" + RECORDS_HEAD)
    blocks = []
    if sep:
        mine, more, after = rest.partition("\n\n## ")
        blocks.append(Block("records", 4, (RECORDS_HEAD + mine).strip(),
                            sources=list((secs.get("records") or {}).get("refs") or [])[:20]))
        body = (head + (more + after if more else "")).strip()
    refs = [ref for k, s in secs.items() if k != "records" for ref in (s.get("refs") or [])]
    if body.strip():
        blocks.insert(0, Block("memory", 4, body, sources=refs[:20]))
    return blocks or None


def chronological(plan: ContextPlan) -> float | None:
    """Hours of the owner's latest exchanges to read in order, when the plan's question is about what just happened
    in his life (personal « history » on an instant/day horizon) and names no day and no person — those are read by
    the period synthesis and the people's cards. None: no chronological reading. Owner 2026-11-27: a request about
    recent events is met by a structured, deterministic read (no semantic search, no rerank); the model stays free
    to read more with memory_events."""
    hours = PACK.get("chronological_hours") or {}
    horizons = set(plan.horizons or [])
    obs = plan.observations or {}
    if plan.level not in (PACK.get("chronological_levels") or ()):
        return None                 # a heavier plan needs its whole memory (24/1 744 plans 24–27/11, 21 of them L3)
    if "history" not in (plan.personal or []) or not horizons or not horizons <= set(hours):
        return None
    if obs.get("dates") or obs.get("people"):
        return None
    return float(max(hours[h] for h in horizons))


def memory(plan: ContextPlan, message: str) -> list[Block] | None:
    budget = _memory_budget(plan)
    return _memory_block(message, budget, recent_hours=chronological(plan)) if budget is not None else None


def records(plan: ContextPlan, message: str) -> Block | None:
    """The curated records (decisions register, owner rules) matching the message, when the plan gets no memory block
    but says the answer must be looked up, or is unsure of itself. Calibration 2026-10-28 (DSH trials): questions on
    Walter's own setup or the owner's decisions were planned L0 « tools suffice » with low confidence, and a model
    without tools then had nothing to answer from. ContextPlan v2 (07/11): only a *memory* lookup asks for them; an
    unsure plan that needs the web and not the owner's memory (« prix du Bitcoin ») gets none."""
    conf = ((plan.decision or {}).get("confidence") or {}).get("plan")
    caps = set(plan.capabilities)
    unsure = conf is not None and conf < UNSURE_PLAN and not caps & {"web", "browser"} and len(_words(message)) >= 2
    if "memory" not in caps and not unsure:       # a lone word (« test ») names nothing to look up
        return None
    from walter_memory import context
    r = context.get_context(message, budget={**RECORDS_BUDGET, **NOT_HERE}, include_profile=False)
    if not r.get("text"):
        return None
    return Block("records", 4, r["text"], sources=(r.get("trace") or {}).get("sections", {}).get("records", {}).get("refs", []))


def recent(session_key: str | None, native: bool) -> Block | None:
    """The last exchanges of the channel (the safety net measured 21/10). A host with native history already shows
    them: counted, not injected."""
    if not session_key:
        return None
    from walter_memory import logs
    from walter_memory.db import connection
    with connection() as conn:
        rows = logs.search(conn, "", session=session_key, types=["user/message", "assistant/message"], limit=12,
                           max_privacy="cloud_allowed")
    rows = rows if isinstance(rows, list) else rows.get("results", [])
    lines = [f"{'Owner' if r.get('type') == 'user/message' else 'Assistant'} : {(r.get('text') or r.get('snippet') or '')[:600]}"
             for r in reversed(rows[: RECENT_EXCHANGES * 2])]
    return Block("recent_exchanges", 5, "\n".join(lines), injected=not native, sources=[session_key]) if lines else None


_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre")


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"


def _days_span(a: str, b: str | None = None) -> str:
    return _day(a) if not b or b == a else f"du {_day(a)} au {_day(b)}"


_DURATION_UNITS = {"D": ("jour", "jours"), "W": ("semaine", "semaines"), "M": ("mois", "mois")}


def _duration(iso: str) -> str:
    m = re.match(r"^P(\d+)([DWM])$", iso or "")
    if not m:
        return iso
    n = int(m.group(1))
    return f"{n} {_DURATION_UNITS[m.group(2)][n > 1]}"


def dates_line(plan: ContextPlan | None) -> str:
    """The days the message names, read by Walter (preflight observation `dates`, Walter Decision 2.0): « jeudi »
    is said as a calendar day, a period as its first and last days (18/11), a length of time as a length; when the
    words leave a choice (the coming or the past Thursday or weekend, a weekday that does not match the date) the
    line says both readings rather than one guess, and a period with no exact bounds says so."""
    out = []
    for d in ((plan.observations or {}).get("dates") or []) if plan else []:
        if d.get("duration") and not d.get("date"):
            out.append(f"« {d['text']} » = une durée de {_duration(d['duration'])}, pas une date")
            continue
        if not d.get("date"):
            continue
        text = f"« {d['text']} » = {_days_span(d['date'], d.get('end'))}" + (f" à {d['time']}" if d.get("time") else "")
        if d.get("approx"):
            text += " (bornes approximatives)"
        if d.get("past"):
            text += f" (ou {_days_span(d['past'], d.get('past_end'))} si c'est le passé)"
        elif d.get("ambiguous"):
            text += " (à confirmer : les mots laissent un choix)"
        out.append(text)
    return ("Dates du message : " + " ; ".join(out) + ".") if out else ""


def now(at: "datetime | None" = None, plan: ContextPlan | None = None) -> Block:
    """The present instant in the owner's time zone (Walter Memory's setting, the owner's places). No host told the
    model the date: on 07/11 it ran `date` in a shell (one more step) and guessed « heure de Paris » in its answers.
    With a plan, the days its message names, as calendar days (dates_line)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        from walter_memory import organic
        tz = str(organic.settings().get("periods", {}).get("tz") or "UTC")
        zone = ZoneInfo(tz)
    except Exception:  # noqa: BLE001 — Memory unreachable: UTC is still the truth
        tz, zone = "UTC", timezone.utc
    utc = at or datetime.now(timezone.utc)
    local = utc.astimezone(zone)
    text = (f"Maintenant : {_DAYS[local.weekday()]} {local.day} {_MONTHS[local.month - 1]} {local.year}, "
            f"{local:%H:%M} heure locale ({tz}) ; {utc:%Y-%m-%d %H:%M} UTC.")
    extra = dates_line(plan)
    return Block("now", 5, text + ("\n" + extra if extra else ""),
                 sources=[f"tz:{tz}", *(["preflight:dates"] if extra else [])])


def people(plan: ContextPlan, message: str) -> Block | None:
    """The people the message names (preflight observation `people`, Walter Decision 2.0) matched to the people the
    owner talks with, their Kardex card (cloud-safe; Walter Memory resolves and reads, never this module). Those the
    memory block already shows by its own name match are left to it: a person is shown once."""
    names = [p["text"] for p in ((plan.observations or {}).get("people") or []) if p.get("text")]
    if not names:
        return None
    from walter_memory import context
    budget = _memory_budget(plan)
    shown = context.people_in(message) if budget and budget.get("people", 0) > 0 else []
    r = context.people_cards(names, exclude=shown, budget=PACK["people_tokens"])
    if not r.get("text"):
        return None
    return Block("people", 4, "Personnes nommées dans le message (Kardex) :\n" + r["text"],
                 sources=[f"entity:{e}" for e in r.get("matched") or []])


def _ago(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} h {m:02d}" if m else f"{h} h"
    return f"{h // 24} j {h % 24} h"


def position(plan: ContextPlan, at: "datetime | None" = None, read=None) -> Block | None:
    """Where the owner is (v4, 18/11): asked when the plan says the answer depends on it (`personal` has location —
    « une pizza autour de moi », « il fait quel temps ici »), at every level. Walter Memory's last position sample,
    its time and age, whether it is recent, the known place it falls in and the known home — said as they are: an old
    position is said old (the owner may have moved), an absent one is said absent, never guessed. Memory decides
    what a cloud reader may read (walter_memory.whereabouts)."""
    if "location" not in (plan.personal or []):
        return None
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    if read is None:
        from walter_memory import whereabouts
        read = whereabouts.current
    w = read()
    st = w.get("status")
    if st == "withheld":
        return Block("position", 5, "Position du propriétaire : non lisible par ce modèle (classe de confidentialité).",
                     sources=["memory:whereabouts"])
    home = w.get("home")
    home_line = (f"Domicile connu : « {home['name']} » (≈ {home['lat']}, {home['lng']})"
                 + (f", à {home['distance_m'] / 1000:.1f} km de cette position" if home.get("distance_m") else "")
                 + ".") if home else "Domicile : inconnu de la mémoire."
    if st == "absent":
        text = "Position du propriétaire : aucun relevé GPS en mémoire. " + home_line
    else:
        try:
            from walter_memory import organic
            zone = ZoneInfo(str(organic.settings().get("periods", {}).get("tz") or "UTC"))
        except Exception:  # noqa: BLE001
            zone = timezone.utc
        when = datetime.fromisoformat(w["at"]).astimezone(zone)
        fresh = "récente" if st == "recent" else "ancienne : il a pu bouger depuis"
        place = w.get("place")
        where = (" — au domicile connu" if place and place.get("home") else
                 f" — au lieu connu « {place['name']} »" if place else "")
        text = (f"Position du propriétaire (GPS, Walter Memory) : dernier relevé le {when:%Y-%m-%d à %H:%M} heure locale, "
                f"il y a {_ago(w['age_s'])} ({fresh}){where} ; ≈ {w['lat']}, {w['lng']}"
                + (f" (précision {w['accuracy_m']} m)" if w.get("accuracy_m") is not None else "") + ".\n" + home_line)
        if st != "recent":
            text += ("\nSi la réponse dépend de l'endroit exact, partir de cette position en disant son âge, ou "
                     "demander confirmation en une phrase.")
    return Block("position", 5, text, sources=["memory:whereabouts"])


LATE = "not ready in time"                      # note of a source the pack did not wait for
_WORKERS: list = []


def _workers():
    """Shared worker threads of the pack's sources (each one is I/O: Memory's database, its gateway, a command)."""
    from .threads import Executor as ThreadPoolExecutor
    if not _WORKERS:
        _WORKERS.append(ThreadPoolExecutor(max_workers=PACK["workers"], thread_name_prefix="pack-source"))
    return _WORKERS[0]


def _timed(step):
    t0 = time.perf_counter()
    b = step()
    for x in (b if isinstance(b, list) else [b]):
        if x is not None:
            x.ms = round((time.perf_counter() - t0) * 1000, 1)
    return b


class Prefetch:
    """The sources that need the message but not the plan, started as the message arrives (2026-11-16). Before this,
    they waited for the plan's decision (median 0.8 s) and then took up to 1.3 s more: Memory's rerank call, the
    thread's working state, the module notes. Started early, they run during the decision.
    Memory is started at the budget most plans ask for: L3, and L1/L2 with a personal domain (about 60 % of the
    14–16/11 records). gather() takes a result only when the plan asks for exactly these inputs, so the same
    functions get the same arguments: the pack is the same, only ready sooner. A result the plan does not ask for is
    dropped, never shown.
    The local candidate searches run during the decision; the rerank call over their union (about 190 passages,
    24 000 tokens) waits for the plan and runs only when the plan takes this memory (27/11: it ran for every message,
    an L0 chronological question included, and was thrown away). Past `prefetch_gate_s` without a plan it is not
    made, and the plan then asks its memory itself."""

    def __init__(self, message: str, session_key: str | None, socle_rules: bool = False):
        w = _workers()
        self.message, self.session_key, self.socle_rules = message, session_key, socle_rules
        self.memory_budget = {**MEMORY_BUDGET["L3"], **NOT_HERE}
        self._go, self._lock, self._wanted, self._skipped = threading.Event(), threading.Lock(), False, False
        w.submit(_notes)                         # warms the shared notes; their blocks read the cache
        self.state = w.submit(_timed, lambda: session_state(None, message, session_key, socle_rules))
        self.memory = w.submit(_timed, lambda: _memory_block(message, self.memory_budget, before_rerank=self._gate))

    def _gate(self) -> bool:
        """Memory asks before its rerank call: wait for the plan; rerank only if the plan takes this memory."""
        self._go.wait(PACK.get("prefetch_gate_s", 8))
        with self._lock:
            if not self._go.is_set():
                self._skipped = True
            return self._wanted and not self._skipped

    def taken(self, plan: ContextPlan, message: str, session_key: str | None) -> dict:
        """name → future, for the sources this plan asks for with exactly the prefetched inputs."""
        same = message == self.message and session_key == self.session_key
        with self._lock:
            self._wanted = same and not self._skipped and _memory_budget(plan) == self.memory_budget
            self._go.set()
        if not same:
            return {}
        out = {"session_state": self.state} if plan.level != "L0" and continues(plan) else {}
        if self._wanted:
            out["memory"] = self.memory
        return out

    def release(self) -> None:
        """No plan will take anything (the caller gives up): the rerank is not made."""
        with self._lock:
            self._go.set()


def gather(plan: ContextPlan, message: str, *, session_key: str | None = None, native_history: bool = True,
           deadline: float | None = None, prefetch: Prefetch | None = None,
           socle_rules: bool = False) -> tuple[list[Block], list[str]]:
    """The blocks the plan asks for. L0: capabilities (+ records when unsure or a lookup is needed), and — at every
    level, two short Memory calls — the objectives of the plan's thread and a recent failed attempt at the same thing
    (SOCLE A3/A4: a light request is exactly the one that would otherwise be retried blind). Returns (blocks, notes
    on failed sources), in the order of the steps.
    The sources are asked together: the pack costs its slowest source, not their sum (13/11: plan 2 s + session state
    1 s + memory 3 s one after the other passed the engine's 7 s and the whole plan was lost). `deadline`
    (time.monotonic) is when the caller must answer: a source not ready by then gives no block and the note
    « <source>: not ready in time », which the pack says to the model — late context is said, never silent.
    `prefetch`: sources already started with this message (Prefetch); a block's `ms` is then its own time since that
    start, and `retrieval_ms` alone says what the pack added after the plan."""
    pending = getattr(plan, "_readings", None)      # readings asked apart from the judgements, still running

    def settled(fn):
        """A block that reads the message's dates or people waits for the readings, at most `readings_wait_s` after
        the message — never past the answer's deadline less the grace the pack gives its sources, so `now` itself is
        never lost to them."""
        if pending is None:
            return fn

        def step():
            # counted from the message, not from this step (17/11 bench: a 2 s wait from here put 2 slow readings
            # of OpenRouter's Extractions route, 1.8–3.6 s, on the answer's total)
            left = PACK["readings_wait_s"] - (time.perf_counter() - pending.t0)
            if deadline is not None:
                left = min(deadline - time.monotonic() - PACK["late_grace_s"], left)
            pending.settle(plan, left)
            return fn()
        return step
    steps = [("capabilities", lambda: capabilities(plan)), ("tool_cards", lambda: tool_cards(plan)),
             ("now", settled(lambda: now(plan=plan)))]
    if pending is not None or (plan.observations or {}).get("people"):
        steps.append(("people", settled(lambda: people(plan, message))))
    if "location" in (plan.personal or []):
        steps.append(("position", lambda: position(plan)))
    if plan.level != "L0":
        steps += [("board", lambda: board(plan)), ("session_state", lambda: session_state(plan, message, session_key, socle_rules)),
                  ("subject", lambda: subject(plan))]
    steps += [("tasks", lambda: tasks(plan, session_key=session_key)), ("experience", lambda: experience(plan, message))]
    if _gets_memory(plan):
        steps.append(("memory", lambda: memory(plan, message)))
    if plan.level != "L0":
        steps.append(("recent", lambda: recent(session_key, native_history)))
    if not _gets_memory(plan):
        steps.append(("records", lambda: records(plan, message)))

    early = prefetch.taken(plan, message, session_key) if prefetch is not None else {}
    if prefetch is not None:                    # an early source this plan does not ask for: not started, never will
        for f in (prefetch.state, prefetch.memory):
            if f not in early.values():
                f.cancel()
    futures = [(name, early.get(name) or _workers().submit(_timed, step)) for name, step in steps]
    blocks, notes = [], []
    for name, f in futures:
        if deadline is not None:
            wait([f], timeout=max(deadline - time.monotonic(), PACK["late_grace_s"]))
            if not f.done():                        # (a source's own TimeoutError is a failure, not a late source)
                f.cancel()                          # not started yet: never will; started: its result is dropped
                notes.append(f"{name}: {LATE}")
                continue
        try:
            b = f.result()
        except Exception as exc:  # noqa: BLE001 — one source failing never drops the others
            reason = "route absent" if isinstance(exc, RouteAbsent) else f"{type(exc).__name__}: {str(exc)[:120]}"
            notes.append(f"{name}: {reason}")
            continue
        if isinstance(b, list):
            blocks += [x for x in b if x is not None]
        elif b is not None:
            blocks.append(b)
    return blocks, notes
