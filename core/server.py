#!/usr/bin/env python3
"""walter-core — the W.Alter harness as one stable MCP surface.

Any MCP client (Claude Code, Claude Desktop, Cursor, Codex, another Hermes...) gets the same
capabilities without importing Hermes internals:

  memory_recall / memory_retain / memory_reflect  → Walter Memory canonical facade (privacy + Router synthesis)
  walter_profile                                  → USER.md / SOUL.md / MEMORY.md
  skills_search / skill_read                      → W.Alter skills (walter-skills service :8891)
  ask_hermes                                      → delegate a task to the live Hermes agent (all its tools)
  memory_search / memory_events                   → unified search (knowledge + evidence) / canonical event history
  person_lookup                                   → Kardex social card (relationship metrics, accounts, groups)
  memory_context                                  → budgeted context block for a request (P6 context engine)
  vault_search / vault_get / vault_put            → Raw Vault: every non-text raw file (Google Drive + PG catalog)
  browser_session / browser_sites                 → Camoufox session logged in as Monsieur (his Brave cookies,
                                                    injected server-side; agents never see a cookie value)
  walter_health                                   → status of the stack services

Each tool talks to a public HTTP API or a file, never to Hermes' Python modules, so `hermes update`
cannot break this server and this server cannot break Hermes.

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
from mcp.server.fastmcp import FastMCP

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
HERMES_API_URL = os.environ.get("WALTER_HERMES_API_URL", "http://127.0.0.1:8642")
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


def _env_value(name: str) -> str:
    """Read one key from Hermes' .env at call time (rotations apply without restart)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in (HERMES_HOME / ".env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


from walter_capabilities import router_brief  # noqa: E402 — the router's own brief joins the server instructions

