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
import time
import urllib.error
import urllib.request
from concurrent.futures import wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .config import pack_settings
from .plan import ContextPlan
from .preflight import _words

# capability → module whose brief (M1) the model gets in full; every module's one line (M0) is always there
CAPABILITY_MODULES = {"skills": ["skills"], "memory": ["memory"], "web": ["browse"], "browser": ["browse", "computer"],
                      "delegation": ["router"], "secrets": ["secrets"]}
DOMAIN_MODULES = {"relations": ["memory"], "agenda": ["memory"], "profile": ["memory"], "activities": ["memory"],
                  "decisions": ["memory"], "goals": ["memory"]}
SUBJECT_DEPTH = {"L0": None, "L1": "index", "L2": "overview", "L3": "synthesis", "L4": "synthesis"}
PACK = pack_settings()
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


_CAP_CACHE: dict[tuple, tuple[float, str, list]] = {}


def capabilities(plan: ContextPlan, ttl: float = 600) -> Block | None:
    """M0 of every module + M1 of the modules the plan needs (session layer: changes rarely, cached)."""
    m1 = sorted({m for c in plan.capabilities for m in CAPABILITY_MODULES.get(c, [])} |
                {m for d in plan.domains for m in DOMAIN_MODULES.get(d, [])})
    key = tuple(m1)
    hit = _CAP_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return Block("capabilities", 0, hit[1], sources=hit[2])
    args = ["walter", "present", "notes", "--form", "m0"] + (["--m1", ",".join(m1)] if m1 else [])
    out = json.loads(subprocess.run(args, capture_output=True, text=True, timeout=20).stdout)
    notes = out.get("notes") or []
    text = "\n\n".join(n["content"].strip() for n in notes if n.get("content"))
    ids = [n.get("id") for n in notes]
    _CAP_CACHE[key] = (time.time(), text, ids)
    return Block("capabilities", 0, text, sources=ids)


# capability → modules whose agent brief (M1) is shown *for this message* (tool cards, layer 4): the host lists only a
# core toolset and every module's one line (M0), so the plan says which modules' tools fit the request (07/11: a web
# question answered with `curl` from the VM because nothing pointed at walter_browse). Delegation has none: the engine
# delegates through its own `subagent` tool; which modules' guide helps a message is question set 3's D question (P4).
TOOL_CARD_MODULES = {"web": ["browse"], "browser": ["browse", "computer"], "secrets": ["secrets"],
                     "memory": ["memory"], "skills": ["skills"]}
_CARD_CACHE: dict[str, tuple[float, str]] = {}


def _card(module: str, ttl: float = 600) -> str:
    hit = _CARD_CACHE.get(module)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    out = json.loads(subprocess.run(["walter", "present", "notes", "--form", "m0", "--m1", module],
                                    capture_output=True, text=True, timeout=20).stdout)
    text = "\n\n".join(n["content"].strip() for n in out.get("notes") or []
                        if n.get("module") == module and str(n.get("id", "")).endswith(".manifest") and n.get("content"))
    _CARD_CACHE[module] = (time.time(), text)
    return text


