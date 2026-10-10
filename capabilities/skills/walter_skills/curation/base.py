"""Shared machinery of the curation operators: the run context, the checks every change must pass, the git branch."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import cards as cards_mod
from .. import config, evaluate, postes, registry, store
from ..ranker import Corpus, Encoder, Ranker, features, score
from . import signals

TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".sql", ".js", ".ts", ".mjs", ".toml", ".ini",
                 ".cfg", ".html", ".css")
WORKTREES = store.ROOT / ".worktrees"


@dataclass
class Context:
    root: Path               # the store being changed: master (active) or a worktree (shadow)
    mode: str                # active | shadow
    day: str
    cfg: dict
    use_models: bool
    cards: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)
    sig: dict = field(default_factory=dict)   # signals computed once per run (usage, needed, pins, similarity…)

    def skills(self) -> dict[str, store.Skill]:
        return {s.name: s for s in store.iter_skills(root=self.root)}

    def commit(self, message: str, action: str, name: str | None, evidence: dict,
               paths: list[str] | None = None) -> str | None:
        c = store.commit(message, root=self.root, author="walter-curator", paths=paths)
        if c and self.mode == "active":
            registry.ledger("curator", action, name, c, evidence)
        return c


# ── content helpers ───────────────────────────────────────────────────────────────────────────────────

def bundle(s: store.Skill, limit: int = 150000, per_file: int = 40000) -> str:
    """The skill as the editor/judge reads it. Never truncated silently: any cut is marked as display-only."""
    def cut(text: str, n: int) -> str:
        return text if len(text) <= n else text[:n] + f"\n[… display truncated here: {len(text) - n} more chars; the file is complete on disk …]"
    parts = [f"=== {s.name}/SKILL.md ===\n{cut(s.body, per_file)}"]
    for p in sorted(s.path.rglob("*")):
        if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and "__pycache__" not in p.parts:
            txt = cut(p.read_text(errors="replace"), per_file) if p.suffix in TEXT_SUFFIXES else f"(binary, {p.stat().st_size} bytes)"
            parts.append(f"=== {s.name}/{p.relative_to(s.path)} ===\n{txt}")
    return cut("\n\n".join(parts), limit)


def sections(md: str) -> tuple[str, str, list[tuple[str, str]]]:
    """(frontmatter, intro before the first ## heading, [(heading, section text incl. heading)])."""
    m = re.match(r"(---\s*\n.*?\n---\s*\n)", md, re.S)
    fm, body = (m.group(1), md[m.end():]) if m else ("", md)
    parts = re.split(r"(?m)^(?=## )", body)
    intro = parts[0] if parts and not parts[0].startswith("## ") else ""
    return fm, intro, [(p.splitlines()[0], p) for p in parts if p.startswith("## ")]


def write_files(dst: Path, res: dict) -> None:
    (dst / "SKILL.md").write_text(res["skill_md"].rstrip() + "\n")
    copied = None
    if res.get("copy_dir"):  # byte-exact copy of an absorbed skill (binaries included)
        src, rel = res["copy_dir"]
        target = dst / rel
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=shutil.ignore_patterns(store.SIDECAR, "__pycache__"))
        (target / "SKILL.md").rename(target / f"{Path(src).name}.md")
        copied = rel
    for rel, content in (res.get("references") or {}).items():
        rel = rel.lstrip("/")
        if rel.startswith("references/") and ".." not in rel and not (copied and rel.startswith(copied)):
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            (dst / rel).write_text(content.rstrip() + "\n")


def archive(root: Path, s: store.Skill, reason: str, extra: dict | None = None) -> None:
    dst = root / "archive" / s.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(s.path), str(dst))
    store.write_sidecar(dst, store.read_sidecar(dst) | {"domain": s.domain, "archived_reason": reason,
                                                        "archived_at": signals.now().isoformat(timespec="seconds")}
                        | (extra or {}))


# ── the checks every change must pass ─────────────────────────────────────────────────────────────────

ATOM_RX = [r"`([^`\n]{3,120})`", r"(?<![\w.])(/(?:opt|root|etc|var|usr|home|tmp)/[\w./~@-]+)",
           r"(https?://[^\s)>\]\"'`]+)", r"\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{2,5})\b", r"\b([A-Z][A-Z0-9_]{3,}=)"]


def atoms(text: str) -> set[str]:
    """Commands, paths, URLs, ports, variables and code lines — what a change must never silently lose."""
    out = set()
    for rx in ATOM_RX:
        out |= {m.strip() for m in re.findall(rx, text) if m.strip()}
    for block in re.findall(r"```[\w-]*\n(.*?)```", text, re.S):
        out |= {line.strip() for line in block.splitlines() if len(line.strip()) > 8}
    return out


def lossless(before: str, after: str, dropped: list[dict]) -> dict:
    dropped_txt = " ".join(json.dumps(d, ensure_ascii=False) for d in dropped)
    missing = sorted(a for a in atoms(before) if a not in after and a not in dropped_txt)
    return {"ok": not missing, "missing": missing[:40]}


def review(kind: str, before: str, after: str) -> dict | None:
    """The judge poste (another model family than the editor)."""
    obj, _ = postes.ask_json(
        "judge", f"You are the reviewer of an automated {kind} in W.Alter's skill library (procedures an AI agent loads "
                 "before acting). Reject if any still-valid procedure, command, path, credential *location*, model id or "
                 "warning was lost or altered, if facts were invented, or if the result is less usable by an agent. "
                 'Return JSON only: {"ok": true|false, "issues": ["..."]}\n\n'
                 "Texts marked 'display truncated' are complete on disk: never treat a display cut as content loss.\n\n"
                 f"BEFORE:\n{before}\n\nAFTER:\n{after}", require="ok", timeout=300)
    return obj


