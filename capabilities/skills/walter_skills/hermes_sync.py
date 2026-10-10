"""One-way sync Hermes → walter-skills. Hermes keeps its own skills and curator untouched; we only read.

- New Hermes skill → imported (owner `upstream` for bundled/hub skills, `walter` for skills the agent wrote).
- Hermes changed a skill we never edited → fast-forward our copy.
- Hermes changed a skill we edited too → Hermes' version goes to drafts/ for the curator to merge (never overwrites).
- Hermes archived/removed a skill → ignored (our lifecycle is ours); recorded in the sidecar.
`restore` imports chosen skills from Hermes' .archive/ (the ones its curator absorbed) back into our active store.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import store

HERMES = Path("/root/.hermes/skills")
LEDGER = HERMES / ".curator_ledger.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bundled() -> set[str]:
    p = HERMES / ".bundled_manifest"
    return {line.split(":", 1)[0] for line in p.read_text().splitlines() if line.strip()} if p.exists() else set()


def _hub() -> set[str]:
    p = HERMES / ".hub" / "lock.json"
    return set(json.loads(p.read_text()).get("installed", {})) if p.exists() else set()


def hermes_active() -> dict[str, tuple[Path, str]]:
    """name -> (dir, category). Nested SKILL.md that duplicate an ancestor's name are copies, not skills."""
    out: dict[str, tuple[Path, str]] = {}
    for md in sorted(HERMES.rglob("SKILL.md"), key=lambda p: len(p.parts)):
        rel = md.parent.relative_to(HERMES)
        if rel.parts[0].startswith(".") or set(rel.parts) & store.IGNORED_PARTS:
            continue
        name = md.parent.name
        if name in out or name in rel.parts[:-1]:
            continue
        out[name] = (md.parent, "/".join(rel.parts[:-1]))
    return out


def _nested_skill_dirs(src: Path) -> set[Path]:
    return {md.parent for md in src.rglob("SKILL.md") if md.parent != src}


def _copy(src: Path, dst: Path) -> None:
    nested = _nested_skill_dirs(src)

    def ignore(d: str, names: list[str]) -> list[str]:
        return [n for n in names if n in store.IGNORED_PARTS or n == store.SIDECAR or Path(d, n) in nested]

    if dst.exists():
        keep = store.read_sidecar(dst)
        shutil.rmtree(dst)
    else:
        keep = {}
    shutil.copytree(src, dst, ignore=ignore)
    if keep:
        store.write_sidecar(dst, keep)


def _repo_skills() -> set[str]:
    """Skills shipped in the Hermes repository (skills/ + optional-skills/): upstream even when not in the manifest."""
    repo = Path("/root/.hermes/hermes-agent")
    return {md.parent.name for d in ("skills", "optional-skills") for md in (repo / d).rglob("SKILL.md")}


def _draft(name: str, src: Path, sha: str, kind: str, domain: str, reason: str) -> bool:
    """Hermes' change → drafts/<name>@<kind>-hermes-<sha8> for the curator (once per Hermes version)."""
    dst = store.DRAFTS / f"{name}@{kind.replace('_', '-')}-hermes-{sha[:8]}"
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    _copy(src, dst)
    from .history import edit_evidence
    try:
        evidence = edit_evidence(name)
    except Exception:
        evidence = {}
    store.write_sidecar(dst, {"kind": kind, "target": name, "domain": domain, "runtime": "hermes", "reason": reason,
                              "evidence": evidence, "hermes": {"path": str(src), "sha": sha, "state": "active"},
                              "created_at": _now()})
    return True


def _origin(name: str, bundled: set[str], hub: set[str]) -> tuple[str, str]:
    if name in bundled or name in _REPO:
        return "hermes-bundled", "upstream"
    if name in hub:
        return "hermes-hub", "upstream"
    return "hermes-agent", "walter"


_REPO: set[str] = set()