BASE_INSTRUCTIONS = (
    "W.Alter is the user's modular capability stack on this VM. Use its connected modules across harnesses; keep the host runtime and permissions. These tools share its long-term "
    "memory and skills. The user is addressed as 'Monsieur' and works in French. Recalled memories are dated "
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
    Search indexing is asynchronous. No direct copy is sent to the legacy Hindsight bank;
    the result explicitly reports the projection state. Never submit credentials."""
    return _agent_memory("retain", {"content": content, "context": context, "tags": tags or []})


@mcp.tool()
def memory_reflect(question: str, budget: str = "mid") -> str:
    """Synthesize an answer from permitted canonical memory with source references, using Walter Router.
    This is Walter Memory reflection, not legacy Hindsight reflect. Local-only questions are
    refused; redacted questions are pseudonymised. Empty evidence makes no model call."""
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
    for label, path in (("USER.md", HERMES_HOME / "memories" / "USER.md"),
                        ("W.Alter identity", _soul_profile()),
                        ("MEMORY.md", HERMES_HOME / "memories" / "MEMORY.md")):
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
def skills_index(domain: str = "", offset: int = 0, limit: int = 20) -> str:
    """Browse the Curator-maintained index. Empty domain lists domains only; select a domain for workflow/skill
    purposes and workflow dependencies, then skill_read the chosen entry. next_offset paginates; no procedure bodies."""
    return json.dumps(skills_client.index(domain, offset, limit), ensure_ascii=False)


@mcp.tool()
def skills_search(query: str = "", limit: int = 8, context: str = "", include_archived: bool = False) -> str:
    """Find the W.Alter skills (tested procedures for Monsieur's tools, infra, projects and workflows) that match an
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
    found the hard way, a workflow Monsieur asked for). skill_md = full SKILL.md with frontmatter (name: <name>,
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


@mcp.tool()
def ask_hermes(prompt: str, session_id: str = "", timeout_s: int = 600) -> str:
    """Delegate a task to the live W.Alter/Hermes agent, which has the user's integrations (Telegram,
    Google accounts, calendar, browser, voice, cron...). Blocks until Hermes answers.
    Pass the returned session_id back to continue the same conversation."""
    key = _env_value("API_SERVER_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    r = httpx.post(f"{HERMES_API_URL}/v1/chat/completions", headers=headers,
                   json={"model": "hermes-agent", "stream": False,
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=max(30, min(int(timeout_s), 1800)))
    if r.status_code >= 400:
        return f"Hermes API error HTTP {r.status_code}: {r.text[:500]}"
    answer = r.json()["choices"][0]["message"]["content"]
    return f"{answer}\n\n[session_id: {r.headers.get('X-Hermes-Session-Id', '')}]"


def _walter_memory(*args: str, timeout: float = 600) -> str:
    r = subprocess.run([*WALTER_MEMORY, *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return f"Walter Memory error: {(r.stderr or r.stdout).strip()[-800:]}"
    return r.stdout.strip()


@mcp.tool()
def memory_search(query: str, limit: int = 10, source: str = "", since: str = "", until: str = "",
                  evidence_only: bool = False, history: bool = False) -> str:
    """Unified search over everything W.Alter has observed and learned: knowledge (derived memories) AND original
    evidence (messages with W.Alter, Beeper chats, e-mails, calendar, files' extracted text), each result with its
    source and date. Full-text + semantic + rerank. evidence_only=True skips derived knowledge (raw history only).
    since/until: ISO dates. Prefer this to find *when/where/who said what*; memory_recall for synthesised facts.
    history=True also reads pre-V1 interpretations (archived memory generations), each marked as such."""
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
def memory_view(key: str = "", query: str = "", depth: str = "overview", max_tokens: int = 1500) -> str:
    """Walter Memory's consolidated views (Memory V1), rebuilt from current knowledge and evidence: a subject of work
    (g1:subject:…), an episode (episode:…: hypotheses keep their status — candidate / probable / confirmed), a period
    (period:day:YYYY-MM-DD, period:week:YYYY-Www, period:month:YYYY-MM). Give `key` to read one at a depth: index
    (one line) · overview (budgeted current state) · synthesis (how it evolved) · details (every item with stage and id)
    · sources (what it is built from: knowledge, observations, sub-views, with event ids for memory_events). Give
    `query` instead to find the views closest to some words. Cloud-safe: local-only views are never returned."""
    if key:
        d = depth if depth in ("index", "overview", "synthesis", "details", "sources") else "overview"
        return _walter_memory("views", "read", key, "--depth", d, "--max-tokens", str(max(100, min(int(max_tokens), 8000))),
                              *(["--json"] if d == "sources" else []), timeout=60)
    return _walter_memory("views", "find", "--query", query or "", timeout=60)


@mcp.tool()
def person_lookup(name: str) -> str:
    """Kardex social card for a person (name, alias, handle or phone): their accounts across networks, relationship
    metrics with Monsieur (volume, who initiates, reply latencies, first/last contact), measured communication changes,
    what Kardex knows (respecting mention policies), shared groups, recent interactions, media counts.
    Only facts measured or stated with evidence; deviations are observations, never causes."""
    return _walter_memory("social", "person", name, "--cloud-safe", timeout=60)


@mcp.tool()
def memory_events(text: str = "", source: str = "", event_type: str = "", thread_id: str = "", since: str = "",
                  limit: int = 20) -> str:
    """Read W.Alter's canonical event history (what actually happened: messages, conversations with W.Alter,
    e-mails, calendar, files...). Exact substring search on content; filters: source (hermes, beeper, gmail,
    calendar, vault, claude…), event_type (message.received, message.sent, tool.called…), thread_id, since (ISO).
    Use memory_recall for synthesised knowledge, this for the original record. Only cloud_allowed rows are exposed."""
    args = ["events", "--limit", str(max(1, min(int(limit), 200))), "--cloud-safe"]
    for flag, value in (("--text", text), ("--source", source), ("--type", event_type), ("--thread", thread_id),
                        ("--since", since)):
        if value:
            args += [flag, value]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_search(query: str = "", runtime: str = "", event_type: str = "", tool: str = "", session: str = "",
                since: str = "", until: str = "", limit: int = 20) -> str:
    """walter-logs: search what Walter's agents DID in past sessions, any runtime (Hermes and its profiles, Claude
    Code, Codex, DSH): user/assistant messages, reasoning, tool calls with their full arguments, tool results in full,
    compaction summaries. Words (full-text, accent-insensitive) or an exact string (paths, error messages, ids).
    Filters: runtime (hermes, claude_code, codex, dsh), event_type (user/message, assistant/message,
    assistant/reasoning, tool/call, tool/result, compaction/summary), tool (e.g. terminal, Bash, walter_route),
    session (id or part of it), since/until (ISO). Each hit has a ref 'session#seq': open the surrounding flow with
    logs_timeline(session, seq), the full event with logs_get. Secrets are masked; local-only content is hidden."""
    args = ["logs", "search", query, "--limit", str(max(1, min(int(limit), 100))), "--cloud-safe"]
    for flag, value in (("--runtime", runtime), ("--type", event_type), ("--tool", tool), ("--session", session),
                        ("--since", since), ("--until", until)):
        if value:
            args += [flag, value]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_timeline(session: str, seq: int = -1, before: int = 5, after: int = 15, event_type: str = "",
                  max_chars: int = 600) -> str:
    """walter-logs: the flow of one agent session in order (message → reasoning → tool call → result → answer...).
    session: id or part of it (from logs_search refs 'session#seq'); seq: anchor event (-1 = the latest events);
    before/after: how many events around it; event_type: only one type; max_chars: text per event (logs_get for
    the full text)."""
    args = ["logs", "timeline", session, "--before", str(max(0, min(int(before), 100))),
            "--after", str(max(0, min(int(after), 200))), "--max-chars", str(max(80, min(int(max_chars), 5000))),
            "--cloud-safe"]
    if int(seq) >= 0:
        args += ["--seq", str(int(seq))]
    if event_type:
        args += ["--type", event_type]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def logs_get(session: str, seq: int) -> str:
    """walter-logs: one event in full (e.g. a complete tool result or reasoning), with the linked tool call/result."""
    return _walter_memory("logs", "get", session, "--seq", str(int(seq)), "--cloud-safe", timeout=60)


@mcp.tool()
def vault_search(text: str = "", kind: str = "", source: str = "", limit: int = 20) -> str:
    """Search the Raw Vault: every raw file of the user's life that is not text (photos, screenshots, videos,
    voice notes, documents). Matches file names and derived text (OCR/transcripts/captions); empty text lists
    the newest permitted metadata. kind: image|screenshot|video|audio|document|archive.
    Only cloud_allowed objects are exposed. Returns ids for vault_get."""
    args = ["objects", "search", text, "--limit", str(max(1, min(int(limit), 100))), "--cloud-safe"]
    if kind:
        args += ["--kind", kind]
    if source:
        args += ["--source", source]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def vault_get(object_id: str, dest_dir: str = "/tmp/walter-vault") -> str:
    """Download one Raw Vault file (by id or sha256) to a local directory on the W.Alter VM, integrity-checked.
    Returns the local path. Restricted objects are refused before any download or directory creation."""
    return _walter_memory("objects", "get", object_id, "--dest-dir", dest_dir, "--cloud-safe")


@mcp.tool()
def vault_put(path: str, source: str = "", captured_at: str = "", links: list[str] | None = None) -> str:
    """Store a local file (path on the W.Alter VM) in the Raw Vault, once (deduplicated by content).
    source: where it comes from (default: the client name). captured_at: ISO date if known.
    links: ["kardex_contact:5", "hermes_session:<id>", ...] to attach people/conversations."""
    args = ["objects", "put", path, "--source", source or CLIENT_TAG]
    if captured_at:
        args += ["--captured", captured_at]
    for link in links or []:
        args += ["--link", link]
    return _walter_memory(*args)


@mcp.tool()
def browser_session(site: str, session: str = "", verify: bool = True, engine: str = "camoufox") -> str:
    """Open (or refresh) a Camoufox browser session logged in as Monsieur on a site (google, meta, linkedin, x…; see
    browser_sites), so you can use a web interface on his behalf. His current Brave cookies are copied from his Mac,
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
    """Status of the W.Alter stack: core services, Hermes gateway, memory health score, model router, disk."""
    out = []
    units = _stack_units()
    states = subprocess.run(["systemctl", "is-active", *units], capture_output=True, text=True).stdout.split()
    out += [f"{u}: {s}" for u, s in zip(units, states)]
    gw = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway"], capture_output=True, text=True)
    out.append(f"hermes-gateway (user): {gw.stdout.strip() or gw.stderr.strip()}")
    try:
        summary = json.loads((HERMES_HOME / "logs/memory-autopilot/latest.json").read_text())["summary"]
        out.append(f"memory autopilot: {summary.get('severity')} score={summary.get('score')} "
                   f"errors={summary.get('errors')} warnings={summary.get('warnings')}")
    except (OSError, KeyError, ValueError):
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


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = int(os.environ.get("WALTER_CORE_PORT", "8931"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
