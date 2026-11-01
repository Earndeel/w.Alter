"""What the curator observes — read-only signals, no decisions."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .. import registry, store

HERMES_SKILLS = Path("/root/.hermes/skills")
READ_TOOLS = ("skill_view", "mcp__walter__skill_read", "walter_skill_read", "Skill")


def now() -> datetime:
    return datetime.now(timezone.utc)


def skill_reads(human_only: bool = False) -> list[dict]:
    """(session_id, seq, at, name, file_path) of every skill read by any runtime (arguments parsed in Python)."""
    with registry.db() as c:
        rows = c.execute(
            """select e.session_id, e.seq, e.occurred_at as at, e.text from walter_logs.events e
               join walter_logs.sessions s using (session_id)
               where e.type = 'tool/call' and e.tool = any(%s)
                 and (not %s or s.platform in ('desktop', 'tui', 'cli', 'telegram') or s.runtime <> 'hermes')
               order by e.session_id, e.seq""", (list(READ_TOOLS), human_only)).fetchall()
    out = []
    for r in rows:
        try:
            a = json.loads(r["text"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(a, dict) and (a.get("name") or a.get("skill")):
            out.append({"session_id": r["session_id"], "at": r["at"], "name": str(a.get("name") or a.get("skill")),
                        "file_path": a.get("file_path")})
    return out


def usage(aliases: dict[str, str]) -> dict[str, dict]:
    cut = now() - timedelta(days=60)
    with registry.db() as c:
        extra = [dict(r) for r in c.execute("select name, at from skills.reads")]
    out: dict[str, dict] = {}
    for r in skill_reads() + extra:
        n = aliases.get(r["name"] or "")
        if n:
            u = out.setdefault(n, {"last": None, "n": 0, "n60": 0})
            u["n"] += 1
            u["n60"] += r["at"] >= cut
            u["last"] = max(filter(None, [u["last"], r["at"]]), default=None)
    return out


def judged_needed(days: int) -> Counter:
    """How many real messages needed each skill in the last `days` days (label 2 from the judge, an opened card or a
    search miss). Bench labels are synthetic questions: since 2026-11-01 they no longer protect a skill from the
    reserve, and an old judgement no longer protects it forever."""
    with registry.db() as c:
        rows = c.execute("""select skill, count(distinct qid) n from skills.labels
                            where label = 2 and source <> 'bench' and at > now() - make_interval(days => %s)
                            group by skill""", (days,)).fetchall()
    return Counter({r["skill"]: r["n"] for r in rows})


def pinned() -> set[str]:
    try:
        d = json.loads((HERMES_SKILLS / ".usage.json").read_text())
        return {k for k, v in d.items() if isinstance(v, dict) and v.get("pinned")}
    except (OSError, json.JSONDecodeError):
        return set()


def recently_curated(days: int) -> set[str]:
    with registry.db() as c:
        rows = c.execute("""select distinct name from skills.ledger where actor = 'curator'
                            and action in ('merge', 'split', 'workflow', 'fix_refs', 'draft_new', 'draft_patch')
                            and at > now() - make_interval(days => %s) and name is not null""", (days,)).fetchall()
    return {r["name"] for r in rows}


def content_age_days(s: store.Skill) -> int:
    """Age of the content: the Hermes source file when it still exists (store import dates are all recent)."""
    src = (s.meta.get("hermes") or {}).get("path")
    p = Path(src) / "SKILL.md" if src and (Path(src) / "SKILL.md").exists() else s.skill_md
    return (now() - datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)).days


def successors() -> dict[str, str]:
    """archived skill → its direct, specific successor: Hermes' absorption chain (first hop only, never a catch-all
    umbrella with ≥ 5 absorptions) and walter-skills' own merges (archive sidecar absorbed_into)."""
    chain = {}
    led = HERMES_SKILLS / ".curator_ledger.jsonl"
    if led.exists():
        for line in led.read_text().splitlines():
            r = json.loads(line)
            tgt = (r.get("evidence") or {}).get("absorbed_into")
            if r.get("actor") == "curator" and tgt:
                chain[r["skill"]] = tgt
    fan_in = Counter(chain.values())
    out = {k: v for k, v in chain.items() if fan_in[v] < 5}
    for s in store.iter_skills(include_archived=True):
        if s.state == "archived" and s.meta.get("absorbed_into"):
            out[s.name] = s.meta["absorbed_into"]
    return out


def similarity(active: list[store.Skill], cards: dict, enc) -> np.ndarray:
    v = enc([f"{s.name.replace('-', ' ')}: {(cards.get(s.name) or {}).get('summary', '')} {s.description}" for s in active])
    sim = v @ v.T
    np.fill_diagonal(sim, 0)
    return sim


def workflow_chains(aliases: dict[str, str], active: set[str], cfg: dict) -> list[dict]:
    """Ordered skill pairs/triples that co-occur in real sessions far more than chance (lift), specific skills only."""
    seqs: dict[str, list[str]] = defaultdict(list)
    for r in skill_reads(human_only=True):
        n = aliases.get(r["name"] or "")
        if not r["file_path"] and n in active and (not seqs[r["session_id"]] or seqs[r["session_id"]][-1] != n):
            seqs[r["session_id"]].append(n)
    n_sess = len(seqs) or 1
    df = Counter(n for s in seqs.values() for n in set(s))
    generic = {n for n, c in df.items() if c / n_sess > cfg["generic_session_share"]}
    pair = Counter()
    for s in seqs.values():
        spec, seen = [n for n in s if n not in generic], set()
        for i, a in enumerate(spec):
            for b in spec[i + 1:i + 6]:
                if a != b and (a, b) not in seen:
                    seen.add((a, b))
                    pair[(a, b)] += 1
    strong = {}
    for (a, b), c in pair.items():
        lift = c * n_sess / (df[a] * df[b])
        if c >= cfg["workflow_min_sessions"] and lift >= cfg["workflow_min_lift"]:
            strong[(a, b)] = {"steps": [a, b], "sessions": c, "lift": round(lift, 1)}
    chains = []
    for (a, b), o in strong.items():
        nxt = [(c2, strong[(b2, c2)]) for (b2, c2) in strong if b2 == b and c2 not in (a, b)]
        if nxt:
            c2, o2 = max(nxt, key=lambda x: x[1]["sessions"])
            chains.append({"steps": [a, b, c2], "sessions": min(o["sessions"], o2["sessions"]),
                           "lift": min(o["lift"], o2["lift"])})
    picked, used = [], set()
    for c in sorted(chains + list(strong.values()), key=lambda x: (-len(x["steps"]), -x["sessions"])):
        if not set(c["steps"]) & used:
            picked.append(c)
            used |= set(c["steps"])
    return picked
