"""Repair of one incident by the L2 agent, on a copy of the module; deterministic gates decide whether it lands.

The agent never writes the live module: it runs in a mount namespace where the module, the instance configuration
and the system units are read-only, and works on `<state>/guardian/<incident>-<time>/module` (a copy with its own
git baseline). The patch is applied only when every gate passes, and only to files nobody else is editing.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from walter_router import instance, paths
from walter_router.guardian import checks

LEVEL = "L2"
MAX_TURNS = 80
BUDGET_S = 2400
PROMPT = paths.ROOT / "guardian" / "prompt.md"

# What a repair may change: how data is read and understood, the page, the tests. Never the owner's choices
# (config/, preferences, plans), execution policy (serve/, llm/), the schema, the units or the cycle itself.
ALLOWED = ("research/", "analysis/parse.py", "analysis/identity.py", "analysis/aliases.json", "interface/", "tests/")
_SKIP = re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.skip\(|pytest\.xfail\(")
_COPY_IGNORE = shutil.ignore_patterns("venv", "__pycache__", ".git", ".pytest_cache", "*.pyc")


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-c", "user.name=Walter Router Guardian", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=120, check=check).stdout


def workspace(incident_id: int) -> Path:
    """A fresh copy of the live module with a git baseline: what the agent works on."""
    base = instance.state_file("guardian") / f"{incident_id}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
    module = base / "module"
    shutil.copytree(paths.ROOT, module, symlinks=True, ignore=_COPY_IGNORE)
    (module / "venv").symlink_to(paths.ROOT / "venv")
    _git(module, "init", "-q")
    _git(module, "add", "-A")
    _git(module, "-c", "user.email=guardian@localhost", "commit", "-qm", "baseline (live module at copy time)")
    return module


def _render(incident: dict, module: Path) -> str:
    text = PROMPT.read_text()
    for k, v in {"workspace": str(module), "live": str(paths.ROOT),
                 "incident": json.dumps({k: incident[k] for k in ("kind", "subject", "detail", "opened_at")},
                                        ensure_ascii=False, default=str, indent=1),
                 "allowed": ", ".join(ALLOWED)}.items():
        text = text.replace("{{" + k + "}}", v)
    out = subprocess.run(["walter", "instance", "render"], input=text, capture_output=True, text=True, timeout=30)
    return out.stdout if out.returncode == 0 and out.stdout.strip() else text


def _readonly_script() -> str:
    """The live module, the instance configuration and the system units are read-only for the agent."""
    ro = [str(paths.ROOT), str(instance.state_file("guardian").parents[2] / "config"), "/etc/systemd"]
    mounts = " && ".join(f"mount --bind {p} {p} && mount -o remount,ro,bind {p}" for p in ro if Path(p).exists())
    return f"{mounts} && exec walter-router run"


def verdict_of(output: str) -> dict:
    """The agent's closing JSON (outcome, cause, changes, summary): the last object carrying an `outcome`."""
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"\{", output or ""))):
        try:
            obj, _ = decoder.raw_decode(output[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("outcome"):
            return obj
    return {"outcome": "unknown", "summary_fr": (output or "")[-600:]}


def agent(incident: dict, module: Path) -> dict:
    spec = {"goal": _render(incident, module), "task": "general", "level": LEVEL,
            "toolsets": ["terminal", "file"], "max_turns": MAX_TURNS, "budget_seconds": BUDGET_S}
    try:
        proc = subprocess.run(["unshare", "--mount", "--propagation", "private", "bash", "-c", _readonly_script()],
                              input=json.dumps(spec), capture_output=True, text=True, timeout=BUDGET_S + 600)
        res = json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__, "verdict": {"outcome": "unknown"}}
    routed = res.get("routed") or {}
    return {"ok": bool(res.get("ok")), "error": res.get("error"), "verdict": verdict_of(res.get("output") or ""),
            "model": routed.get("model_id"), "provider": routed.get("provider"), "notice": res.get("user_notice"),
            "tools": len(res.get("tools") or [])}


def changed_files(module: Path) -> list[tuple[str, str]]:
    """(status, path) of the agent's changes against the baseline; status D = deleted."""
    _git(module, "add", "-A")
    out = _git(module, "diff", "--cached", "--name-status", "--no-renames", "HEAD")
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if line.strip()]


def _asserts(text: str) -> int:
    return len(re.findall(r"\bassert\b", text))


def verify_source(module: Path, kind: str) -> dict:
    """Read the source with the repaired code (no database write): rows parsed, or the error."""
    code = ("import json,sys\nfrom walter_router.research.sources import SOURCES\nfrom walter_router.analysis import parse\n"
            "doc,_,_=SOURCES[sys.argv[1]]()\nn=None\ntry:\n    n=len(parse.parse_benchmarks(sys.argv[1],doc))\n"
            "except Exception:\n    pass\nprint(json.dumps({'ok':True,'rows':n,'size':len(json.dumps(doc,default=str))}))")
    proc = subprocess.run([str(module / "venv" / "bin" / "python"), "-c", code, kind], cwd=module,
                          capture_output=True, text=True, timeout=900)
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": (proc.stderr or proc.stdout)[-500:]}
    if out.get("rows") == 0:
        return {"ok": False, "error": "source read but nothing parsed"}
    return out


