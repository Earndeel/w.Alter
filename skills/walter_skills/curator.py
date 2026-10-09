"""Walter curator (P10.6) — keeps the skill library clean, small and findable, without the Hermes failure modes.

Nightly run = signals → proposals → (shadow) a git branch + report, or (active) commits on master + ledger.

  archive   dead skills (no read by any runtime for N days, never judged "the one to load", not pinned, not upstream)
            → archive/ (recoverable; nothing is ever deleted automatically)
  fix_refs  references to archived skills → their active successor (Hermes curator absorption chain)
  split     SKILL.md over 24k chars → always-on rules + references/ (editor)
  merge     near-duplicates → one skill (editor), accepted only if: judge OK, lossless (every command, path, URL,
            port, script kept or explicitly dropped), retrieval of the judged cases that wanted either skill not worse
  workflow  frequent, surprising sequences of specific skills in real sessions → a `type: workflow` skill that
            ORCHESTRATES the sub-skills (they stay intact — composition, never absorption)
  flags     retired services, stale cards, Hermes conflicts (report only)
Guard-rails: ≤ max_merges / max_workflows per run; a skill the curator created or changed < 30 days ago is never
absorbed (no cascades); upstream skills (bundled/hub) are read-only; every change is a commit with its evidence.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import cards as cards_mod
from . import models, store

sys.path.insert(0, "/opt/walter-memory")
from walter_memory.db import connection  # noqa: E402

REPORTS = store.ROOT / "reports"
CONFIG = store.ROOT / "config" / "curator.json"
WORKTREES = store.ROOT / ".worktrees"
HERMES_SKILLS = Path("/root/.hermes/skills")
DEFAULTS = {"mode": "shadow", "shadow_until": "2026-10-23", "archive_after_days": 60, "max_merges": 5,
            "max_workflows": 3, "max_splits": 3, "dup_cosine": 0.80, "workflow_max_step_cosine": 0.75, "max_chars": 24000, "cooldown_days": 30,
            "generic_session_share": 0.08, "workflow_min_sessions": 5, "workflow_min_lift": 4.0}
RETIRED = {
    "Qdrant / pg-qdrant-sync": r"\bqdrant\b|pg-qdrant",
    "hybrid-search / write-worker / write-bridge": r"hybrid[-_]search|write[-_]worker|write[-_]bridge",
    "dream-cycle": r"dream[-_]cycle",
    "jarvis-memory-gateway": r"jarvis[-_]memory[-_]gateway",
    "web call (call.walter-ai.cloud)": r"call\.walter-ai\.cloud|hermes-voice-call",
    "walter-ops remote admin": r"walter-ops\b",
}


def config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    return cfg


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────────── signals ─────────────────────────────

def _aliases() -> dict[str, str]:
    out = {}
    for s in store.iter_skills(include_archived=True):
        out[s.name] = s.name
        fm = store.frontmatter(s.body[:6000]).get("name")
        if fm:
            out.setdefault(fm, s.name)
    return out


def _skill_reads(conn, human_only: bool = False) -> list[dict]:
    """(session_id, seq, at, name, file_path) of every skill read by any runtime; arguments parsed here, not in SQL."""
    rows = conn.execute(
        """select e.session_id, e.seq, e.occurred_at as at, e.text from walter_logs.events e
           join walter_logs.sessions s using (session_id)
           where e.type = 'tool/call' and e.tool in ('skill_view', 'mcp__walter__skill_read', 'Skill')
             and (not %s or s.platform in ('desktop', 'tui', 'cli', 'telegram') or s.runtime <> 'hermes')
           order by e.session_id, e.seq""", (human_only,)).fetchall()
    out = []
    for r in rows:
        try:
            a = json.loads(r["text"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(a, dict) and (a.get("name") or a.get("skill")):
            out.append({"session_id": r["session_id"], "seq": r["seq"], "at": r["at"],
                        "name": str(a.get("name") or a.get("skill")), "file_path": a.get("file_path")})
    return out


def usage(al: dict[str, str]) -> dict[str, dict]:
    """Reads of each skill by any runtime (walter_logs + walter-skills reads): last read, reads in 60 days."""
    cut = _now() - timedelta(days=60)
    with connection() as conn:
        reads = _skill_reads(conn) + [dict(r) for r in conn.execute("select name, at from skills.reads").fetchall()]
    out: dict[str, dict] = {}
    for r in reads:
        n = al.get(r["name"] or "")
        if not n:
            continue
        u = out.setdefault(n, {"last": None, "n": 0, "n60": 0})
        u["n"] += 1
        u["n60"] += r["at"] >= cut
        u["last"] = max(filter(None, [u["last"], r["at"]]), default=None)
    return out


def judged_relevant() -> Counter:
    c = Counter()
    jd = store.ROOT / "index" / "judged"
    for f in sorted(jd.glob("*.jsonl")) if jd.exists() else []:
        for line in open(f):
            if line.strip():
                for n, v in json.loads(line)["labels"].items():
                    if v == 2:
                        c[n] += 1
    return c


def pinned() -> set[str]:
    p = HERMES_SKILLS / ".usage.json"
    try:
        return {k for k, v in json.loads(p.read_text()).items() if isinstance(v, dict) and v.get("pinned")}
    except (OSError, json.JSONDecodeError):
        return set()


def recently_curated(days: int) -> set[str]:
    with connection() as conn:
        rows = conn.execute("""select distinct name from skills.ledger where actor like 'curator%%'
                               and action in ('merge', 'split', 'workflow', 'fix_refs')
                               and at > now() - make_interval(days => %s) and name is not null""", (days,)).fetchall()
    return {r["name"] for r in rows}


def last_modified(s: store.Skill) -> datetime:
    """Content age: the Hermes source file if it still exists (git import dates are all 2026-10-09), else the store."""
    src = (s.meta.get("hermes") or {}).get("path")
    p = Path(src) / "SKILL.md" if src and (Path(src) / "SKILL.md").exists() else s.skill_md
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)


def absorbed_into() -> dict[str, str]:
    led = HERMES_SKILLS / ".curator_ledger.jsonl"
    m = {}
    if led.exists():
        for line in led.read_text().splitlines():
            r = json.loads(line)
            tgt = (r.get("evidence") or {}).get("absorbed_into")
            if r.get("actor") == "curator" and tgt:
                m[r["skill"]] = tgt
    return m


def successor(name: str, chain: dict[str, str], active: set[str]) -> str | None:
    """Direct, specific successor only: the skill it was absorbed into, if active and not a catch-all umbrella
    (Hermes' cascade ended in `evidence-and-execution-operations`, which absorbed everything)."""
    tgt = chain.get(name)
    fan_in = Counter(chain.values())
    return tgt if tgt in active and fan_in[tgt] < 5 else None


# ───────────────────────────── proposals ─────────────────────────────

def propose(cfg: dict) -> dict:
    active = list(store.iter_skills())
    everything = list(store.iter_skills(include_archived=True, include_drafts=True))
    active_names = {s.name for s in active}
    archived = {s.name for s in everything if s.state == "archived"}
    al = _aliases()
    use = usage(al)
    judged = judged_relevant()
    pins = pinned()
    cool = recently_curated(cfg["cooldown_days"])
    chain = absorbed_into()
    now = _now()
    P: dict[str, list] = defaultdict(list)

    for s in active:
        u = use.get(s.name, {})
        texts = {p: p.read_text(errors="replace") for p in s.path.rglob("*.md")}
        blob = "\n".join(texts.values())
        # archive dead skills
        last = u.get("last")
        idle = (now - last).days if last else None
        age = (now - last_modified(s)).days
        if (s.name not in pins and not judged.get(s.name)
                and (idle is None or idle >= cfg["archive_after_days"]) and age >= cfg["archive_after_days"]):
            P["archive"].append({"skill": s.name, "owner": s.meta.get("owner"), "idle_days": idle,
                                 "content_age_days": age, "reads_total": u.get("n", 0),
                                 "reason": "never read by any agent" if idle is None else f"not read for {idle} days"})
        # broken references → successor
        refs = {n for n in archived if len(n) > 6 and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", blob)}
        if refs and s.meta.get("owner") != "upstream":
            fix = {r: successor(r, chain, active_names) for r in sorted(refs)}
            P["fix_refs"].append({"skill": s.name, "replace": {k: v for k, v in fix.items() if v},
                                  "unresolved": [k for k, v in fix.items() if not v]})
        hits = [label for label, rx in RETIRED.items() if re.search(rx, blob, re.I)]
        if hits:
            P["retired"].append({"skill": s.name, "mentions": hits})
        if len(s.body) > cfg["max_chars"] and s.meta.get("owner") != "upstream":
            P["split"].append({"skill": s.name, "chars": len(s.body)})
        c = cards_mod.load(s.name)
        if not c or c.get("sha") != store.tree_hash(s.path):
            P["stale_cards"].append(s.name)
        pending = (s.meta.get("hermes") or {}).get("pending_sha")
        if pending:
            P["hermes_drafts"].append({"skill": s.name, "draft": f"drafts/{s.name}@hermes-{pending[:8]}"})
    P["split"] = sorted(P["split"], key=lambda x: -x["chars"])[:cfg["max_splits"]]

    # near-duplicates (local embeddings over name + card summary + description)
    from .retrieve import Encoder
    enc = Encoder("minishlab/potion-multilingual-128M")
    v = enc([f"{s.name.replace('-', ' ')}: {(cards_mod.load(s.name) or {}).get('summary', '')} {s.description}"
             for s in active])
    sim = v @ v.T
    np.fill_diagonal(sim, 0)
    pairs = []
    for i, j in zip(*np.where(np.triu(sim) >= cfg["dup_cosine"])):
        a, b = active[i], active[j]
        if "upstream" in (a.meta.get("owner"), b.meta.get("owner")) or {a.name, b.name} & (cool | pins):
            continue
        pairs.append({"a": a.name, "b": b.name, "cosine": round(float(sim[i, j]), 3),
                      "reads_60d": [use.get(a.name, {}).get("n60", 0), use.get(b.name, {}).get("n60", 0)]})
    P["merge"] = sorted(pairs, key=lambda x: -x["cosine"])[:cfg["max_merges"]]
    pos = {s.name: i for i, s in enumerate(active)}
    wf = []
    for w in mine_workflows(cfg, al, active_names):
        ix = [pos[n] for n in w["steps"]]
        top = max(float(sim[i, j]) for i in ix for j in ix if i != j)
        (wf if top < cfg["workflow_max_step_cosine"] else P["variants"]).append(w | {"max_step_cosine": round(top, 3)})
    P["workflow"] = wf[:cfg["max_workflows"]]
    return dict(P)


def mine_workflows(cfg: dict, al: dict[str, str], active: set[str]) -> list[dict]:
    """Ordered skill pairs/triples that co-occur in sessions far more than chance (lift), on specific skills only."""
    with connection() as conn:
        rows = [r for r in _skill_reads(conn, human_only=True) if not r["file_path"]]
    seqs: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        n = al.get(r["name"] or "")
        if n in active and (not seqs[r["session_id"]] or seqs[r["session_id"]][-1] != n):
            seqs[r["session_id"]].append(n)
    n_sess = len(seqs) or 1
    df = Counter(n for s in seqs.values() for n in set(s))
    generic = {n for n, c in df.items() if c / n_sess > cfg["generic_session_share"]}
    pair = Counter()
    for s in seqs.values():
        spec = [n for n in s if n not in generic]
        seen = set()
        for i, a in enumerate(spec):
            for b in spec[i + 1:i + 6]:
                if a != b and (a, b) not in seen:
                    seen.add((a, b))
                    pair[(a, b)] += 1
    out = []
    for (a, b), c in pair.items():
        if c < cfg["workflow_min_sessions"]:
            continue
        lift = c * n_sess / (df[a] * df[b])
        if lift >= cfg["workflow_min_lift"]:
            out.append({"steps": [a, b], "sessions": c, "lift": round(lift, 1)})
    # extend to triples when b→c is also strong
    strong = {(o["steps"][0], o["steps"][1]): o for o in out}
    chains = []
    for (a, b), o in strong.items():
        nxt = [(c2, strong[(b, c2)]) for (b2, c2) in strong if b2 == b and c2 not in (a, b)]
        if nxt:
            c2, o2 = max(nxt, key=lambda x: x[1]["sessions"])
            chains.append({"steps": [a, b, c2], "sessions": min(o["sessions"], o2["sessions"]),
                           "lift": round(min(o["lift"], o2["lift"]), 1)})
    cands = sorted(chains + out, key=lambda x: (-len(x["steps"]), -x["sessions"]))
    picked, used = [], set()
    for c in cands:  # avoid proposing overlapping workflows in the same run
        if not set(c["steps"]) & used:
            picked.append(c)
            used |= set(c["steps"])
    return picked


# ───────────────────────────── checks ─────────────────────────────

ATOM_RX = [r"`([^`\n]{3,120})`", r"(?<![\w.])(/(?:opt|root|etc|var|usr|home|tmp)/[\w./~@-]+)", r"(https?://[^\s)>\]\"'`]+)",
           r"\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{2,5})\b", r"\b([A-Z][A-Z0-9_]{3,}=)"]


def atoms(text: str) -> set[str]:
    out = set()
    for rx in ATOM_RX:
        out |= {m.strip() for m in re.findall(rx, text) if m.strip()}
    for block in re.findall(r"```[\w-]*\n(.*?)```", text, re.S):
        out |= {line.strip() for line in block.splitlines() if len(line.strip()) > 8}
    return out


def lossless(originals: list[str], result: str, dropped: list[dict]) -> dict:
    need = set().union(*(atoms(t) for t in originals)) if originals else set()
    dropped_txt = " ".join(json.dumps(d, ensure_ascii=False) for d in dropped)
    missing = sorted(a for a in need if a not in result and a not in dropped_txt)
    return {"atoms": len(need), "missing": missing[:40], "ok": not missing}


def retrieval_check(names_before: list[str], target: str, new_desc: str, new_card: dict, root: Path) -> dict:
    """Judged cases that wanted any of `names_before`: after the change (originals replaced by `target` with its new
    card), is `target` in the top 15 at least as often as one of the originals was before?"""
    from . import engine, history
    from .retrieve import Index
    jd = engine.judged_labels()
    al = engine.aliases(engine.corpus())
    cases = {c["qid"]: c for c in history.cases(al)}
    want = [cases[q] for q, lab in jd.items() if q in cases and any(lab.get(n) == 2 for n in names_before)]
    if not want:
        return {"cases": 0, "ok": True, "note": "no judged case"}
    live = engine.load_engine()
    before = sum(any(r["name"] in names_before for r in live.search(c["query"], c["ctx"], k=15)) for c in want)
    skills = []
    for s in store.iter_skills(root=root):
        if s.name in names_before and s.name != target:
            continue
        skills.append({"name": s.name, "description": new_desc if s.name == target else s.description,
                       "tags": s.tags, "domain": s.domain, "state": s.state, "path": str(s.path)})
    cards = {s["name"]: new_card if s["name"] == target else (cards_mod.load(s["name"]) or {}) for s in skills}
    idx = Index(skills, cards, live.enc)
    idx.weights, idx.bias, idx.model = live.idx.weights, live.idx.bias, live.idx.model
    after = 0
    for c in want:
        sc = idx.score(idx.features(c["query"], c["ctx"]))
        after += target in [idx.names[i] for i in np.argsort(-sc)[:15]]
    return {"cases": len(want), "before_in_top15": before, "after_in_top15": after, "ok": after >= before}


def card_for_result(target: store.Skill, res: dict) -> tuple[dict | None, str]:
    """Trigger card of an edited skill, generated from the edited files in a scratch directory."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="walter-card-") as d:
        tmp = Path(d) / target.name
        shutil.copytree(target.path, tmp)
        _write_skill_files(tmp, res)
        s = store._load(tmp, "active", target.domain)
        try:
            return cards_mod.generate(s), s.description
        except Exception:
            return None, s.description


# ───────────────────────────── editor actions ─────────────────────────────

def _skill_bundle(s: store.Skill, limit: int = 60000) -> str:
    parts = [f"=== {s.name}/SKILL.md ===\n{s.body}"]
    for p in sorted(s.path.rglob("*")):
        if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and "__pycache__" not in p.parts:
            rel = p.relative_to(s.path)
            txt = p.read_text(errors="replace") if p.suffix in (".md", ".txt", ".json", ".yaml", ".yml") else \
                f"(file kept as-is: {p.stat().st_size} bytes)"
            parts.append(f"=== {s.name}/{rel} ===\n{txt[:12000]}")
    return "\n\n".join(parts)[:limit]


EDIT_RULES = """Rules: keep every command, path, URL, port, env variable name, model id and script reference that still
applies — or list it in "dropped" with a one-line reason. Distil narration into imperative rules (one clause of why).
SKILL.md keeps the always-on rules (target < 12000 chars); topic depth goes to references/*.md files. Frontmatter:
name, description (one line, starts with "Use when", the trigger class), optional metadata. Write in the language of
the source (French or English). Return JSON only:
{"skill_md": "<full SKILL.md>", "references": {"references/<file>.md": "<content>", ...}, "dropped": [{"item": "...", "reason": "..."}]}"""


def edit_merge(a: store.Skill, b: store.Skill) -> dict | None:
    prompt = (f"You maintain W.Alter's skill library (procedures an AI agent loads before acting). These two skills look "
              f"similar. If they do NOT cover the same job (e.g. two different providers or tools), answer only "
              f'{{"skip": "<reason>"}}. Otherwise merge them into ONE skill named `{a.name}` (the other, `{b.name}`, '
              f"will be archived), keeping both specific procedures.\n{EDIT_RULES}\n\n{_skill_bundle(a)}\n\n{_skill_bundle(b)}")
    return models.parse_json(models.editor(prompt))


def edit_split(s: store.Skill) -> dict | None:
    prompt = (f"You maintain W.Alter's skill library. `{s.name}` is too long ({len(s.body)} chars): every load costs "
              f"the agent that many tokens. Restructure it: SKILL.md = the always-on rules and the map of references; "
              f"move topic depth into references/ files. Do not lose anything.\n{EDIT_RULES}\n\n{_skill_bundle(s)}")
    return models.parse_json(models.editor(prompt))


def edit_workflow(steps: list[store.Skill], evidence: dict) -> dict | None:
    lines = "\n".join(f"- {s.name}: {(cards_mod.load(s.name) or {}).get('summary') or s.description}" for s in steps)
    prompt = (
        "You maintain W.Alter's skill library. Real sessions repeatedly chain these skills in this order "
        f"({evidence['sessions']} sessions, lift {evidence['lift']}):\n{lines}\n\n"
        "Write ONE workflow skill that orchestrates them. It must NOT copy their content: it says when the whole "
        "chain applies, the order, what each step must produce for the next (hand-off), the checks between steps, "
        "and tells the agent to load each sub-skill with skill_read(<name>) at that step. Frontmatter must include "
        "`type: workflow` and `requires: [<sub-skill names>]`. Return JSON only: "
        '{"name": "<kebab-case-workflow-name>", "skill_md": "<full SKILL.md>"}\n\nSub-skills (for reference):\n\n'
        + "\n\n".join(_skill_bundle(s, 15000) for s in steps))
    return models.parse_json(models.editor(prompt))


def review(kind: str, before: str, after: str) -> dict | None:
    prompt = (f"You are the reviewer (poste skills.judge) of an automated {kind} in W.Alter's skill library. Compare "
              "BEFORE and AFTER. Reject if any still-valid procedure, command, path, credential *location*, model id or "
              "warning was lost or altered, if facts were invented, or if the result is less usable by an agent. "
              'Return JSON only: {"ok": true|false, "issues": ["..."]}\n\n'
              f"BEFORE:\n{before[:70000]}\n\nAFTER:\n{after[:70000]}")
    return models.judge(prompt)


# ───────────────────────────── apply ─────────────────────────────

def _worktree(day: str) -> Path:
    WORKTREES.mkdir(exist_ok=True)
    wt = WORKTREES / f"curator-{day}"
    if wt.exists():
        subprocess.run(["git", "-C", str(store.ROOT), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(store.ROOT), "worktree", "add", "-B", f"curator/{day}", str(wt), "HEAD"],
                   capture_output=True, check=True)
    for d in ("index/cards",):  # untracked-in-branch helpers are tracked anyway; nothing to copy
        (wt / d).mkdir(parents=True, exist_ok=True)
    return wt


def _ledger(action: str, name: str | None, commit: str | None, evidence: dict) -> None:
    with connection() as conn:
        conn.execute("insert into skills.ledger (actor, action, name, git_commit, evidence) values (%s,%s,%s,%s,%s)",
                     ("curator", action, name, commit, json.dumps(evidence, ensure_ascii=False, default=str)))


def _write_skill_files(dst: Path, result: dict) -> None:
    (dst / "SKILL.md").write_text(result["skill_md"].rstrip() + "\n")
    for rel, content in (result.get("references") or {}).items():
        rel = rel.lstrip("/")
        if not rel.startswith("references/") or ".." in rel:
            continue
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content.rstrip() + "\n")


def _archive_in(root: Path, s: store.Skill, reason: str, extra: dict | None = None) -> None:
    src = s.path  # already under `root` (skills listed with store.iter_skills(root=root))
    dst = root / "archive" / s.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(src), str(dst))
    meta = store.read_sidecar(dst) | {"domain": s.domain, "archived_at": _now().isoformat(timespec="seconds"),
                                      "archived_reason": reason} | (extra or {})
    store.write_sidecar(dst, meta)


def run(apply: bool | None = None, use_models: bool = True) -> dict:
    cfg = config()
    day = _now().strftime("%Y-%m-%d")
    mode = "active" if (apply if apply is not None else (cfg["mode"] == "active" and day >= cfg["shadow_until"])) \
        else "shadow"
    P = propose(cfg)
    root = store.ROOT if mode == "active" else _worktree(day)
    by = {s.name: s for s in store.iter_skills(root=root)}
    done: dict[str, list] = defaultdict(list)

    # 1. archive dead skills
    for a in P.get("archive", []):
        s = by.get(a["skill"])
        if s:
            _archive_in(root, s, a["reason"], {"idle_days": a["idle_days"]})
            c = store.commit(f"curator: archive {s.name} ({a['reason']}; never judged needed)", root=root,
                             author="walter-curator")
            done["archive"].append(a | {"commit": c})
            if mode == "active":
                _ledger("archive", s.name, c, a)
    by = {s.name: s for s in store.iter_skills(root=root)}

    # 2. references to archived skills → successor
    for f in P.get("fix_refs", []):
        s = by.get(f["skill"])
        if not s or not f["replace"]:
            continue
        for p in s.path.rglob("*.md"):
            t = p.read_text(errors="replace")
            new = t
            for old, succ in f["replace"].items():
                new = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", f"{succ}", new)
            if new != t:
                p.write_text(new)
        c = store.commit(f"curator: {s.name}: references to archived skills → successors {f['replace']}", root=root,
                         author="walter-curator")
        if c:
            done["fix_refs"].append(f | {"commit": c})
            if mode == "active":
                _ledger("fix_refs", s.name, c, f)

    # 3-5. editor actions (need the Codex session + the judge)
    editor_ok = use_models and models.codex_ready()
    if editor_ok:
        for m in P.get("merge", []):
            a, b = by.get(m["a"]), by.get(m["b"])
            if not (a and b):
                continue
            keep, gone = (a, b) if m["reads_60d"][0] >= m["reads_60d"][1] else (b, a)
            res = edit_merge(keep, gone)
            verdict = _validate("merge", [keep, gone], keep, res, root)
            done["merge" if verdict["accepted"] else "merge_rejected"].append(
                m | {k: v for k, v in verdict.items() if k != "card"})
            if verdict["accepted"]:
                _write_skill_files(keep.path, res)
                _archive_in(root, gone, f"merged into {keep.name}", {"absorbed_into": keep.name})
                card = verdict.pop("card")
                card["sha"] = store.tree_hash(keep.path)
                (root / "index" / "cards" / f"{keep.name}.json").write_text(json.dumps(card, ensure_ascii=False, indent=1))
                c = store.commit(f"curator: merge {gone.name} into {keep.name} (judge OK, lossless, retrieval "
                                 f"{verdict['retrieval']})", root=root, author="walter-curator",
                                 paths=["skills", "archive", "index/cards"])
                if mode == "active":
                    _ledger("merge", keep.name, c, m | verdict)
                by = {s.name: s for s in store.iter_skills(root=root)}
        for sp in P.get("split", []):
            s = by.get(sp["skill"])
            if not s:
                continue
            res = edit_split(s)
            verdict = _validate("split", [s], s, res, root)
            done["split" if verdict["accepted"] else "split_rejected"].append(sp | verdict)
            if verdict["accepted"]:
                _write_skill_files(s.path, res)
                c = store.commit(f"curator: split {s.name} ({sp['chars']} chars → SKILL.md + references)", root=root,
                                 author="walter-curator")
                if mode == "active":
                    _ledger("split", s.name, c, sp | verdict)
        for w in P.get("workflow", []):
            steps = [by[n] for n in w["steps"] if n in by]
            if len(steps) < 2:
                continue
            res = edit_workflow(steps, w)
            if not res or not res.get("name") or not res.get("skill_md"):
                done["workflow_rejected"].append(w | {"reason": "editor returned nothing"})
                continue
            name = re.sub(r"[^a-z0-9-]", "-", res["name"].lower()).strip("-")
            missing = [s.name for s in steps if s.name not in res["skill_md"]]
            rv = review("workflow creation", "\n\n".join(_skill_bundle(s, 8000) for s in steps), res["skill_md"])
            ok = not missing and "type: workflow" in res["skill_md"] and bool(rv and rv.get("ok"))
            entry = w | {"name": name, "missing_steps": missing, "judge": rv}
            done["workflow" if ok else "workflow_rejected"].append(entry)
            if ok and name not in by:
                dst = root / "skills" / "workflows" / name
                dst.mkdir(parents=True, exist_ok=True)
                (dst / "SKILL.md").write_text(res["skill_md"].rstrip() + "\n")
                store.write_sidecar(dst, {"origin": "walter-curator", "owner": "walter", "kind": "workflow",
                                          "requires": [s.name for s in steps], "created_at": _now().isoformat()})
                c = store.commit(f"curator: workflow {name} = {' → '.join(w['steps'])} ({w['sessions']} sessions)",
                                 root=root, author="walter-curator")
                if mode == "active":
                    _ledger("workflow", name, c, entry)

    summary = {"mode": mode, "editor": "codex:" + models.EDITOR_MODEL if editor_ok else "unavailable",
               "proposed": {k: len(v) for k, v in P.items()}, "done": {k: len(v) for k, v in done.items()}}
    _report(day, mode, P, done, summary, root)
    if mode == "shadow":
        with connection() as conn:
            conn.execute("insert into skills.ledger (actor, action, evidence) values (%s, %s, %s)",
                         ("curator.shadow", "report", json.dumps(summary)))
    return {"summary": summary, "proposals": P, "done": done, "branch": None if mode == "active" else f"curator/{day}"}


def _validate(kind: str, originals: list[store.Skill], target: store.Skill, res: dict | None, root: Path) -> dict:
    if res and res.get("skip"):
        return {"accepted": False, "reason": f"editor: not the same job — {res['skip']}"[:300]}
    if not res or not res.get("skill_md"):
        return {"accepted": False, "reason": "editor returned nothing"}
    before = "\n\n".join(_skill_bundle(s) for s in originals)
    after = res["skill_md"] + "\n\n" + "\n\n".join(f"=== {k} ===\n{v}" for k, v in (res.get("references") or {}).items())
    ll = lossless([before], after, res.get("dropped") or [])
    rv = review(kind, before, after)
    out = {"lossless": ll, "judge": rv, "retrieval": None}
    if not ll["ok"] or not (rv and rv.get("ok")):
        return out | {"accepted": False, "reason": "lossless" if not ll["ok"] else "judge"}
    if kind == "merge":
        card, desc = card_for_result(target, res)
        if card is None:
            return out | {"accepted": False, "reason": "card"}
        rc = retrieval_check([s.name for s in originals], target.name, desc, card, root)
        out["retrieval"] = rc
        out["card"] = card
        if not rc["ok"]:
            return out | {"accepted": False, "reason": "retrieval"}
    return out | {"accepted": True}


def _report(day: str, mode: str, P: dict, done: dict, summary: dict, root: Path) -> None:
    REPORTS.mkdir(exist_ok=True)
    lines = [f"# walter-skills curator — {day} ({mode})", "",
             "Shadow: changes are on git branch `curator/" + day + "` (worktree " + str(root) + "), master untouched."
             if mode == "shadow" else "Active: changes committed on master, see skills.ledger.", "",
             f"Editor: {summary['editor']} · judge: {models.JUDGE_MODEL}", "", "| | proposed | done |", "|---|---|---|"]
    for k in sorted(set(P) | set(done)):
        lines.append(f"| {k} | {len(P.get(k, []))} | {len(done.get(k, []))} |")
    for title, items in list(P.items()) + [(f"DONE {k}", v) for k, v in done.items()]:
        lines += ["", f"## {title} ({len(items)})", ""]
        lines += [f"- {json.dumps(x, ensure_ascii=False, default=str)[:600]}" for x in items[:60]] or ["- none"]
    (REPORTS / f"curator-{day}.md").write_text("\n".join(lines) + "\n")


def digest(days: int = 7) -> str:
    """Weekly Telegram digest (French, short)."""
    with connection() as conn:
        rows = conn.execute("""select action, count(*) as n from skills.ledger where actor = 'curator'
                               and at > now() - make_interval(days => %s) group by 1""", (days,)).fetchall()
        shadow = conn.execute("""select evidence from skills.ledger where actor = 'curator.shadow'
                                 order by at desc limit 1""").fetchone()
    active = len(list(store.iter_skills()))
    parts = [f"Skills W.Alter — semaine : {active} actifs."]
    if rows:
        parts.append(", ".join(f"{r['n']} {r['action']}" for r in rows) + ".")
    if shadow:
        ev = shadow["evidence"]
        parts.append(f"Mode fantôme : {ev.get('done', {})} préparés sur une branche, rien appliqué.")
    return " ".join(parts)
