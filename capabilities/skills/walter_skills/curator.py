"""Walter curator — shadow mode (P10.6, first brick): deterministic checks + archive/merge *proposals*, no mutation.

Reports to reports/curator-<date>.md and one skills.ledger row. The LLM editor/judge postes (merges, rewrites) come
later and will act only through git commits validated by the benchmark (PLAN P10.2 guard-rails).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import numpy as np

from . import cards as cards_mod
from . import store

sys.path.insert(0, "/opt/walter-memory")
from walter_memory.db import connection  # noqa: E402

REPORTS = store.ROOT / "reports"
RETIRED = {  # services retired on the VM (CLAUDE.md, DECISIONS 2026-10-01)
    "Qdrant / pg-qdrant-sync": r"\bqdrant\b|pg-qdrant",
    "hybrid-search / write-worker / write-bridge": r"hybrid[-_]search|write[-_]worker|write[-_]bridge",
    "dream-cycle": r"dream[-_]cycle",
    "jarvis-memory-gateway": r"jarvis[-_]memory[-_]gateway",
    "web call (call.walter-ai.cloud)": r"call\.walter-ai\.cloud|hermes-voice-call",
    "walter-ops remote admin": r"walter-ops\b",
}
MAX_CHARS = 24000
DUP_COSINE = 0.93
UNUSED_DAYS = 60


def _usage(days: int) -> dict[str, int]:
    with connection() as conn:
        rows = conn.execute(
            """select coalesce((text::jsonb)->>'name', '') as name, count(*) as n from walter_logs.events
               where type = 'tool/call' and tool in ('skill_view', 'mcp__walter__skill_read')
                 and occurred_at > now() - make_interval(days => %s) group by 1""", (days,)).fetchall()
        reads = conn.execute(
            """select name, count(*) as n from skills.reads where at > now() - make_interval(days => %s)
               group by 1""", (days,)).fetchall()
    out: dict[str, int] = {}
    for r in list(rows) + list(reads):
        out[r["name"]] = out.get(r["name"], 0) + r["n"]
    return out


def run(write: bool = True) -> dict:
    active = list(store.iter_skills())
    everything = list(store.iter_skills(include_archived=True, include_drafts=True))
    archived = {s.name for s in everything if s.state == "archived"}
    known = {s.name for s in everything}
    findings: dict[str, list] = {k: [] for k in ("broken_refs", "retired", "oversized", "duplicates", "unused",
                                                 "stale_cards", "hermes_drafts")}
    for s in active:
        text = "\n".join(p.read_text(errors="replace") for p in s.path.rglob("*.md"))
        refs = {n for n in archived if len(n) > 6 and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text)}
        if refs:
            findings["broken_refs"].append({"skill": s.name, "archived_refs": sorted(refs)})
        hits = [label for label, rx in RETIRED.items() if re.search(rx, text, re.I)]
        if hits:
            findings["retired"].append({"skill": s.name, "mentions": hits})
        if len(s.body) > MAX_CHARS:
            findings["oversized"].append({"skill": s.name, "chars": len(s.body)})
        c = cards_mod.load(s.name)
        if not c or c.get("sha") != store.tree_hash(s.path):
            findings["stale_cards"].append(s.name)
        pending = (s.meta.get("hermes") or {}).get("pending_sha")
        if pending:
            findings["hermes_drafts"].append({"skill": s.name, "draft": f"drafts/{s.name}@hermes-{pending[:8]}"})
    # near-duplicates on card summaries + descriptions (local embeddings)
    from .retrieve import Encoder
    enc = Encoder("minishlab/potion-multilingual-128M")
    texts = [f"{s.name.replace('-', ' ')}: {(cards_mod.load(s.name) or {}).get('summary', '')} {s.description}"
             for s in active]
    v = enc(texts)
    sim = v @ v.T
    np.fill_diagonal(sim, 0)
    for i, j in zip(*np.where(np.triu(sim) >= DUP_COSINE)):
        findings["duplicates"].append({"a": active[i].name, "b": active[j].name, "cosine": round(float(sim[i, j]), 3)})
    used = _usage(UNUSED_DAYS)
    now = datetime.now(timezone.utc)
    for s in active:
        if s.meta.get("owner") == "upstream" or used.get(s.name):
            continue
        imported = s.meta.get("imported_at")
        age = (now - datetime.fromisoformat(imported)).days if imported else 999
        findings["unused"].append({"skill": s.name, "origin": s.meta.get("origin"), "days_in_store": age})
    summary = {k: len(v) for k, v in findings.items()}
    if write:
        REPORTS.mkdir(exist_ok=True)
        day = now.strftime("%Y-%m-%d")
        lines = [f"# walter-skills curator report — {day} (shadow: nothing was changed)", "",
                 f"Active skills: {len(active)} · archived: {len(archived)} · drafts: "
                 f"{sum(s.state == 'draft' for s in everything)}", "", "| check | count |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in summary.items()]
        titles = {"broken_refs": "References to archived skills", "retired": "Mentions of retired services",
                  "oversized": f"SKILL.md over {MAX_CHARS} chars (distil into references/)",
                  "duplicates": f"Probable duplicates (cosine >= {DUP_COSINE}) — merge candidates for skills.editor",
                  "unused": f"No read by any runtime in {UNUSED_DAYS} days — archive candidates "
                            "(not proposed before 60 days in the store)",
                  "stale_cards": "Trigger cards out of date", "hermes_drafts": "Hermes changed a skill we also edited"}
        for k, items in findings.items():
            lines += ["", f"## {titles[k]} ({len(items)})", ""]
            lines += [f"- {json.dumps(x, ensure_ascii=False)}" for x in items[:80]] or ["- none"]
        (REPORTS / f"curator-{day}.md").write_text("\n".join(lines) + "\n")
        with connection() as conn:
            conn.execute("insert into skills.ledger (actor, action, evidence) values (%s, %s, %s)",
                         ("curator.shadow", "report", json.dumps(summary)))
    return {"summary": summary, "findings": findings}
