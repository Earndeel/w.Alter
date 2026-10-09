"""Build the skill-retrieval benchmark from walter_logs.

A case = one user message + the skills the agent actually opened (skill_view without file_path) before the next
user message, in Hermes sessions with a human on the other end. The corpus is every skill on disk, active and
archived (the library walter-skills will manage); `gold_active` maps each gold through the curator's
absorbed_into chain onto today's active Hermes library.

Output (0600, contains private messages, never committed): data/cases.jsonl, data/corpus.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/opt/walter-memory")
from walter_memory.db import connect  # noqa: E402

SKILLS = Path("/root/.hermes/skills")
LEDGER = SKILLS / ".curator_ledger.jsonl"
OUT = Path(__file__).parent / "data"
HUMAN_PLATFORMS = ("desktop", "tui", "cli", "telegram", "voice-router")
TEST_SPLIT_FROM = "2026-09-20"  # cases on/after this date = test; before = dev (the learner may use dev only)


def frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    out = {}
    if not m:
        return out
    lines = m.group(1).splitlines()
    for i, line in enumerate(lines):
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            v = v.strip()
            if v in (">", "|", ">-", "|-"):  # block scalar
                block = []
                for nxt in lines[i + 1:]:
                    if nxt.startswith((" ", "\t")):
                        block.append(nxt.strip())
                    else:
                        break
                v = " ".join(block)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def corpus() -> dict[str, dict]:
    items = {}
    for md in SKILLS.rglob("SKILL.md"):
        rel = md.relative_to(SKILLS).parts
        if rel[0].startswith(".") and rel[0] != ".archive":
            continue
        archived = rel[0] == ".archive"
        if archived and len(rel) != 3:  # .archive/<name>/SKILL.md only (skip nested copies)
            continue
        text = md.read_text(errors="replace")
        fm = frontmatter(text[:6000])
        name = md.parent.name
        if name in items and not archived:
            pass
        elif name in items:
            continue
        items[name] = {"name": name, "fm_name": fm.get("name") or name, "description": fm.get("description", ""),
                       "tags": fm.get("tags", ""), "category": "" if archived else "/".join(rel[:-2]),
                       "archived": archived, "path": str(md), "body": text}
    return items


def absorbed_into() -> dict[str, str]:
    m = {}
    for line in LEDGER.read_text().splitlines():
        r = json.loads(line)
        tgt = (r.get("evidence") or {}).get("absorbed_into")
        if r.get("actor") == "curator" and tgt:
            m[r["skill"]] = tgt
    return m


def resolve(name: str, chain: dict[str, str]) -> str:
    seen = set()
    while name in chain and name not in seen:
        seen.add(name)
        name = chain[name]
    return name


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    os.chmod(OUT, 0o700)
    skills = corpus()
    by_alias = {s["name"]: s["name"] for s in skills.values()} | {s["fm_name"]: s["name"] for s in skills.values()}
    chain = absorbed_into()
    active = {n for n, s in skills.items() if not s["archived"]}

    conn = connect()
    rows = conn.execute(
        """select e.session_id, e.seq, e.type, e.occurred_at, e.tool, e.text, e.privacy_class, s.platform, s.profile
           from walter_logs.events e join walter_logs.sessions s using (session_id)
           where s.runtime = 'hermes' and s.platform = any(%s)
             and (e.type in ('user/message', 'assistant/message') or (e.type = 'tool/call' and e.tool = 'skill_view'))
           order by e.session_id, e.seq""", (list(HUMAN_PLATFORMS),)).fetchall()

    cases, cur = [], None
    prev_user, prev_assistant, prev_session = "", "", None
    turn, opened = 0, {}  # skills opened earlier in the session -> turn index of the last opening
    for r in rows:
        if r["session_id"] != prev_session:
            prev_user, prev_assistant, prev_session = "", "", r["session_id"]
            turn, opened = 0, {}
        if r["type"] == "assistant/message":
            if r["text"]:
                prev_assistant = r["text"].strip()
            continue
        if r["type"] == "user/message":
            if cur is not None and cur["session_id"] == r["session_id"]:
                prev_user = cur["query"]
            cur = {"session_id": r["session_id"], "seq": r["seq"], "at": r["occurred_at"].isoformat(),
                   "platform": r["platform"], "profile": r["profile"], "privacy_class": r["privacy_class"],
                   "query": (r["text"] or "").strip(), "gold": [],
                   "context": {"prev_user": prev_user[-400:], "prev_assistant": prev_assistant[-600:]},
                   "session_skills": {n: turn - t for n, t in opened.items()}}
            turn += 1
            prev_assistant = ""
            cases.append(cur)
            continue
        if cur is None or cur["session_id"] != r["session_id"]:
            continue
        try:
            args = json.loads(r["text"] or "{}")
        except json.JSONDecodeError:
            continue
        if args.get("file_path"):
            continue
        name = by_alias.get(str(args.get("name", "")).strip())
        if name and name not in cur["gold"]:
            cur["gold"].append(name)
        if name:
            opened[name] = turn

    seen, kept, stats = set(), [], {"messages": len(cases)}
    for c in cases:
        q = c["query"]
        if not c["gold"]:
            stats["no_skill"] = stats.get("no_skill", 0) + 1
            continue
        if q.startswith("/") or len(q.split()) < 3:
            stats["slash_or_short"] = stats.get("slash_or_short", 0) + 1
            continue
        if q.startswith(("[System", "[SYSTEM", "<system", "[Context", "[CONTEXT")):
            stats["system_injected"] = stats.get("system_injected", 0) + 1
            continue
        key = hashlib.sha1(re.sub(r"\s+", " ", q.lower())[:500].encode()).hexdigest()
        if key in seen:
            stats["duplicate"] = stats.get("duplicate", 0) + 1
            continue
        seen.add(key)
        c["query"] = q[:1500]
        c["id"] = key[:12]
        c["split"] = "test" if c["at"][:10] >= TEST_SPLIT_FROM else "dev"
        c["gold_active"] = sorted({resolve(g, chain) for g in c["gold"]} & active)
        lower = q.lower()
        c["names_skill"] = any(g.lower() in lower or g.replace("-", " ").lower() in lower for g in c["gold"])
        kept.append(c)
    stats["kept"] = len(kept)
    stats["dev"] = sum(c["split"] == "dev" for c in kept)
    stats["test"] = sum(c["split"] == "test" for c in kept)
    stats["names_skill"] = sum(c["names_skill"] for c in kept)
    stats["local_only"] = sum(c["privacy_class"] == "local_only" for c in kept)
    stats["corpus"] = len(skills)
    stats["corpus_active"] = len(active)

    with open(OUT / "cases.jsonl", "w") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(OUT / "corpus.jsonl", "w") as f:
        for s in skills.values():
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    for p in OUT.iterdir():
        os.chmod(p, 0o600)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
