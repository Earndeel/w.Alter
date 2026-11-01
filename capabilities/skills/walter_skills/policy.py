"""The exposure policy — the ONLY place that decides what an agent sees. Adapters (hooks, plugins) hold no rules.

The agent's own model always decides what to open; the policy only chooses what to show, in three tiers:
  tier 0  session start: compact purpose + domain overview + navigation tools
  tier 1  on demand: domain index entries (purposes and workflow components), no per-message shortlist by default
  tier 2  on demand: intent search / selected procedure and references (the agent's initiative)
Legacy discovery=shortlist retains adaptive cards for comparison/rollback.
After a failed command: only skills whose card lists that symptom (lexical evidence, not a guess).
Every exposure is journaled (skills.retrievals) — the learning loop reads it back as implicit feedback.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import config, domains, history, registry
from .retrieval import engine

MACHINE = ("<task-notification", "[SYSTEM NOTIFICATION", "Another Claude session sent a message", "[Subagent hand-back]",
           "<system-reminder", "[ASYNC DELEGATION", "[CONTEXT COMPACTION", "[System:", "[SYSTEM:")
GENERIC_ERROR_WORDS = set("""traceback most recent call last error errors failed failure fatal exception module named no
not found file line lines command denied permission connection refused timeout timed out http status code returned
returns return unable cannot could while during python bash usr lib site packages py sh none null undefined invalid
warning warn info debug stderr stdout exit modulenotfounderror importerror keyerror valueerror typeerror
attributeerror syntaxerror nameerror runtimeerror oserror filenotfounderror permissionerror connectionerror
indexerror assertionerror jsondecodeerror unicodedecodeerror import""".split())
ERROR_MARKERS = ("Traceback (most recent call last)", "Error:", "ERROR", "error:", "FAILED", "Permission denied",
                 "No such file or directory", "command not found", "Connection refused", "fatal:", "HTTP 4", "HTTP 5",
                 "[exit code:", "Exit code ", "Failed to", "failed to", "Exception")  # the hooks only send failed commands


@dataclass
class Exposure:
    text: str = ""
    shown: list[str] = field(default_factory=list)
    mode: str = "none"
    reason: str = ""
    latency_ms: int = 0
    results: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"text": self.text, "shown": self.shown, "mode": self.mode, "reason": self.reason,
                "latency_ms": self.latency_ms, "results": self.results}


def _safe(fn, default):
    """Session state and the map come from the registry; if it is unreachable, expose without them (degraded)."""
    try:
        return fn()
    except Exception:
        return default


def _tools(runtime: str) -> tuple[str, str]:
    """Names of the read/search tools in this runtime (the only runtime-specific detail)."""
    return ("walter_skill_read", "walter_skill_search") if runtime.startswith("hermes") else ("skill_read", "skills_search")


def _cards_text(rows: list[dict], read_tool: str) -> str:
    lines = []
    for r in rows:
        line = f"- {r['name']} — {r['summary'][:160]}"
        if r.get("requires"):
            line += f" (workflow : {' → '.join(r['requires'])})"
        lines.append(line)
    return ("Skills W.Alter candidats pour ce message (procédures testées sur cette VM, classées par pertinence probable). "
            f"Si l'un correspond à la tâche, lis-le avec {read_tool} avant d'agir ; sinon ignore cette liste :\n"
            + "\n".join(lines))


def expose(kind: str, message: str, *, context: str = "", session_id: str | None = None, runtime: str = "agent",
           first_turn: bool = False) -> Exposure:
    t0 = time.perf_counter()
    p = config.get("policy")
    read_tool, search_tool = _tools(runtime)
    msg = (message or "").strip()
    out = Exposure()

    layered = runtime in p.get("layer_runtimes", [])  # the module layer already shows the map
    if kind == "session_start":
        if p["domain_map"] and not layered:
            out.text, out.mode = _safe(lambda: domains.render(search_tool), ""), "map"
            out.shown = []
        return _done(out, t0, runtime, session_id, msg, journal=False)

    if not msg or any(m in msg[:400] for m in MACHINE):
        out.reason = "machine prompt"
        return _done(out, t0, runtime, session_id, msg, journal=False)

    if kind == "message" and p.get("discovery", "shortlist") == "on_demand":
        out.reason = "on-demand discovery"
        if first_turn and p["domain_map"] and not layered:
            out.text, out.mode = _safe(lambda: domains.render(search_tool), ""), "map"
        return _done(out, t0, runtime, session_id, msg, journal=False)

    e = engine()
    if kind == "error":
        if not any(m in msg for m in ERROR_MARKERS):
            out.reason = "no error marker"
            return _done(out, t0, runtime, session_id, msg, journal=False)
        seen, _ = _safe(lambda: registry.recently_shown(session_id, 50), (set(), 0))
        from .ranker import tokens
        # only the error's own words: the command line names tools and paths, not the symptom
        specific = " ".join(w for w in tokens(msg[-1500:]) if w not in GENERIC_ERROR_WORDS and not w.isdigit())
        hits = [(n, s) for n, s in e.symptom_matches(specific) if s >= p["error_min_symptom"] and n not in seen]
        rows = [e.row(n, s, "active") for n, s in hits[:p["error_max"]]]
        if rows:
            out.text = ("La commande a échoué. Skills W.Alter dont la fiche décrit ce symptôme (lis-le avec "
                        f"{read_tool} si pertinent) :\n" + "\n".join(f"- {r['name']} — {r['summary'][:160]}" for r in rows))
            out.shown, out.mode, out.results = [r["name"] for r in rows], "error", rows
        else:
            out.reason = "no symptom match"
        return _done(out, t0, runtime, session_id, msg)

    # kind == "message"
    if len(msg.split()) < p["min_words"] or msg.startswith("/"):
        out.reason = "too short"
        return _done(out, t0, runtime, session_id, msg, journal=False)
    session = _safe(lambda: history.session_history(session_id, e.aliases), {}) if session_id else {}
    rows = e.rank(msg, context, session, k=p["k_max"])
    out.results = rows
    seen, n_prev = _safe(lambda: registry.recently_shown(session_id, p["recent_injections"]), (set(), 0))
    ranked = [r["name"] for r in rows]

    # workflows first; they replace the sub-skills they orchestrate
    wf = [r for r in rows if r.get("kind") == "workflow"]
    covered = {s for r in wf for s in r.get("requires", [])}
    ordered = wf + [r for r in rows if r.get("kind") != "workflow" and r["name"] not in covered]

    # confidence → fewer cards
    threshold = e.calibration.get("confident_p1", p["confident_p1"]) if "confident_p1" in e.calibration else p["confident_p1"]
    confident = threshold is not None and bool(rows) and rows[0]["score"] >= threshold
    k = p["k_confident"] if confident else p["k_max"]

    fresh = [r for r in ordered if r["name"] not in seen and session.get(r["name"], 99) > 1]
    if n_prev:  # ongoing session
        if len(msg.split()) < p["followup_words"]:
            out.reason = "follow-up: the ongoing task's skills were already proposed"
            fresh = []
        else:
            fresh = [r for r in fresh if ranked.index(r["name"]) < p["refresh_depth"]]
    shown = fresh[:k]
    if shown:
        out.text = _cards_text(shown, read_tool)
        out.shown, out.mode = [r["name"] for r in shown], "inject"
        out.reason = "confident" if confident else "ambiguous"
    if first_turn and p["domain_map"] and not layered:
        tier0 = _safe(lambda: domains.render(search_tool), "")
        if tier0:
            out.text = tier0 + ("\n\n" + out.text if out.text else "")
            out.mode = "map+inject" if shown else "map"
    return _done(out, t0, runtime, session_id, msg)


def _done(out: Exposure, t0: float, runtime: str, session_id: str | None, msg: str, journal: bool = True) -> Exposure:
    out.latency_ms = round(1000 * (time.perf_counter() - t0))
    if journal:
        try:
            registry.journal_retrieval(runtime, session_id, "inject" if out.mode.endswith("inject") else out.mode,
                                       msg, out.results, out.shown, out.latency_ms, engine().version)
        except Exception:
            pass  # journaling never blocks an exposure
    return out


def search(query: str, context: str = "", k: int = 8, include_archived: bool = False, runtime: str = "agent",
           session_id: str | None = None) -> list[dict]:
    """Tier 2 — the agent's own search."""
    t0 = time.perf_counter()
    e = engine()
    rows = e.rank(query, context, k=k) + (e.rank_archived(query) if include_archived else [])
    try:
        registry.journal_retrieval(runtime, session_id, "search", query, rows, [], round(1000 * (time.perf_counter() - t0)),
                                   e.version)
    except Exception:
        pass
    return rows
