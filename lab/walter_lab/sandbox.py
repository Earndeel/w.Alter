"""Lab sandbox: run untrusted code (a repository a scout found, a candidate harness) away from Walter's secrets and
data (P7 prep, 2026-10-28; owner rule: external code is untrusted, experiments run isolated, without production
secrets nor databases).

A disposable container works on a COPY of the source: no network (the host has services listening on all interfaces,
e.g. the browser API that holds the owner's cookies — a bridged container could reach them), read-only root, all
capabilities dropped, no new privileges, an unprivileged user, bounded memory / CPU / processes / time, nothing of the
host mounted except that copy, no environment passed. Results are what the code writes in /work/out, copied back.
Network access (to install dependencies) needs a dedicated network with host access blocked by a firewall rule — not
granted: asked of the owner before it exists.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_IMAGE = "python:3.12-slim"


def run(src: str | None, command: list[str], *, image: str = DEFAULT_IMAGE, timeout: int = 600,
        memory: str = "2g", cpus: str = "2", out_dir: Path | None = None) -> dict:
    if not command:
        raise ValueError("a command is required")
    work = Path(tempfile.mkdtemp(prefix="walter-lab-sandbox-"))
    try:
        (work / "src").mkdir()
        if src:
            shutil.copytree(src, work / "src", dirs_exist_ok=True, symlinks=True,
                            ignore=shutil.ignore_patterns(".git", "node_modules", "venv", ".venv", "__pycache__"))
        (work / "out").mkdir()
        for p in work.rglob("*"):
            p.chmod(0o777 if p.is_dir() else 0o666)       # the container's unprivileged user writes its copy
        work.chmod(0o777)
        name = f"walter-lab-{int(time.time() * 1000)}"
        argv = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
                "--tmpfs", "/tmp:rw,size=256m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "256", "--memory", memory, "--cpus", cpus, "--user", "65534:65534",
                "-v", f"{work}:/work", "-w", "/work/src", "-e", "HOME=/tmp", image, *command]
        t0 = time.time()
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            rc, stdout, stderr, timed_out = p.returncode, p.stdout, p.stderr, False
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            rc, stdout, stderr, timed_out = 124, (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""), "", True
        result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "image": image, "command": command,
                  "rc": rc, "timed_out": timed_out, "seconds": round(time.time() - t0, 1),
                  "stdout_tail": stdout[-4000:], "stderr_tail": stderr[-2000:], "network": "none"}
        produced = list((work / "out").rglob("*"))
        if out_dir and produced:
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(work / "out", out_dir, dirs_exist_ok=True)
            result["outputs"] = str(out_dir)
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


PROBE = r'''
import os, socket, json, pathlib
def reach(host, port):
    try:
        socket.create_connection((host, port), timeout=2).close(); return True
    except OSError:
        return False
print(json.dumps({
  "uid": os.getuid(),
  "env_keys": sorted(k for k in os.environ if k not in ("PATH", "HOME", "HOSTNAME", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256")),
  "root_home_visible": os.path.exists("/root/.hermes") or os.path.exists("/instances") or os.path.exists("/walter"),
  "internet": reach("1.1.1.1", 443),
  "host_browser_api": reach("172.17.0.1", 9377),
  "host_postgres": reach("172.17.0.1", 5433),
  "can_write_root_fs": os.access("/usr", os.W_OK),
}))
'''


def probe() -> dict:
    """Proof of isolation, measured from inside: run it after any change to the sandbox."""
    r = run(None, ["python3", "-c", PROBE], timeout=120)
    try:
        seen = json.loads(r["stdout_tail"].strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": r["stderr_tail"][-300:]}
    bad = [k for k in ("root_home_visible", "internet", "host_browser_api", "host_postgres", "can_write_root_fs") if seen.get(k)]
    bad += ["runs as root"] if seen.get("uid") == 0 else []
    bad += ["environment leaked: " + ", ".join(seen["env_keys"])] if seen.get("env_keys") else []
    return {"ok": not bad, "seen": seen, "violations": bad}
