#!/usr/bin/env python3
"""walter-core — the W.Alter harness as one stable MCP surface.

Any MCP client (Walter Engine, Claude Code, Claude Desktop, Cursor, Codex...) gets the same
capabilities:

  memory_recall / memory_retain / memory_reflect  → Walter Memory canonical facade (privacy + Router synthesis)
  walter_profile                                  → USER.md / SOUL.md / MEMORY.md
  skills_search / skill_read                      → W.Alter skills (walter-skills service :8891)
  memory_search / memory_events                   → unified search (knowledge + evidence) / canonical event history
  person_lookup                                   → Kardex social card (relationship metrics, accounts, groups)
  memory_context                                  → budgeted context block for a request (P6 context engine)
  vault_search / vault_get / vault_put            → Raw Vault: every non-text raw file (Google Drive + PG catalog)
  browser_session / browser_sites                 → Camoufox session logged in as Monsieur (his Brave cookies,
                                                    injected server-side; agents never see a cookie value)
  walter_health                                   → status of the stack services

Each tool talks to a module's public interface (HTTP API, CLI, client) or a file, never to a runtime's internals.

Transport: stdio by default (local clients). `--http` serves streamable HTTP on 127.0.0.1 for a
reverse proxy that adds authentication (never expose it bare).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import Context, FastMCP

CLIENT_TAG = os.environ.get("WALTER_CLIENT_TAG", "claude")
# Machine services Walter relies on without owning them; module services come from the registry.
HOST_UNITS = ["cloudflared-tunnel", "docker"]


def _stack_units() -> list[str]:
    try:
        from walter_platform.registry import load
        units = sorted({u for m in load()["modules"] for u in m.get("services", [])})
    except Exception:  # registry unreadable: still report the host
        units = []
    return units + HOST_UNITS
# Walter Memory (events, Raw Vault objects) runs in its own venv; called as a CLI so this server stays light.
WALTER_MEMORY = ["/usr/local/bin/walter-memory"]
BUDGETS = {"low", "mid", "high"}


from walter_capabilities import router_brief  # noqa: E402 — the router's own brief joins the server instructions

def _owner_line() -> str:
    """How the instance's owner is addressed, from the instance (lot 3a, 2026-11-24: never hardcoded in software)."""
    try:
        from walter_platform import instance
        o = instance.owner()
        return f"The user is addressed as '{o['address']}' and works in {o['language_name']}. "
    except Exception:  # noqa: BLE001 — no instance: neutral text
        return ""


BASE_INSTRUCTIONS = (
    "W.Alter is the user's modular capability stack on this VM. Use its connected modules across harnesses; keep the host runtime and permissions. These tools share its long-term "
    "memory and skills. " + _owner_line() + "Recalled memories are dated "
    "snapshots, not live state: verify current config/services before asserting them. Retain only durable "
    "facts about the user, their projects and decisions — never secrets, credentials or transient logs.")
mcp = FastMCP("walter-core", instructions=BASE_INSTRUCTIONS)  # + module layer, set once the tools are registered


def _agent_memory(method: str, args: dict, timeout: float = 180) -> str:
    """Transport only: privacy, retrieval, retention and reflection live in Walter Memory."""
    payload = {"version": 1, "method": method, "args": args, "caller": CLIENT_TAG}
    try:
        result = subprocess.run([*WALTER_MEMORY, "agent-memory"], input=json.dumps(payload, ensure_ascii=False),
                                capture_output=True, text=True, timeout=timeout)
        # agent-memory errors are structured and never echo input or credentials.
        if result.stdout.strip():
            json.loads(result.stdout)
            return result.stdout.strip()
    except Exception:
        pass
    return json.dumps({"status": "error", "text": "Walter Memory unavailable; no legacy fallback was used."})


@mcp.tool()
def memory_recall(query: str, budget: str = "mid", max_tokens: int = 2048) -> str:
    """Retrieve budgeted, cloud-safe canonical knowledge and evidence from Walter Memory.
    Returns source references; historical records may be stale. Uses local hybrid search,
    excluding legacy cognitive rows without canonical provenance. budget: low | mid | high."""
    return _agent_memory("recall", {"query": query, "budget": budget, "max_tokens": max_tokens})


@mcp.tool()
def memory_retain(content: str, context: str = "", tags: list[str] | None = None) -> str:
    """Record a durable fact once in Walter Memory's canonical event store, with module-owned privacy.
    Search indexing is asynchronous; the result explicitly reports the projection state. Never submit credentials."""
    return _agent_memory("retain", {"content": content, "context": context, "tags": tags or []})


