#!/usr/bin/env python3
"""walter-core — the W.Alter harness as one stable MCP surface.

Any MCP client (Claude Code, Claude Desktop, Cursor, Codex, another Hermes...) gets the same
capabilities without importing Hermes internals:

  memory_recall / memory_retain / memory_reflect  → Hindsight (Postgres + pgvector), bank "walter"
  walter_profile                                  → USER.md / SOUL.md / MEMORY.md
  skills_search / skill_read                      → Hermes procedural skills (~/.hermes/skills)
  ask_hermes                                      → delegate a task to the live Hermes agent (all its tools)
  memory_search / memory_events                   → unified search (knowledge + evidence) / canonical event history
  person_lookup                                   → Kardex social card (relationship metrics, accounts, groups)
  vault_search / vault_get / vault_put            → Raw Vault: every non-text raw file (Google Drive + PG catalog)
  walter_health                                   → status of the stack services

Each tool talks to a public HTTP API or a file, never to Hermes' Python modules, so `hermes update`
cannot break this server and this server cannot break Hermes.

Transport: stdio by default (local clients). `--http` serves streamable HTTP on 127.0.0.1 for a
reverse proxy that adds authentication (never expose it bare).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
HINDSIGHT_URL = os.environ.get("WALTER_HINDSIGHT_URL", "http://127.0.0.1:8888")
BANK = os.environ.get("WALTER_BANK_ID", "walter")
HERMES_API_URL = os.environ.get("WALTER_HERMES_API_URL", "http://127.0.0.1:8642")
CLIENT_TAG = os.environ.get("WALTER_CLIENT_TAG", "claude")
SKILLS_DIR = HERMES_HOME / "skills"
STACK_UNITS = [
    "hindsight-api", "walter-voice-memory", "walter-memory-gateway", "raw-vault-s3", "hermes-bridge", "voice-router",
    "hermes-dashboard", "cloudflared-tunnel", "docker",
]
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


def _hindsight(path: str, body: dict, timeout: float = 60.0) -> dict:
    r = httpx.post(f"{HINDSIGHT_URL}/v1/default/banks/{BANK}{path}", json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Hindsight {path} → HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def _skills() -> list[dict]:
    items = []
    for f in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            meta = _frontmatter(f.read_text(errors="replace")[:4000])
        except OSError:
            continue
        items.append({"name": meta.get("name") or f.parent.name, "description": meta.get("description", ""),
                      "tags": meta.get("tags", ""), "path": str(f)})
    return items


mcp = FastMCP("walter-core", instructions=(
    "W.Alter is the user's personal AI agent (Hermes) running on this VM. These tools share its long-term "
    "memory and skills. The user is addressed as 'Monsieur' and works in French. Recalled memories are dated "
    "snapshots, not live state: verify current config/services before asserting them. Retain only durable "
    "facts about the user, their projects and decisions — never secrets, credentials or transient logs."))


@mcp.tool()
def memory_recall(query: str, budget: str = "mid", max_tokens: int = 2048) -> str:
    """Search W.Alter's long-term memory about the user (preferences, projects, people, past decisions).
    Use before answering anything personal or project-related. budget: low | mid | high (depth/latency)."""
    body = {"query": query, "budget": budget if budget in BUDGETS else "mid", "max_tokens": int(max_tokens),
            # junk/task-log memories flagged by the usefulness audit are kept but never recalled
            "tag_groups": [{"not": {"tags": ["quarantine:noise"], "match": "any_strict"}}]}
    data = _hindsight("/memories/recall", body)
    results = data.get("results") or []
    if not results:
        return "No relevant memory."
    lines = []
    for i, item in enumerate(results, 1):
        when = item.get("occurred_start") or item.get("mentioned_at") or ""
        kind = item.get("type") or ""
        lines.append(f"{i}. [{kind}{' · ' + when[:10] if when else ''}] {item.get('text', '').strip()}")
    return "\n".join(lines)


@mcp.tool()
def memory_retain(content: str, context: str = "", tags: list[str] | None = None) -> str:
    """Store a durable fact in W.Alter's memory so every agent (Hermes, Claude, voice) knows it.
    content: a self-contained statement, e.g. "Monsieur prefers X because Y". Never store secrets."""
    item = {"content": content, "context": context or f"noted by {CLIENT_TAG} via walter-core",
            "tags": sorted({f"source:{CLIENT_TAG}", *(tags or [])})}
    # Canonical record first (the statement as told, A1/§5), then Hindsight until the P5 router takes over.
    note = _walter_memory("note", content, "--source", CLIENT_TAG, "--context", context,
                          *[x for t in tags or [] for x in ("--tag", t)], timeout=60)
    data = _hindsight("/memories", {"items": [item], "async": True})
    return (f"Recorded as event ({'ok' if 'recorded' in note else note[:200]}); "
            f"queued for memory (operation {data.get('operation_id') or data.get('id') or 'ok'}).")


@mcp.tool()
def memory_reflect(question: str, budget: str = "mid") -> str:
    """Ask W.Alter's memory to reason over everything it knows and answer a synthetic question
    (e.g. "What are Monsieur's current priorities?"). Slower than memory_recall."""
    data = _hindsight("/reflect", {"query": question, "budget": budget if budget in BUDGETS else "mid"},
                      timeout=180.0)
    return data.get("text") or json.dumps(data, ensure_ascii=False)[:4000]


@mcp.tool()
def walter_profile() -> str:
    """Return the user's curated profile (USER.md), W.Alter's identity/style rules (SOUL.md) and the
    critical memory buffer (MEMORY.md). Small; safe to load at the start of a session."""
    parts = []
    for label, path in (("USER.md", HERMES_HOME / "memories" / "USER.md"),
                        ("SOUL.md", HERMES_HOME / "SOUL.md"),
                        ("MEMORY.md", HERMES_HOME / "memories" / "MEMORY.md")):
        try:
            parts.append(f"## {label}\n{path.read_text(errors='replace').strip()}")
        except OSError as e:
            parts.append(f"## {label}\n(unavailable: {e.strerror})")
    return "\n\n".join(parts)


@mcp.tool()
def skills_search(query: str = "", limit: int = 15) -> str:
    """Search W.Alter's procedural skills (how-tos for the user's tools, infra and workflows).
    Empty query lists the first skills. Read one with skill_read before doing that kind of task."""
    words = [w for w in query.lower().split() if w]
    scored = []
    for s in _skills():
        hay = f"{s['name']} {s['description']} {s['tags']}".lower()
        score = sum(hay.count(w) + 3 * (w in s["name"].lower()) for w in words) if words else 1
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return "\n".join(f"- {s['name']}: {s['description'][:200]}" for _, s in scored[:max(1, int(limit))]) or "No skill matched."


@mcp.tool()
def skill_read(name: str) -> str:
    """Read the full SKILL.md of a W.Alter skill by name (as returned by skills_search)."""
    for s in _skills():
        if s["name"] == name or Path(s["path"]).parent.name == name:
            return Path(s["path"]).read_text(errors="replace")[:60000]
    return f"Unknown skill '{name}'. Use skills_search."


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
                  evidence_only: bool = False) -> str:
    """Unified search over everything W.Alter has observed and learned: knowledge (derived memories) AND original
    evidence (messages with W.Alter, Beeper chats, e-mails, calendar, files' extracted text), each result with its
    source and date. Full-text + semantic + rerank. evidence_only=True skips derived knowledge (raw history only).
    since/until: ISO dates. Prefer this to find *when/where/who said what*; memory_recall for synthesised facts."""
    args = ["search", query, "--limit", str(max(1, min(int(limit), 50))), "--rerank", "--cloud-safe"]
    for flag, value in (("--source", source), ("--since", since), ("--until", until)):
        if value:
            args += [flag, value]
    if evidence_only:
        args.append("--no-derived")
    return _walter_memory(*args, timeout=90)


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
    Use memory_recall for synthesised knowledge, this for the original record."""
    args = ["events", "--limit", str(max(1, min(int(limit), 200)))]
    for flag, value in (("--text", text), ("--source", source), ("--type", event_type), ("--thread", thread_id),
                        ("--since", since)):
        if value:
            args += [flag, value]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def vault_search(text: str = "", kind: str = "", source: str = "", limit: int = 20) -> str:
    """Search the Raw Vault: every raw file of the user's life that is not text (photos, screenshots, videos,
    voice notes, documents). Matches file names and derived text (OCR/transcripts/captions); empty text lists
    the newest. kind: image|screenshot|video|audio|document|archive. Returns ids for vault_get."""
    args = ["objects", "search", text, "--limit", str(int(limit))]
    if kind:
        args += ["--kind", kind]
    if source:
        args += ["--source", source]
    return _walter_memory(*args, timeout=60)


@mcp.tool()
def vault_get(object_id: str, dest_dir: str = "/tmp/walter-vault") -> str:
    """Download one Raw Vault file (by id or sha256) to a local directory on the W.Alter VM, integrity-checked.
    Returns the local path."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
    return _walter_memory("objects", "get", object_id, "--dest", dest_dir)


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
def walter_health() -> str:
    """Status of the W.Alter stack: core services, Hermes gateway, memory health score, disk."""
    out = []
    states = subprocess.run(["systemctl", "is-active", *STACK_UNITS], capture_output=True, text=True).stdout.split()
    out += [f"{u}: {s}" for u, s in zip(STACK_UNITS, states)]
    gw = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway"], capture_output=True, text=True)
    out.append(f"hermes-gateway (user): {gw.stdout.strip() or gw.stderr.strip()}")
    try:
        summary = json.loads((HERMES_HOME / "logs/memory-autopilot/latest.json").read_text())["summary"]
        out.append(f"memory autopilot: {summary.get('severity')} score={summary.get('score')} "
                   f"errors={summary.get('errors')} warnings={summary.get('warnings')}")
    except (OSError, KeyError, ValueError):
        out.append("memory autopilot: no report")
    st = os.statvfs("/")
    out.append(f"disk /: {100 - st.f_bavail * 100 // st.f_blocks}% used, {st.f_bavail * st.f_frsize >> 30} GiB free")
    return "\n".join(out)


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = int(os.environ.get("WALTER_CORE_PORT", "8931"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
