"""The write door — the single way content enters walter-skills: any agent proposes a new skill or a fix; nothing goes
live directly (the curation Drafts operator judges every draft).

propose(...) → drafts/<name>@new-<runtime>-<ts>/      (kind: new)
patch(...)   → drafts/<name>@patch-<runtime>-<ts>/    (kind: patch, full new SKILL.md or one linked file)
The curator reviews drafts every night (judge + checks) and promotes or rejects them (curator.process_drafts).
Refused at the door: bad names, missing frontmatter, oversized content, path tricks, and anything that looks like a
secret (an agent must reference where a secret lives, never paste it).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from walter_memory import privacy

from . import store

NAME_RX = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
MAX_SKILL = 60000
MAX_FILE = 120000
MAX_FILES = 20


class Refused(ValueError):
    pass


def _check_text(label: str, text: str, limit: int) -> None:
    if len(text) > limit:
        raise Refused(f"{label}: {len(text)} chars > {limit}")
    secrets = [kind for cat, kind in privacy.detect(text) if cat == "secret"]
    if secrets:
        raise Refused(f"{label} looks like it contains a secret ({', '.join(sorted(set(secrets)))}): reference where "
                      "it is stored (e.g. Bitwarden item, env var name), never its value")


def _check_skill_md(name: str, skill_md: str) -> dict:
    fm = store.frontmatter(skill_md[:8000])
    if not fm:
        raise Refused("SKILL.md must start with a YAML frontmatter (--- name / description ---)")
    if fm.get("name") and fm["name"] != name:
        raise Refused(f"frontmatter name {fm['name']!r} != {name!r}")
    if len(fm.get("description", "")) < 20:
        raise Refused("frontmatter description missing or too short (one line, starting with 'Use when …')")
    _check_text("SKILL.md", skill_md, MAX_SKILL)
    return fm


def _files(files: dict | None) -> dict[str, str]:
    out = {}
    for rel, content in (files or {}).items():
        rel = str(rel).lstrip("/")
        if ".." in Path(rel).parts or not re.match(r"^(references|scripts|templates)/[\w./-]+$", rel):
            raise Refused(f"file path {rel!r}: only references/, scripts/ or templates/ inside the skill")
        _check_text(rel, str(content), MAX_FILE)
        out[rel] = str(content)
    if len(out) > MAX_FILES:
        raise Refused(f"too many files ({len(out)} > {MAX_FILES})")
    return out


def _draft_dir(name: str, kind: str, runtime: str | None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    tag = re.sub(r"[^a-z0-9]+", "-", (runtime or "agent").lower()).strip("-")[:20]
    d = store.DRAFTS / f"{name}@{kind}-{tag}-{ts}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def propose(name: str, skill_md: str, reason: str, files: dict | None = None, domain: str = "",
            runtime: str | None = None, session_id: str | None = None) -> dict:
    name = (name or "").strip()
    if not NAME_RX.match(name):
        raise Refused("name must be kebab-case, 3-64 chars, e.g. 'stripe-refund-flow'")
    if store.find(name, include_archived=True):
        raise Refused(f"skill {name!r} already exists: use skill_patch to improve it")
    fm = _check_skill_md(name, skill_md)
    extra = _files(files)
    if len((reason or "").strip()) < 15:
        raise Refused("reason: say in one sentence what recurring task this captures and where it was learned")
    d = _draft_dir(name, "new", runtime)
    (d / "SKILL.md").write_text(skill_md.rstrip() + "\n")
    for rel, content in extra.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(content)
    store.write_sidecar(d, {"kind": "new", "target": name, "domain": re.sub(r"[^a-z0-9/-]", "", domain.lower()),
                            "reason": reason.strip()[:2000], "runtime": runtime, "session_id": session_id,
                            "description": fm.get("description"), "created_at": datetime.now(timezone.utc).isoformat()})
    c = store.commit(f"draft (new) {name} from {runtime or 'agent'}: {reason.strip()[:120]}", paths=["drafts"],
                     author="walter-skills-door")
    return {"draft": str(d.relative_to(store.ROOT)), "commit": c, "status": "pending curator review (nightly)"}


def patch(name: str, reason: str, skill_md: str | None = None, file_path: str | None = None,
          content: str | None = None, runtime: str | None = None, session_id: str | None = None) -> dict:
    s = store.find(name, include_archived=False)
    if s is None:
        raise Refused(f"unknown active skill {name!r}")
    if s.meta.get("owner") == "upstream":
        raise Refused(f"{name!r} ships with Hermes (upstream, read-only): propose a separate skill instead")
    if len((reason or "").strip()) < 15:
        raise Refused("reason: what was wrong or missing, and the evidence (command output, session)")
    if bool(skill_md) == bool(file_path):
        raise Refused("give either the full new skill_md, or file_path + content for one linked file")
    if skill_md:  # every check happens before anything is written
        _check_skill_md(name, skill_md)
        changed = "SKILL.md"
    else:
        changed = next(iter(_files({file_path: content or ""})))
    d = _draft_dir(name, "patch", runtime)
    if skill_md:
        (d / "SKILL.md").write_text(skill_md.rstrip() + "\n")
    else:
        (d / changed).parent.mkdir(parents=True, exist_ok=True)
        (d / changed).write_text(content or "")
        (d / "SKILL.md").write_text(s.body)  # drafts are skill-shaped; the patch target is `changed`
    store.write_sidecar(d, {"kind": "patch", "target": name, "changed": changed, "domain": s.domain,
                            "base_sha": store.tree_hash(s.path), "reason": reason.strip()[:2000], "runtime": runtime,
                            "session_id": session_id, "created_at": datetime.now(timezone.utc).isoformat()})
    c = store.commit(f"draft (patch) {name}/{changed} from {runtime or 'agent'}: {reason.strip()[:120]}",
                     paths=["drafts"], author="walter-skills-door")
    return {"draft": str(d.relative_to(store.ROOT)), "commit": c, "status": "pending curator review (nightly)"}