@mcp.tool()
def memory_reflect(question: str, budget: str = "mid") -> str:
    """Synthesize an answer from permitted canonical memory with source references, using Walter Router.
    Local-only questions are refused; redacted questions are pseudonymised. Empty evidence makes no model call."""
    return _agent_memory("reflect", {"question": question, "budget": budget}, timeout=240)


def _soul_profile() -> Path:
    """The runtime-neutral identity walter-soul renders for the active instance, asked through its interface."""
    try:
        out = subprocess.run(["walter-soul", "path", "agent"], capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path("/nonexistent/walter-soul-agent-profile")


@mcp.tool()
def walter_profile() -> str:
    """Return the user's curated profile (USER.md), W.Alter's identity/style rules (walter-soul, the
    runtime-neutral render) and the critical memory buffer (MEMORY.md). Small; safe to load at the start of a session."""
    parts = []
    from walter_platform import instance  # the owner's profile lives in the instance (was ~/.hermes/memories)
    for label, path in (("USER.md", instance.path("profile", "USER.md")),
                        ("W.Alter identity", _soul_profile()),
                        ("MEMORY.md", instance.path("profile", "MEMORY.md"))):
        try:
            parts.append(f"## {label}\n{path.read_text(errors='replace').strip()}")
        except OSError as e:
            parts.append(f"## {label}\n(unavailable: {e.strerror})")
    return "\n\n".join(parts)


from walter_skills import client as skills_client  # walter-skills adapter: transport only, fallback to the git store


@mcp.tool()
def skills_manifest() -> str:
    """Explain walter-skills: purpose, components, ownership, and progressive discovery. Read once when needed."""
    return skills_client.manifest()


@mcp.tool()
def skills_index(domain: str = "", offset: int = 0, limit: int = 20, cursor: str = "") -> str:
    """Browse the Curator-maintained index. Empty domain lists domains only; select a domain for workflow/skill
    purposes and workflow dependencies, then skill_read the chosen entry. Continue with the answer's `cursor` (or
    next_offset as offset); no procedure bodies."""
    from walter_platform import capabilities
    read = f"skills_index:{domain}"
    if cursor:
        try:
            offset = capabilities.page_offset(read, cursor)
        except ValueError as e:
            return json.dumps(capabilities.error("invalid_request", str(e)), ensure_ascii=False)
    return json.dumps(capabilities.with_cursor(read, skills_client.index(domain, offset, limit)), ensure_ascii=False)


@mcp.tool()
def skills_search(query: str = "", limit: int = 8, context: str = "", include_archived: bool = False) -> str:
    """Find the W.Alter skills (tested procedures for the owner's tools, infra, projects and workflows) that match an
    intent. Pass the user's request as `query` (any language, plain words) and optionally the previous turn as
    `context`. Read the chosen skill with skill_read before acting. include_archived=True also searches retired
    skills (marked [archived])."""
    rows = skills_client.search(query, context, max(1, min(int(limit), 20)), include_archived, runtime=f"mcp-{CLIENT_TAG}")
    return "\n".join(f"- {x['name']}{' [archived]' if x.get('state') == 'archived' else ''}: {x.get('summary', '')[:220]}"
                     for x in rows) or "No skill matched."


@mcp.tool()
def skill_read(name: str, file_path: str = "") -> str:
    """Read the full SKILL.md of a W.Alter skill by name (as returned by skills_search), or one of its linked files
    (references/…, scripts/…) with file_path."""
    text = skills_client.read(name, file_path, runtime=f"mcp-{CLIENT_TAG}")
    return text[:60000] if text else f"Unknown skill or file '{name}' {file_path}. Use skills_search."


def _skills_door(kind: str, body: dict) -> str:
    d = skills_client.write(kind, body | {"runtime": CLIENT_TAG})
    if not d.get("ok"):
        return f"Refused: {d.get('refused') or d}"
    return f"Draft recorded ({d['draft']}). The walter-skills watcher judges it within a minute (judge + checks); if accepted it is live right away."


@mcp.tool()
def skill_propose(name: str, skill_md: str, reason: str, files_json: str = "", domain: str = "",
                  session_id: str = "") -> str:
    """Propose a NEW W.Alter skill after solving a task that will recur (a procedure that took several steps, a fix
    found the hard way, a workflow the owner asked for). skill_md = full SKILL.md with frontmatter (name: <name>,
    description: one line starting with "Use when …"), then the procedure as imperative rules with exact commands,
    paths and checks. Never paste secrets: say where they live. files_json = optional JSON {"references/x.md": "…",
    "scripts/y.sh": "…"}. Goes to drafts; judged within a minute before it is live."""
    try:
        files = json.loads(files_json) if files_json.strip() else None
    except json.JSONDecodeError as e:
        return f"files_json is not valid JSON: {e}"
    return _skills_door("propose", {"name": name, "skill_md": skill_md, "reason": reason, "files": files,
                                    "domain": domain, "session_id": session_id or None})


@mcp.tool()
def skill_patch(name: str, reason: str, skill_md: str = "", file_path: str = "", content: str = "",
                session_id: str = "") -> str:
    """Fix or improve an existing W.Alter skill when it proved wrong, outdated or incomplete while you used it (a
    command that failed, a path that moved, a missing step, a pitfall). Give either the full corrected skill_md, or
    file_path + content to replace one linked file (references/…, scripts/…). reason = what was wrong + evidence.
    Goes to drafts; judged within a minute before it is live."""
    return _skills_door("patch", {"name": name, "reason": reason, "skill_md": skill_md or None,
                                  "file_path": file_path or None, "content": content or None,
                                  "session_id": session_id or None})


def _walter_memory(*args: str, timeout: float = 600) -> str:
    r = subprocess.run([*WALTER_MEMORY, *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return f"Walter Memory error: {(r.stderr or r.stdout).strip()[-800:]}"
    return r.stdout.strip()


TASK_STATUSES = ("open", "suspended", "done", "failed", "cancelled")


@mcp.tool()
def tasks_list(status: str = "", thread_id: str = "", limit: int = 10) -> str:
    """The owner's durable tasks (objectives that outlive a turn, a session, an interface or a restart): what is in
    progress or suspended, with its progress, the number of attempts and how the last one ended. Use it to resume
    work or to answer "où en est… ?". status: open | suspended | done | failed | cancelled | all (default: the active
    ones); thread_id narrows to one conversation thread."""
    if status and status != "all" and status not in TASK_STATUSES:
        return json.dumps({"ok": False, "error": "status: open, suspended, done, failed, cancelled or all"})
    args = ["tasks", "list", "--limit", str(max(1, min(int(limit), 50)))]
    if status:
        args += ["--status", status]
    if thread_id:
        args += ["--thread", thread_id[:200]]
    return _walter_memory(*args, timeout=60)


def _run_meta(ctx) -> dict:
    """The run the caller works under, when its client says it (the engine passes `_meta.walter_*` on tools/call):
    a task it creates belongs to that run, so to its channel (a test run's never reaches the owner's list)."""
    try:
        meta = ctx.request_context.meta if ctx is not None else None
        extra = dict(getattr(meta, "model_extra", None) or {}) if meta is not None else {}
    except Exception:   # noqa: BLE001 — no request context (direct call, older client): the owner's
        extra = {}
    return {k: str(extra[f"walter_{k}"])[:80] for k in ("run_id", "session_id") if extra.get(f"walter_{k}")}


@mcp.tool()
def task_create(goal: str, entity_id: str = "", person: str = "", due_at: str = "", remind_at: str = "",
                draft: str = "", source: str = "", ctx: Context | None = None) -> str:
    """Create a durable task for the owner (a local record, nothing is sent to anyone): an explicit `goal` written
    with the person's name, never « le » / « il »; the linked person — `entity_id` (from person_lookup) or its exact
    full name in `person` (several or no match → an error with the candidates: ask the owner, never guess); `due_at`
    (YYYY-MM-DD or ISO with offset); `remind_at` = when the owner is reminded (ISO with its offset, e.g.
    2026-12-10T09:00:00+07:00), fired once by Walter's scheduler — without it a dated task reminds the owner on
    `due_at` (09:00 his time for a day); `draft` = a prepared message stored with the task,
    NOT sent (sending is a separate tool that needs its own permission); `source` = where the request came from.
    Answers the task read back from the Run Plane (`verified` true when it carries what was asked) and its reminder.
    Replaying the same call never creates a second task."""
    if not (goal or "").strip():
        return json.dumps({"ok": False, "error": "goal required"})
    spec = {"goal": goal[:500], "entity_id": entity_id[:80] or None, "entity_name": person[:200] or None,
            "due_at": due_at[:40] or None, "remind_at": remind_at[:40] or None, "draft": (draft or "")[:2000] or None,
            "source": {"text": source[:300]} if source else None, "by": CLIENT_TAG or "mcp", **_run_meta(ctx)}
    r = subprocess.run([*WALTER_MEMORY, "tasks", "create"], input=json.dumps(spec, ensure_ascii=False, default=str),
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return f"Walter Memory error: {(r.stderr or r.stdout).strip()[-800:]}"
    return r.stdout.strip()


@mcp.tool()
def task_update(task_id: str, status: str = "", progress: dict | None = None, result: dict | None = None,
                note: str = "") -> str:
    """Record where a durable task stands, so it can be resumed later from any conversation: `progress` (what is done,
    what remains, the next step — merged key by key), a short `note` (a finding, a failure and its cause), `result`
    when it is finished, and its status: open (being worked on), suspended (waiting: say for what in the note), done,
    failed, cancelled. Task ids come from tasks_list or from the Tasks block of your context. Never a secret."""
    if not task_id or (status and status not in TASK_STATUSES):
        return json.dumps({"ok": False, "error": "task_id required; status: open, suspended, done, failed or cancelled"})
    spec = {"task_id": task_id[:80], "status": status or None, "progress": progress if isinstance(progress, dict) else None,
            "result": result if isinstance(result, dict) else None, "note": (note or "")[:300] or None}
    if len(json.dumps(spec, ensure_ascii=False, default=str)) > 20000:
        return json.dumps({"ok": False, "error": "too large: keep progress and result to what is needed to resume"})
    r = subprocess.run([*WALTER_MEMORY, "tasks", "update"], input=json.dumps(spec, ensure_ascii=False, default=str),
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return f"Walter Memory error: {(r.stderr or r.stdout).strip()[-800:]}"
    return r.stdout.strip()


DEVBOARD_FIELDS = ("status", "title", "module", "owner", "change", "deadline", "decision_link")


@mcp.tool()
def devboard_correct(ref: str, field: str, value: str, reason: str) -> str:
    """Correct a card of the development board (ops/devboard), only when the owner reports a wrong card — never on
    your own inference. ref = "W-12"; field = status (waiting_owner|in_progress|paused|done|abandoned) |
    title | module | owner | change | deadline (YYYY-MM-DD, "" to clear) | decision_link (a decision anchor);
    reason = his words. The correction wins over every later reading of the agents' sessions."""
    if field not in DEVBOARD_FIELDS:
        return json.dumps({"ok": False, "error": f"field: one of {', '.join(DEVBOARD_FIELDS)}"})
    spec = {"ref": (ref or "").strip()[:20], "field": field, "value": (value or "")[:2000],
            "reason": (reason or "")[:500], "by": "owner"}
    r = subprocess.run(["walter-devboard", "correct"], input=json.dumps(spec, ensure_ascii=False),
                       capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()[-2000:]


@mcp.tool()
def memory_search(query: str, limit: int = 10, source: str = "", since: str = "", until: str = "",
                  evidence_only: bool = False, history: bool = False) -> str:
    """Unified search over everything W.Alter has observed and learned: knowledge (derived memories) AND original
    evidence (messages with W.Alter, Beeper chats, e-mails, calendar, files' extracted text), each result with its
    source and date. Full-text + semantic + rerank. evidence_only=True skips derived knowledge (raw history only).
    since/until: ISO dates. Prefer this to find *when/where/who said what*; memory_recall for synthesised facts.
    Each result has `typed_ref` (kind/ref_id unchanged): event:… → memory_events(event_id=…), derived:… →
    memory_view(key=…), object:… → vault_get(object_id=…). history=True also reads pre-V1 interpretations (archived memory generations), each marked as such."""
    args = ["search", query, "--limit", str(max(1, min(int(limit), 50))), "--rerank", "--cloud-safe"]
    if history:
        args.append("--history")
    for flag, value in (("--source", source), ("--since", since), ("--until", until)):
        if value:
            args += [flag, value]
    if evidence_only:
        args.append("--no-derived")
    return _walter_memory(*args, timeout=90)


@mcp.tool()
def memory_context(query: str, include_profile: bool = False, history: bool = False) -> str:
    """Ready-to-use memory context for a request: the owner's durable rules in force, Kardex card of people named in
    it, relevant knowledge (deduplicated), pointers to consolidated views (memory_view), and original sources when the
    request is about who/when/what was said. Budgeted (~2k tokens), cloud-safe. Call this first when answering
    anything personal; then go deeper with memory_view / memory_search / person_lookup. history=True also reads
    pre-V1 interpretations, marked « pré-V1 »."""
    args = ["context", query] + ([] if include_profile else ["--no-profile"]) + (["--history"] if history else [])
    return _walter_memory(*args, timeout=120)


@mcp.tool()
def memory_view(key: str = "", query: str = "", depth: str = "overview", max_tokens: int = 1500, at: str = "") -> str:
    """Walter Memory's consolidated views (Memory V1), rebuilt from current knowledge and evidence: a subject of work
    (g1:subject:…), an episode (episode:…: hypotheses keep their status — candidate / probable / confirmed), a period
    (period:day:YYYY-MM-DD, period:week:YYYY-Www, period:month:YYYY-MM). Give `key` to read one at a depth: index
    (one line) · overview (budgeted current state) · synthesis (how it evolved) · details (every item with stage and id)
    · sources (what it is built from: knowledge, observations, sub-views, with event ids for memory_events)
    · state (a project's current state, key project:<name> e.g. project:walter or « Walter Memory »: state, goals
    open/blocked/done, decisions in force, recent changes, unresolved contradictions, known next steps, sub-projects'
    important news; every line dated with its provenance; `at`=YYYY-MM-DD for the state as it was then; key owner =
    the owner's rules in force, dated states, goals by their evidence, states to re-check; key now = where, agenda,
    open work, the freshness of personal knowledge and why it is late, each with its freshness; key me = both,
    « où en suis-je »; key person:<name or id> = the relation with one person: who they are, what is known of the
    relation by who says it (the person / the owner / the data / a hypothesis), recent changes, exchanges as measures,
    commitments, possible follow-ups (nothing is created), contexts, measured rhythm, replaced information; a name
    shared by several people lists them, never merged). Key
    derived:<id> (a memory_search `typed_ref`) reads one knowledge item with its evidence. Give `query` instead to
    find the views closest to some words. Cloud-safe: local-only views are never returned."""
    if key:
        d = depth if depth in ("index", "overview", "synthesis", "details", "sources", "state") else "overview"
        return _walter_memory("views", "read", key, "--depth", d, "--max-tokens", str(max(100, min(int(max_tokens), 8000))),
                              *(["--at", at] if at and d == "state" else []),
                              *(["--json"] if d == "sources" else []), timeout=60)
    return _walter_memory("views", "find", "--query", query or "", timeout=60)


@mcp.tool()
def person_lookup(name: str) -> str:
    """Kardex social card for a person (name, alias, handle or phone): their accounts across networks, relationship
    metrics with the owner (volume, who initiates, reply latencies, first/last contact), measured communication changes,
    what Kardex knows (respecting mention policies), shared groups, recent interactions, media counts.
    Only facts measured or stated with evidence; deviations are observations, never causes."""
    return _walter_memory("social", "person", name, "--cloud-safe", timeout=60)


@mcp.tool()
def memory_events(text: str = "", source: str = "", event_type: str = "", thread_id: str = "", since: str = "",
                  until: str = "", order: str = "newest", event_id: str = "", limit: int = 20, cursor: str = "") -> str:
    """Read W.Alter's canonical event history (what actually happened: messages, conversations with W.Alter,
    e-mails, calendar, files...). Exact substring search on content; filters: source (hermes, beeper, gmail,
    calendar, vault, claude_code, codex, dsh…), event_type (message.received, message.sent…), thread_id,
    since/until (ISO). order="oldest" for the first events (« le tout premier message sur X »), "newest" by default.
    Answer = compact list (event_id, date, source, a window of the content around `text`); event_id="…" (or
    "event:…") returns that one event in full, with `typed_ref` and `reply_to_event_id` when the replied message is
    readable. A truncated conversation answers `cursor`: pass it back as is to read the next page. A message with files carries `attachments` [{object_id, kind, mime, name, derived_kind,
    text}] — e.g. a voice note's transcript, a PDF's text (vault_get for the bytes, vault_search(thread=…) for all the
    files of a conversation). Use memory_search for synthesised knowledge, this for the original record. Rows follow
    Walter Memory's privacy policy for cloud readers (the owner's cloud ceiling); credentials are never exposed."""
    if order not in ("newest", "oldest"):
        return json.dumps({"error": "order must be newest or oldest"})
    args = ["events", "--limit", str(max(1, min(int(limit), 200))), "--cloud-safe",
            "--order", "asc" if order == "oldest" else "desc"]
    for flag, value in (("--text", text), ("--source", source), ("--type", event_type), ("--thread", thread_id),
                        ("--since", since), ("--until", until), ("--id", event_id), ("--cursor", cursor)):
        if value:
            args += [flag, value]
    if not event_id:   # one event asked (limit=1, « the very first… »): its text whole, within the answer budget
        args += ["--compact", "16000" if int(limit) <= 1 else "500"]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_search(query: str = "", runtime: str = "", event_type: str = "", tool: str = "", session: str = "",
                since: str = "", until: str = "", limit: int = 20) -> str:
    """walter-logs: search what Walter's agents DID in past sessions, any runtime (Walter Engine, Claude
    Code, Codex; earlier Hermes and DSH sessions): user/assistant messages, reasoning, tool calls with their full arguments, tool results in full,
    compaction summaries. Words (full-text, accent-insensitive) or an exact string (paths, error messages, ids).
    Filters: runtime (hermes, claude_code, codex, dsh), event_type (user/message, assistant/message,
    assistant/reasoning, tool/call, tool/result, compaction/summary), tool (e.g. terminal, Bash, walter_route),
    session (id or part of it; a session is a walter-logs session id such as claude_code/vm/<uuid>), since/until
    (ISO). Each hit has a ref 'session#seq': pass it as is as `ref` to logs_timeline (the surrounding flow) or
    logs_get (the full event). Secrets are masked; local-only content is hidden."""
    args = ["logs", "search", query, "--limit", str(max(1, min(int(limit), 100))), "--cloud-safe"]
    for flag, value in (("--runtime", runtime), ("--type", event_type), ("--tool", tool), ("--session", session),
                        ("--since", since), ("--until", until)):
        if value:
            args += [flag, value]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_timeline(session: str = "", seq: int = -1, before: int = 5, after: int = 15, event_type: str = "",
                  max_chars: int = 600, ref: str = "") -> str:
    """walter-logs: the flow of one agent session in order (message → reasoning → tool call → result → answer...).
    ref: a logs_search ref 'session#seq' (or log:session#seq), as is — or session (id or part of it) + seq (anchor
    event, -1 = the latest events); before/after: how many events around it; event_type: only one type; max_chars:
    text per event (logs_get for the full text)."""
    if not (ref or session):
        return json.dumps({"error": "invalid_request", "message": "pass ref='session#seq' from logs_search, or session"})
    head = ["--ref", ref] if ref else [session]
    args = ["logs", "timeline", *head, "--before", str(max(0, min(int(before), 100))),
            "--after", str(max(0, min(int(after), 200))), "--max-chars", str(max(80, min(int(max_chars), 5000))),
            "--cloud-safe"]
    if int(seq) >= 0 and not ref:
        args += ["--seq", str(int(seq))]
    if event_type:
        args += ["--type", event_type]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_get(session: str = "", seq: int = -1, ref: str = "") -> str:
    """walter-logs: one event in full (e.g. a complete tool result or reasoning), with the linked tool call/result.
    ref: a logs_search ref 'session#seq' (or log:session#seq), as is — or session + seq."""
    if ref:
        return _walter_memory("logs", "get", "--ref", ref, "--cloud-safe", timeout=60)
    if not session or int(seq) < 0:
        return json.dumps({"error": "invalid_request", "message": "pass ref='session#seq' from logs_search, or session and seq"})
    return _walter_memory("logs", "get", session, "--seq", str(int(seq)), "--cloud-safe", timeout=60)


@mcp.tool()
def vault_search(text: str = "", kind: str = "", source: str = "", thread: str = "", event_id: str = "",
                 since: str = "", until: str = "", limit: int = 20) -> str:
    """Search the Raw Vault: every raw file of the user's life that is not text (photos, pictures, screenshots,
    videos, voice notes, scanned or received documents: quotes, invoices, PDFs). Matches file names and derived text (OCR/transcripts/captions); empty text lists
    the newest permitted metadata. kind: image|screenshot|video|audio|document|archive. thread: the files of one
    conversation (a thread_id from memory_events), oldest first — « the voice notes of conversation X » =
    vault_search(kind="audio", thread=X); event_id: the files of one message. since/until: ISO dates (capture time).
    Each result carries its derived text (derived_kind transcript|extract|ocr|caption). Objects follow Walter
    Memory's privacy policy for cloud readers (same rule as memory_events). Each result has `object_id` and
    `typed_ref` (object:…) for vault_get."""
    args = ["media", "search", "--limit", str(max(1, min(int(limit), 100))), "--cloud-safe"]
    for flag, value in (("--kind", kind), ("--source", source), ("--thread", thread), ("--event", event_id),
                        ("--since", since), ("--until", until)):
        if value:
            args += [flag, value]
    return _walter_memory(*args, "--", text, timeout=60)


@mcp.tool()
def vault_get(object_id: str, dest_dir: str = "/tmp/walter-vault") -> str:
    """Download one Raw Vault file (by id, object:<id> or sha256) to a local directory on the W.Alter VM,
    integrity-checked.
    Returns the local path. Restricted objects are refused before any download or directory creation."""
    return _walter_memory("objects", "get", object_id, "--dest-dir", dest_dir, "--cloud-safe")


@mcp.tool()
def vault_put(path: str, source: str = "", captured_at: str = "", links: list[str] | None = None) -> str:
    """Store a local file (path on the W.Alter VM) in the Raw Vault, once (deduplicated by content).
    source: where it comes from (default: the client name). captured_at: ISO date if known.
    links: typed references to attach people, messages and conversations: ["entity:<uuid>" (person_lookup),
    "event:<id>" (memory_events), "thread:<id>"]; older link forms (type:id) are still accepted."""
    args = ["objects", "put", path, "--source", source or CLIENT_TAG]
    if captured_at:
        args += ["--captured", captured_at]
    for link in links or []:
        args += ["--link", link]
    return _walter_memory(*args)


@mcp.tool()
def browser_session(site: str, session: str = "", verify: bool = True, engine: str = "camoufox") -> str:
    """Open (or refresh) a Camoufox browser session logged in as the owner on a site (google, meta, linkedin, x…; see
    browser_sites), so you can use a web interface on the owner's behalf. Their current Brave cookies are copied from his Mac,
    decrypted and injected server-side: only metadata comes back (cookie counts, authenticated yes/no), never a value.
    Then drive the browser with the Camoufox HTTP API on 127.0.0.1:9377 (/tab/new, /tab/navigate, /tab/snapshot,
    /tab/click, /tab/keyboard-type, /tab/fetch-binary, /tab/close) using userId = the returned session name.
    session: [a-z0-9_-] name, default '<site>-me'. Call again whenever the site shows a sign-in page.
    engine: "camoufox" (Firefox, default) or "chromium" (CloakBrowser stealth Chromium, API on 127.0.0.1:9378) when a
    site needs Chromium (Chrome-only features, React DevTools hooks, a site that rejects Firefox). Same exit and rules."""
    import browser_auth
    try:
        return json.dumps(browser_auth.login(site, session, client=CLIENT_TAG, verify=verify, engine=engine),
                          ensure_ascii=False)
    except Exception as e:
        return f"browser_session failed: {e}"


@mcp.tool()
def browser_sites() -> str:
    """Sites browser_session can log into (name → cookie domains, login check URL). Add one in
    /opt/walter-core/browser_sites.json (no secret in it)."""
    import browser_auth
    return json.dumps(browser_auth.sites(), ensure_ascii=False)


@mcp.tool()
def walter_health() -> str:
    """Is everything working? Status and health of the W.Alter stack: core services, Walter Engine and its Telegram door, deploy freshness (services
    running code older than the code on disk), context preflight (health, plans decided without their model in the
    last 30 min), Walter Memory model-call failures per processor, memory health score, model router, disk."""
    out = []
    units = _stack_units()
    states = subprocess.run(["systemctl", "is-active", *units], capture_output=True, text=True).stdout.split()
    out += [f"{u}: {s}" for u, s in zip(units, states)]
    # the engine's unit: walter-engine (native, 17/11) unless the rollback re-enabled dsh-web
    unit = "dsh-web" if subprocess.run(["systemctl", "is-enabled", "walter-engine"], capture_output=True,
                                       text=True).stdout.strip() != "enabled" else "walter-engine"
    eng = subprocess.run(["systemctl", "is-active", unit, "walter-telegram"], capture_output=True, text=True)
    out.append(f"walter engine ({unit}) / telegram door: " + " / ".join(eng.stdout.split()))
    try:  # SOCLE A8: a service running old code looked healthy for 4 h on 2026-11-11
        r = subprocess.run(["walter", "deploy", "check", "--json"], capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout)
        out.append("deploy: all services run the code on disk" if not d["stale"] else
                   f"deploy: STALE {len(d['stale'])} — " + ", ".join(
                       f"{u} ({(d.get('repair_plan') or {}).get(u, '?')})" for u in d["stale"])
                   + ("" if d.get("repair_enabled") else " | auto-restart off (core config deploy.toml)"))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        out.append("deploy: no report")
    try:  # context preflight: answering, and the share of plans decided without their model (30 min)
        from datetime import datetime, timedelta, timezone
        from walter_platform import instance
        try:
            ok = httpx.get("http://127.0.0.1:8897/health", timeout=5).json().get("ok")
        except Exception:  # noqa: BLE001
            ok = False
        now = datetime.now(timezone.utc)
        rows = []
        for day in sorted({(now - timedelta(minutes=30)).date(), now.date()}):
            p = Path(instance.root()) / "state" / "context" / "shadow" / f"preflight-{day.isoformat()}.jsonl"
            if p.exists():
                rows += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        recent, bad = 0, 0
        for row in rows:
            at = datetime.fromisoformat(str(row.get("at")).replace("Z", "+00:00"))
            at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
            if now - at <= timedelta(minutes=30):
                recent += 1
                dec = ((row.get("plan") or {}).get("decision") or {})
                bad += bool(dec.get("degraded") or dec.get("error"))
        out.append(f"context preflight: {'ok' if ok else 'NOT ANSWERING'}, degraded plans 30 min: {bad}/{recent}"
                   + (" — DEGRADED" if bad >= 2 and bad >= 0.3 * recent else ""))
    except (OSError, ValueError, TypeError):
        out.append("context preflight: no report")
    try:  # Walter Memory: model calls failing per processor (severity error), decisions taken by fallback
        r = subprocess.run(["/usr/local/bin/walter-memory", "health"], capture_output=True, text=True, timeout=120)
        h = json.loads(r.stdout)
        mc = [p for p in h.get("problems", []) if p.startswith("model_calls:")]
        tr = [p for p in h.get("problems", []) if p.startswith("triage:")]
        out.append(("memory model calls: ok (30 min)" if not mc else "memory model calls: FAILING — " + "; ".join(p[:160] for p in mc[:4]))
                   + (" | " + tr[0][:120] if tr else ""))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        out.append("memory model calls: no report")
    try:
        from walter_platform import instance
        summary = json.loads((Path(instance.root()) / "logs/memory-autopilot/latest.json").read_text())["summary"]
        out.append(f"memory autopilot: {summary.get('severity')} score={summary.get('score')} "
                   f"errors={summary.get('errors')} warnings={summary.get('warnings')}")
    except (OSError, KeyError, ValueError, ImportError):
        out.append("memory autopilot: no report")
    try:  # Walter Router (model choice per task): fed, fresh, providers reachable
        r = subprocess.run(["walter-router", "health"], capture_output=True, text=True, timeout=30)
        h = json.loads(r.stdout)
        line = "walter-router: ok" if h["ok"] else "walter-router: KO — " + "; ".join(h["issues"][:3])
        if h.get("warnings"):
            line += " | avertissements : " + "; ".join(w[:90] for w in h["warnings"][:2])
        out.append(line)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        out.append("walter-router: no health report")
    st = os.statvfs("/")
    out.append(f"disk /: {100 - st.f_bavail * 100 // st.f_blocks}% used, {st.f_bavail * st.f_frsize >> 30} GiB free")
    return "\n".join(out)


from walter_capabilities import register as register_capabilities
register_capabilities(mcp, CLIENT_TAG, local_control="--http" not in sys.argv)

# Every module presents itself (level 0) in one layer composed by walter-context from the module contracts, for the
# tools this server really exposes; it replaces the router brief alone. Fixed for the life of the server process.
# A client may list a core toolset and the one-line (M0) module layer (config/toolsets.toml, lot 3 2026-11-07); the
# layer is composed for every tool this server can run, listed or reachable through walter_call.
from walter_capabilities import apply_toolset, client_profile, module_layer, toolset_note  # noqa: E402
_PROFILE = client_profile(CLIENT_TAG)
_LAYER = module_layer(sorted(t.name for t in mcp._tool_manager.list_tools()), _PROFILE["module_layer"])
_LAYER = _LAYER or router_brief()  # fallback: the router's own brief, as before the module layer
_HIDDEN = apply_toolset(mcp, _PROFILE["toolset"])
_LAYER = "\n\n".join(x for x in (_LAYER, toolset_note(_HIDDEN)) if x)
if _LAYER:
    mcp._mcp_server.instructions = BASE_INSTRUCTIONS + "\n\n" + _LAYER

# One lock per declared resource (lot 3e): two calls on the same browser session, device, chat, task or skill never
# interleave, whichever client process makes them. Installed before the policy so a refused call never waits.
from walter_platform import capabilities as _capabilities  # noqa: E402
_capabilities.install_locks(mcp)

# Walter's one execution policy (core/security, lot E3): a call it refuses never reaches a tool, whatever the client.
sys.path.insert(0, str(Path(__file__).resolve().parent / "security"))
from walter_security import mcp_guard  # noqa: E402
mcp_guard.install(mcp, CLIENT_TAG)


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = int(os.environ.get("WALTER_CORE_PORT", "8931"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
