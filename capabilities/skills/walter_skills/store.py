"""The walter-skills store: a git repository of SKILL.md directories, independent of any runtime.

Layout: skills/<domain>/<name>/SKILL.md (+ references/, scripts/, templates/), archive/<name>/, drafts/<name>/.
Each skill directory may carry a `.walter.json` sidecar (owner, origin, sync hashes) — never edited by runtimes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path("/opt/walter-skills")
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


def iter_skills(include_archived: bool = False, include_drafts: bool = False):
    if SKILLS.exists():
        for md in sorted(SKILLS.rglob("SKILL.md")):
            rel = md.parent.relative_to(SKILLS)
            if set(rel.parts) & IGNORED_PARTS:
                continue
            yield _load(md.parent, "active", "/".join(rel.parts[:-1]))
    for base, state, wanted in ((ARCHIVE, "archived", include_archived), (DRAFTS, "draft", include_drafts)):
        if wanted and base.exists():
            for d in sorted(p for p in base.iterdir() if (p / "SKILL.md").exists()):
                yield _load(d, state, read_sidecar(d).get("domain", ""))


def find(name: str, include_archived: bool = True) -> Skill | None:
    return next((s for s in iter_skills(include_archived=include_archived) if s.name == name), None)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=check)
    return r.stdout.strip()


def commit(message: str, paths: list[str] | None = None, author: str = "walter-skills") -> str | None:
    paths = [p for p in (paths or ["skills", "archive", "drafts"]) if (ROOT / p).exists()]
    if not paths:
        return None
    git("add", "-A", *paths)
    if not git("status", "--porcelain", *paths):
        return None
    git("-c", f"user.name={author}", "-c", "user.email=walter-skills@localhost", "commit", "-q", "-m", message)
    return git("rev-parse", "HEAD")
