"""The walter-skills store: a git repository of SKILL.md directories, independent of any runtime.

Layout: skills/<domain>/<name>/SKILL.md (+ references/, scripts/, templates/), archive/<name>/, drafts/<name>/.
Each skill directory may carry a `.walter.json` sidecar (owner, origin, sync hashes) — never edited by runtimes.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path("/walter/skills")
SKILLS = ROOT / "skills"
ARCHIVE = ROOT / "archive"
DRAFTS = ROOT / "drafts"
SIDECAR = ".walter.json"
IGNORED_PARTS = {"__pycache__", ".git", ".DS_Store"}


def frontmatter(text: str) -> dict:
    """Top-level scalar keys of the YAML frontmatter (block scalars folded). No YAML dependency on purpose."""
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    out: dict[str, str] = {}
    if not m:
        return out
    lines = m.group(1).splitlines()
    for i, line in enumerate(lines):
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v in (">", "|", ">-", "|-", ">+", "|+"):
            block = []
            for nxt in lines[i + 1:]:
                if nxt.startswith((" ", "\t")) or not nxt.strip():
                    block.append(nxt.strip())
                else:
                    break
            v = " ".join(b for b in block if b)
        out[k.strip()] = v.strip().strip("\"'")
    return out


def tree_hash(d: Path) -> str:
    """Content hash of a skill directory (relative paths + bytes), sidecar excluded."""
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.name != SIDECAR and not (set(p.relative_to(d).parts) & IGNORED_PARTS):
            h.update(str(p.relative_to(d)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


@dataclass
class Skill:
    name: str
    path: Path
    state: str  # active | archived | draft
    domain: str
    description: str = ""
    tags: str = ""
    body: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def skill_md(self) -> Path:
        return self.path / "SKILL.md"


def read_sidecar(d: Path) -> dict:
    p = d / SIDECAR
    return json.loads(p.read_text()) if p.exists() else {}


def write_sidecar(d: Path, data: dict) -> None:
    (d / SIDECAR).write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def _load(d: Path, state: str, domain: str) -> Skill:
    text = (d / "SKILL.md").read_text(errors="replace")
    fm = frontmatter(text[:8000])
    return Skill(name=d.name, path=d, state=state, domain=domain, description=fm.get("description", ""),
                 tags=fm.get("tags", ""), body=text, meta=read_sidecar(d))


def iter_skills(include_archived: bool = False, include_drafts: bool = False, root: Path | None = None):
    """Skills of the store at `root` (default: the live store; a git worktree for curator branches)."""
    root = root or ROOT
    skills_dir, archive_dir, drafts_dir = root / "skills", root / "archive", root / "drafts"
    if skills_dir.exists():
        for md in sorted(skills_dir.rglob("SKILL.md")):
            rel = md.parent.relative_to(skills_dir)
            if set(rel.parts) & IGNORED_PARTS:
                continue
            yield _load(md.parent, "active", "/".join(rel.parts[:-1]))
    for base, state, wanted in ((archive_dir, "archived", include_archived), (drafts_dir, "draft", include_drafts)):
        if wanted and base.exists():
            for d in sorted(p for p in base.iterdir() if (p / "SKILL.md").exists()):
                yield _load(d, state, read_sidecar(d).get("domain", ""))


def find(name: str, include_archived: bool = True) -> Skill | None:
    return next((s for s in iter_skills(include_archived=include_archived) if s.name == name), None)


def git(*args: str, check: bool = True, root: Path | None = None) -> str:
    r = subprocess.run(["git", "-C", str(root or ROOT), *args], capture_output=True, text=True, check=check)
    return r.stdout.strip()


@contextmanager
def write_lock():
    """One git writer at a time across processes (service door, quick job, nightly, curation)."""
    import fcntl
    with open(ROOT / ".git" / "walter-skills.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def commit(message: str, paths: list[str] | None = None, author: str = "walter-skills",
           root: Path | None = None) -> str | None:
    if (root or ROOT) == ROOT:
        with write_lock():
            return _commit(message, paths, author, ROOT)
    return _commit(message, paths, author, root)


def _commit(message: str, paths: list[str] | None, author: str, root: Path) -> str | None:
    paths = [p for p in (paths or ["skills", "archive", "drafts"]) if (root / p).exists()]
    if not paths:
        return None
    git("add", "-A", *paths, root=root)
    if not git("status", "--porcelain", *paths, root=root):
        return None
    git("-c", f"user.name={author}", "-c", "user.email=walter-skills@localhost", "commit", "-q", "-m", message,
        root=root)
    return git("rev-parse", "HEAD", root=root)