def card_for(target: store.Skill, res: dict) -> tuple[dict | None, str]:
    """Trigger card of an edited skill, generated from the edited files in a scratch copy."""
    with tempfile.TemporaryDirectory(prefix="walter-card-") as d:
        tmp = Path(d) / target.name
        shutil.copytree(target.path, tmp)
        write_files(tmp, res)
        s = store._load(tmp, "active", target.domain)
        card, _ = cards_mod.generate(s)
        return card, s.description


def retrieval_kept(ctx: Context, before_names: list[str], target: str, new_desc: str, new_card: dict) -> dict:
    """Labelled messages that needed any of `before_names`: after the change (they are replaced by `target` with its
    new card), is `target` in the top 15 at least as often as one of them was before? (single evaluator's ranker)"""
    from ..learning import _cases_by_qid
    row = registry.ranker()
    if row is None:
        return {"ok": True, "note": "no active ranker"}
    r = Ranker.loads(bytes(row["blob"]))
    cases = _cases_by_qid()
    want = [cases[q] for q, lab in registry.labels(("bench", "judge")).items()
            if q in cases and any(lab.get(n, (0,))[0] == 2 for n in before_names)]
    if not want:
        return {"ok": True, "cases": 0, "note": "no labelled message"}
    enc = Encoder.get()
    skills = [{"name": s.name, "description": s.description} for s in store.iter_skills(root=ctx.root)]
    before = Corpus(skills, ctx.cards, enc)
    after_sk = [x | ({"description": new_desc} if x["name"] == target else {}) for x in skills
                if x["name"] == target or x["name"] not in before_names]
    after = Corpus(after_sk, ctx.cards | {target: new_card}, enc)

    def in_top(c: Corpus, names: list[str], x: dict) -> bool:
        s = score(r, features(c, r, x["query"], x.get("ctx", "")))
        return bool({c.names[i] for i in np.argsort(-s)[:15]} & set(names))

    b = sum(in_top(before, before_names, x) for x in want)
    a = sum(in_top(after, [target], x) for x in want)
    return {"ok": a >= b, "cases": len(want), "before_in_top15": b, "after_in_top15": a}


def validate(ctx: Context, kind: str, originals: list[store.Skill], target: store.Skill, res: dict | None) -> dict:
    if res and res.get("skip"):
        return {"accepted": False, "reason": f"editor: not the same job — {res['skip']}"[:300]}
    if not res or not res.get("skill_md"):
        return {"accepted": False, "reason": "editor returned nothing"}
    before = "\n\n".join(bundle(s) for s in originals)
    new_files = {k.lstrip("/"): v for k, v in (res.get("references") or {}).items()}
    kept = {}
    for p in sorted(target.path.rglob("*")):
        rel = str(p.relative_to(target.path))
        if p.is_file() and p.name not in ("SKILL.md", store.SIDECAR) and rel not in new_files and "__pycache__" not in p.parts:
            kept[rel] = p.read_text(errors="replace") if p.suffix in TEXT_SUFFIXES else f"(binary, {p.stat().st_size} bytes)"
    after = res["skill_md"] + "\n\n" + "\n\n".join(f"=== {k} ===\n{v}" for k, v in {**kept, **new_files}.items())
    ll = lossless(before, after, res.get("dropped") or [])
    files = "\n".join(f"- {k} ({len(v)} chars{', new' if k in new_files else ''})" for k, v in {**kept, **new_files}.items())
    rv = review(kind, f"ORIGINAL SKILL(S):\n{before[:50000]}",
                "A script moved/copied the original content VERBATIM and verified that every command, path, URL, port, "
                f"code line and variable of the original is present after the {kind} (lossless check: "
                f"{'passed' if ll['ok'] else 'FAILED'}). Judge the result as an agent would use it: frontmatter kept, "
                "always-on rules first, every moved part reachable through an explicit references/ link; does the NEW "
                f"text written by the editor invent or alter any fact?\n\nNEW SKILL.md:\n{res['skill_md'][:30000]}\n\n"
                f"FILES AFTER:\n{files}\n\nTEXT WRITTEN BY THE EDITOR:\n{res.get('added_text') or '(see SKILL.md)'}")
    out = {"lossless": ll, "judge": rv}
    if not ll["ok"] or not (rv and rv.get("ok")):
        return out | {"accepted": False, "reason": "lossless" if not ll["ok"] else "judge"}
    if kind == "merge":
        card, desc = card_for(target, res)
        if card is None:
            return out | {"accepted": False, "reason": "card"}
        rc = retrieval_kept(ctx, [s.name for s in originals], target.name, desc, card)
        out |= {"retrieval": rc, "card": card}
        if not rc["ok"]:
            return out | {"accepted": False, "reason": "retrieval"}
    return out | {"accepted": True}


# ── branch ────────────────────────────────────────────────────────────────────────────────────────────

def worktree(day: str) -> Path:
    WORKTREES.mkdir(exist_ok=True)
    wt = WORKTREES / f"curator-{day}"
    if wt.exists():
        subprocess.run(["git", "-C", str(store.ROOT), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(store.ROOT), "worktree", "add", "-B", f"curator/{day}", str(wt), "HEAD"],
                   capture_output=True, check=True)
    return wt


def mode_today(cfg: dict, day: str, apply: bool | None) -> str:
    if apply is not None:
        return "active" if apply else "shadow"
    return "active" if cfg["mode"] == "active" and day >= cfg["shadow_until"] else "shadow"


def config_section() -> dict:
    return config.get("curation")
