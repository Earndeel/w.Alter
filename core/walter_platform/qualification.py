"""Source attestations for scenario evidence. No runtime, database or model calls.

A passing run is current evidence only while the scenario, bench protocol, module source
inventories and the declared module versions still match. Old evidence stays readable in
its report; a timestamp alone is not a qualification. Git is used as a source inventory,
including uncommitted edits and untracked source additions, never as a cleanliness claim.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import harness, registry
from .release import _excluded, _source

CORE = Path(__file__).resolve().parents[1]
BENCH_VERSION = 2
CAPABILITY_MODULE = {"identity": "soul", "model": "llm", "secrets": "secrets", "browse": "browse",
                     "computer": "computer", "context": "context", "memory": "memory", "logs": "logs", "skills": "skills"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_snapshot(root: Path) -> str:
    """Bounded by the local Git index/ignore rules; never traverses data directories or follows links."""
    root = Path(root)
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("source inventory unavailable")
    digest = hashlib.sha256()
    names = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    count = 0
    for name in names:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("unsafe source inventory")
        if _excluded(name) or any(part in ("state", "data") for part in rel.parts):
            continue
        path = root / rel
        # Include symlink identity, but never read an external target. The target's module has its own snapshot.
        if path.is_symlink():
            payload = ("link:" + str(path.readlink())).encode()
        elif _source(path, name):
            payload = path.read_bytes()
        elif not path.exists():
            payload = b"missing"
        else:
            continue
        digest.update(name.encode() + b"\0" + _hash(payload).encode() + b"\0")
        count += 1
    if count == 0:
        raise ValueError("empty source inventory")
    return digest.hexdigest()


def attest(scenario: dict, path: Path) -> dict:
    """Attest all declared scenario pairs together, with common execution/recording infrastructure."""
    modules = {m["id"]: m for m in registry.load()["modules"]}
    wanted = {"core", "memory", "logs", "router", "llm", "runtime"}
    hosts = set()
    for pair in scenario.get("qualifies") or []:
        wanted.add(CAPABILITY_MODULE[pair["capability"]])
        if pair["harness"] not in harness.HOSTS:
            raise ValueError("unknown qualification harness")
        hosts.add(pair["harness"])
    def dependencies(name):
        if name not in modules:
            raise ValueError("missing qualification dependency")
        for dep in modules[name].get("requires", []):
            if dep not in wanted:
                wanted.add(dep)
                dependencies(dep)
    for name in list(wanted):
        dependencies(name)
    snapshots, sources = {}, {}
    for name in sorted(wanted):
        module = modules[name]
        root = CORE if name == "core" else Path(module["root"])
        real = root.resolve()
        if real not in snapshots:
            snapshots[real] = source_snapshot(real)
        sources[name] = {"version": module.get("contract", {}).get("version"), "sha256": snapshots[real]}
    bindings = {}
    for host in sorted(hosts):
        cfg = harness.config_path(host)
        if not cfg.is_file():
            raise ValueError("harness configuration unavailable")
        # Store hashes only. Client configuration may contain private values.
        bindings[host] = _hash(cfg.read_bytes())
    return {"version": 1, "bench_version": BENCH_VERSION, "scenario_sha256": _hash(Path(path).read_bytes()),
            "sources": sources, "bindings": bindings}


def current(proof: dict, *, core: Path | None = None) -> bool:
    attestation = proof.get("attestation")
    if not isinstance(attestation, dict) or attestation.get("version") != 1 or attestation.get("bench_version") != BENCH_VERSION:
        return False
    name = proof.get("scenario")
    if not isinstance(name, str) or Path(name).name != name:
        return False
    path = (core or CORE) / "scenarios" / (name + ".yaml")
    try:
        import yaml
        scenario = yaml.safe_load(path.read_text())
        return attest(scenario, path) == attestation
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False