def sync(dry_run: bool = False, names: set[str] | None = None) -> dict:
    """Full pass (names=None) or only the given Hermes skills (event-driven)."""
    global _REPO
    _REPO = _repo_skills()
    bundled, hub = _bundled(), _hub()
    ours = {s.name: s for s in store.iter_skills(include_archived=True, include_drafts=False)}
    stats = {"imported": [], "drafted_new": [], "drafted_patch": [], "fast_forward": [], "draft_conflict": [],
             "hermes_gone": [], "unchanged": 0}
    src = hermes_active()
    for name, (d, category) in src.items():
        if names is not None and name not in names:
            continue
        h = store.tree_hash(d)
        mine = ours.get(name)
        origin, owner = _origin(name, bundled, hub)
        if mine is None:
            if owner == "upstream":  # shipped with Hermes: imported as is
                stats["imported"].append(name)
                if not dry_run:
                    dst = store.SKILLS / (category or "misc") / name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    _copy(d, dst)
                    store.write_sidecar(dst, {"origin": origin, "owner": owner, "imported_at": _now(),
                                              "hermes": {"path": str(d), "sha": h, "state": "active"},
                                              "store_sha": store.tree_hash(dst)})
            else:  # written by the Hermes agent: reviewed by the curator like any agent proposal
                if not dry_run and _draft(name, d, h, "new", category, "created by the Hermes agent (skill_manage)"):
                    stats["drafted_new"].append(name)
            continue
        side = mine.meta.get("hermes") or {}
        if side.get("sha") == h or (side.get("pending_sha") == h and any(store.DRAFTS.glob(f"{name}@*-hermes-{h[:8]}"))):
            stats["unchanged"] += 1
            continue
        untouched = store.tree_hash(mine.path) == mine.meta.get("store_sha")
        if mine.meta.get("owner") == "upstream" and untouched and mine.state == "active":
            stats["fast_forward"].append(name)
            if not dry_run:
                _copy(d, mine.path)
                meta = mine.meta | {"hermes": side | {"sha": h, "path": str(d), "state": "active", "synced_at": _now()}}
                meta["store_sha"] = store.tree_hash(mine.path)
                store.write_sidecar(mine.path, meta)
            continue
        kind = "hermes_patch" if untouched and mine.state == "active" else "hermes_update"
        if not dry_run and _draft(name, d, h, kind, mine.domain,
                                  "patched by the Hermes agent" if kind == "hermes_patch" else
                                  "Hermes changed a skill Walter also changed (manual merge)"):
            stats["drafted_patch" if kind == "hermes_patch" else "draft_conflict"].append(name)
            store.write_sidecar(mine.path, mine.meta | {"hermes": side | {"pending_sha": h}})
    for name, s in ([] if names is not None else ours.items()):
        side = s.meta.get("hermes") or {}
        if side.get("state") == "active" and name not in src:
            stats["hermes_gone"].append(name)
            if not dry_run:
                store.write_sidecar(s.path, s.meta | {"hermes": side | {"state": "gone", "gone_at": _now()}})
    if not dry_run:
        n = {k: len(v) if isinstance(v, list) else v for k, v in stats.items()}
        store.commit(f"sync from Hermes: {n}")
    return stats


def _archived_category(name: str) -> str:
    """Category a Hermes-archived skill had before archiving, from the curator ledger's before-paths."""
    if not LEDGER.exists():
        return ""
    for line in LEDGER.read_text().splitlines():
        r = json.loads(line)
        if r.get("skill") != name:
            continue
        for b in r.get("before") or []:
            parts = Path(b.get("path", "")).relative_to(HERMES).parts if b.get("path", "").startswith(
                str(HERMES)) else ()
            if name in parts and not parts[0].startswith("."):
                return "/".join(parts[:parts.index(name)])
    return ""


def restore(names: list[str], reason: str) -> list[str]:
    done = []
    ours = {s.name for s in store.iter_skills(include_archived=True)}
    for name in names:
        src = HERMES / ".archive" / name
        if name in ours or not (src / "SKILL.md").exists():
            continue
        category = _archived_category(name) or "misc"
        dst = store.SKILLS / category / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        _copy(src, dst)
        store.write_sidecar(dst, {"origin": "hermes-archive-restored", "owner": "walter", "imported_at": _now(),
                                  "restore_reason": reason,
                                  "hermes": {"path": str(src), "sha": store.tree_hash(src), "state": "archived"},
                                  "store_sha": store.tree_hash(dst)})
        done.append(name)
    store.commit(f"restore {len(done)} skills from Hermes' curator archive: {reason}")
    return done


def import_archive_rest() -> list[str]:
    """Every other Hermes-archived skill → our archive/ (searchable on demand, not active)."""
    done = []
    ours = {s.name for s in store.iter_skills(include_archived=True)}
    for src in sorted((HERMES / ".archive").iterdir()):
        if not (src / "SKILL.md").exists() or src.name in ours:
            continue
        dst = store.ARCHIVE / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        _copy(src, dst)
        store.write_sidecar(dst, {"origin": "hermes-archive", "owner": "walter", "imported_at": _now(),
                                  "domain": _archived_category(src.name),
                                  "hermes": {"path": str(src), "sha": store.tree_hash(src), "state": "archived"},
                                  "store_sha": store.tree_hash(dst)})
        done.append(src.name)
    store.commit(f"import {len(done)} Hermes-archived skills into archive/")
    return done