def tool_cards(plan: ContextPlan) -> Block | None:
    """The briefs of the modules the plan's capabilities need, in the volatile layer (the cached prefix stays the same)."""
    mods = list(dict.fromkeys(m for c in plan.capabilities for m in TOOL_CARD_MODULES.get(c, [])))
    texts = [(m, _card(m)) for m in mods]
    texts = [(m, t) for m, t in texts if t]
    if not texts:
        return None
    return Block("tool_cards", 4, "Outils W.Alter pour cette demande :\n\n" + "\n\n".join(t for _, t in texts),
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


def session_state(plan: ContextPlan, message: str, session_key: str | None) -> Block | None:
    """Layer 2, SessionState (Memory V1 P1.1): the owner's durable rules in force (always, stable) and the working
    state of this session's thread — interpreted decisions and constraints of the thread and of its subject in other
    runtimes, the owner's words not interpreted yet verbatim, the agent's plan. Rebuilt from Memory at each message, so
    a compression or another runtime loses nothing."""
    from walter_memory import context
    source, thread = None, None
    if session_key and session_key.count("/") >= 2:
        source, _, thread = session_key.split("/", 2)
        source = {"claude-code": "claude_code"}.get(source, source)
    budget = {k: 0 for k in ("profile", "people", "records", "knowledge", "evidence", "views")} | NOT_HERE | STATE_BUDGET
    r = context.get_context(message, budget=budget, include_profile=False,
                            session=(source, thread) if source and thread else None)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("session_state", 2, r["text"], sources=refs[:30])


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


def tasks(plan: ContextPlan, fetch=_gateway, at: datetime | None = None) -> Block | None:
    """The owner's objectives (Run Plane, SOCLE A3): those of the plan's thread, open or suspended, with progress,
    last outcome, age and id; then up to tasks_others other active objectives (open or suspended) in one line each.
    At L0 (the lightest context) only the thread's own objectives: a task is never continued without its state."""
    at = at or datetime.now(timezone.utc)
    thread = plan.thread.id
    mine = (fetch("/v1/tasks/list", {"thread_id": thread, "limit": 5}).get("tasks") or []) if thread else []
    mine = [t for t in mine if t.get("status") in ("open", "suspended")]
    others = [] if plan.level == "L0" else [
        t for t in fetch("/v1/tasks/list", {"limit": 3 + PACK["tasks_others"]}).get("tasks") or []
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
    return plan.level != "L0" and bool(MEMORY_BUDGET.get(plan.level) or (set(plan.domains) - {"projects"}))


def memory(plan: ContextPlan, message: str) -> Block | None:
    budget = MEMORY_BUDGET.get(plan.level)
    if not _gets_memory(plan):
        return None
    from walter_memory import context
    r = context.get_context(message, budget={**(budget or MEMORY_BUDGET["L3"]), **NOT_HERE}, include_profile=False)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("memory", 4, r["text"], sources=refs[:20])


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


def now(at: "datetime | None" = None) -> Block:
    """The present instant in the owner's time zone (Walter Memory's setting, the owner's places). No host told the
    model the date: on 07/11 it ran `date` in a shell (one more step) and guessed « heure de Paris » in its answers."""
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
    return Block("now", 5, text, sources=[f"tz:{tz}"])


LATE = "not ready in time"                      # note of a source the pack did not wait for
_WORKERS: list = []


def _workers():
    """Shared worker threads of the pack's sources (each one is I/O: Memory's database, its gateway, a command)."""
    from concurrent.futures import ThreadPoolExecutor
    if not _WORKERS:
        _WORKERS.append(ThreadPoolExecutor(max_workers=PACK["workers"], thread_name_prefix="pack-source"))
    return _WORKERS[0]


def gather(plan: ContextPlan, message: str, *, session_key: str | None = None, native_history: bool = True,
           deadline: float | None = None) -> tuple[list[Block], list[str]]:
    """The blocks the plan asks for. L0: capabilities (+ records when unsure or a lookup is needed), and — at every
    level, two short Memory calls — the objectives of the plan's thread and a recent failed attempt at the same thing
    (SOCLE A3/A4: a light request is exactly the one that would otherwise be retried blind). Returns (blocks, notes
    on failed sources), in the order of the steps.
    The sources are asked together: the pack costs its slowest source, not their sum (13/11: plan 2 s + session state
    1 s + memory 3 s one after the other passed the engine's 7 s and the whole plan was lost). `deadline`
    (time.monotonic) is when the caller must answer: a source not ready by then gives no block and the note
    « <source>: not ready in time », which the pack says to the model — late context is said, never silent."""
    steps = [("capabilities", lambda: capabilities(plan)), ("tool_cards", lambda: tool_cards(plan)), ("now", now)]
    if plan.level != "L0":
        steps += [("board", lambda: board(plan)), ("session_state", lambda: session_state(plan, message, session_key)),
                  ("subject", lambda: subject(plan))]
    steps += [("tasks", lambda: tasks(plan)), ("experience", lambda: experience(plan, message))]
    if plan.level != "L0":
        steps += [("memory", lambda: memory(plan, message)), ("recent", lambda: recent(session_key, native_history))]
    if not _gets_memory(plan):
        steps.append(("records", lambda: records(plan, message)))

    def timed(step):
        t0 = time.perf_counter()
        b = step()
        if b is not None:
            b.ms = round((time.perf_counter() - t0) * 1000, 1)
        return b

    futures = [(name, _workers().submit(timed, step)) for name, step in steps]
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
        if b is not None:
            blocks.append(b)
    return blocks, notes