def gates(module: Path, incident: dict, baseline: dict) -> dict:
    """Deterministic checks on the agent's patch. ok=False lists why it must not land."""
    changes = changed_files(module)
    why = []
    if not changes:
        return {"ok": False, "reasons": ["no change"], "files": []}
    for status, path in changes:
        if not path.startswith(ALLOWED):
            why.append(f"outside the repair scope: {path}")
        if path.startswith("tests/"):
            if status == "D":
                why.append(f"test deleted: {path}")
                continue
            new = (module / path).read_text(errors="replace")
            old = _git(module, "show", f"HEAD:{path}", check=False) if status != "A" else ""
            if _asserts(new) < _asserts(old):
                why.append(f"fewer assertions in {path}")
            if len(_SKIP.findall(new)) > len(_SKIP.findall(old)):
                why.append(f"skip/xfail added in {path}")
    after = checks.run_tests(module)
    new_failures = sorted(set(after["failures"]) - set(baseline["failures"]))
    if new_failures:
        why.append("new failing tests: " + ", ".join(new_failures[:5]))
    if incident["kind"] == "test_failure" and incident["subject"] in after["failures"]:
        why.append("the failing test still fails")
    source = None
    if incident["kind"] in ("source_stale", "source_error"):
        source = verify_source(module, incident["subject"])
        if not source["ok"]:
            why.append(f'source still unreadable: {source.get("error", "")[:200]}')
    return {"ok": not why, "reasons": why, "files": [p for _, p in changes], "deleted": [p for s, p in changes if s == "D"],
            "tests_after": {"failures": sorted(after["failures"])}, "source": source}


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def apply(module: Path, files: list[str], deleted: list[str], message: str) -> dict:
    """Copy the verified files into the live module, only where the live file is exactly what the agent started
    from and nobody has uncommitted work on it; then commit just those paths."""
    busy = checks.dirty_paths()
    blocked = []
    for path in files:
        base = _git(module, "show", f"HEAD:{path}", check=False).encode() if path not in _new(module) else None
        live = paths.ROOT / path
        live_digest = _digest(live)
        base_digest = hashlib.sha256(base).hexdigest() if base is not None else None
        if path in busy or live_digest != base_digest:
            blocked.append(path)
    if blocked:
        return {"applied": False, "deferred": True, "blocked": blocked}
    for path in files:
        live = paths.ROOT / path
        if path in deleted:
            live.unlink(missing_ok=True)
        else:
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(module / path, live)
    root = paths.ROOT
    _git(root, "add", "--", *files)
    email = _git(root, "config", "user.email", check=False).strip() or "guardian@localhost"
    _git(root, "-c", f"user.email={email}", "commit", "-q", "-m", message, "--", *files)
    return {"applied": True, "commit": _git(root, "rev-parse", "--short", "HEAD").strip(), "files": files}


def regenerate_docs(message: str) -> dict:
    """Generated reference out of date: regenerate it (no model), and commit the regenerated files alone, unless one
    of them is someone's uncommitted work."""
    busy = checks.dirty_paths()
    stale = checks.docs_check().get("stale") or []
    blocked = [p for p in stale if p in busy]
    if blocked:
        return {"applied": False, "deferred": True, "blocked": blocked}
    proc = subprocess.run(["walter-router", "docs", "--write"], capture_output=True, text=True, timeout=600)
    after = checks.docs_check()
    if proc.returncode or not after.get("ok"):
        return {"applied": False, "error": (proc.stderr or proc.stdout)[-500:] or after.get("error"), "check": after}
    changed = sorted(checks.dirty_paths() - busy)
    if not changed:
        return {"applied": True, "files": [], "commit": None}
    if any(not p.startswith("docs/reference/") for p in changed):
        return {"applied": True, "files": changed, "commit": None, "note": "files outside docs/reference left uncommitted"}
    root = paths.ROOT
    _git(root, "add", "--", *changed)
    email = _git(root, "config", "user.email", check=False).strip() or "guardian@localhost"
    _git(root, "-c", f"user.email={email}", "commit", "-q", "-m", message, "--", *changed)
    return {"applied": True, "files": changed, "commit": _git(root, "rev-parse", "--short", "HEAD").strip()}


def _new(module: Path) -> set[str]:
    out = _git(module, "diff", "--cached", "--name-status", "--no-renames", "HEAD")
    return {line.split("\t", 1)[1] for line in out.splitlines() if line.startswith("A\t")}


def prune(days: int = 7, keep: set[str] = frozenset()) -> int:
    """Old workspaces go; those holding a deferred patch stay."""
    root = instance.state_file("guardian")
    if not root.exists():
        return 0
    n = 0
    for d in root.iterdir():
        if d.is_dir() and str(d / "module") not in keep and time.time() - d.stat().st_mtime > days * 86400:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n
