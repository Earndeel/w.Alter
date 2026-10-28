"""Lab sandbox: run untrusted code (a repository a scout found, a candidate harness) away from Walter's secrets and
data (P7 prep, 2026-10-28; owner rule: external code is untrusted, experiments run isolated, without production
secrets nor databases).

A disposable container works on a validated COPY of an approved source tree: no network, read-only root, dropped
capabilities, no new privileges, an unprivileged user, bounded memory / CPU / processes / time, and no forwarded host
environment. Host copies reject links and special files and exclude known credential names. Results from /work/out
are validated after container removal, then copied to a fresh destination. See README for limits: this is Docker
isolation on the host kernel, source-content sanitisation remains the caller's duty, and the writable bind has no
filesystem quota during execution. Network access is not implemented.
"""
from __future__ import annotations

import json
import os
import selectors
import stat
import uuid
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_IMAGE = "python:3.12-slim"


class CopyPolicyError(ValueError):
    """An input/output tree cannot safely cross the host/container boundary."""


# Name-based exclusions are defence in depth, not a detector for arbitrary secret contents.
_IGNORED = {".git", "node_modules", "venv", ".venv", "__pycache__"}
_CREDENTIALS = {".aws", ".ssh", ".gnupg", ".config", ".kube", ".docker", ".pgpass", ".netrc",
                "credentials", "credentials.json", "credentials.yaml", "credentials.yml",
                "secrets", "secrets.json", "secrets.yaml", "secrets.yml", "id_rsa", "id_ed25519",
                "id_ecdsa", "id_dsa", "service-account.json", "service_account.json", "auth.json"}


def _excluded(name: str) -> bool:
    lower = name.lower()
    return (name in _IGNORED or lower in _CREDENTIALS or lower.removeprefix(".") in _CREDENTIALS
            or lower.endswith(".env") or lower.startswith(".env.")
            or lower.endswith((".pem", ".key", ".p12", ".pfx", ".agekey")))


def _open_directory(path: Path, *, create: bool = False) -> int:
    """Walk every component without following links; the returned fd pins the directory."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(os.path.abspath(path)).parts[1:]:
            try:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except OSError as exc:
        os.close(fd)
        raise CopyPolicyError("directory contains a symlink or is unavailable") from exc


def _copy_tree(source_fd: int, target_fd: int, *, source: bool, max_bytes: int,
               max_entries: int, max_file_bytes: int, max_depth: int = 64) -> dict:
    """Only open regular single-link files and directories relative to already-open directories.

    O_NOFOLLOW + fstat also cover a replacement after lstat. O_NONBLOCK prevents a raced FIFO from
    blocking open. No chmod/chown/copystat ever touches an input path. Copy limits apply to actual bytes,
    including a file that grows while it is read. A mutable source is not a point-in-time snapshot.
    """
    totals = {"entries": 0, "bytes": 0}

    def copy_dir(src_fd, dst_fd, depth):
        if depth > max_depth:
            raise CopyPolicyError("directory depth limit exceeded")
        with os.scandir(src_fd) as entries:
            for entry in entries:
                name = entry.name
                before = os.stat(name, dir_fd=src_fd, follow_symlinks=False)
                if stat.S_ISLNK(before.st_mode):
                    raise CopyPolicyError("symlink not allowed")
                if not (stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode)):
                    raise CopyPolicyError("special file not allowed")
                totals["entries"] += 1
                if totals["entries"] > max_entries:
                    raise CopyPolicyError("entry limit exceeded")
                if source and _excluded(name):
                    continue
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if stat.S_ISDIR(before.st_mode):
                    flags |= os.O_DIRECTORY
                try:
                    opened = os.open(name, flags, dir_fd=src_fd)
                except OSError as exc:
                    raise CopyPolicyError("entry changed or is unavailable during copy") from exc
                try:
                    current = os.fstat(opened)
                    if (current.st_dev, current.st_ino, current.st_mode) != (before.st_dev, before.st_ino, before.st_mode):
                        raise CopyPolicyError("entry changed during copy")
                    if stat.S_ISDIR(current.st_mode):
                        os.mkdir(name, 0o700, dir_fd=dst_fd)
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dst_fd)
                        try:
                            copy_dir(opened, child, depth + 1)
                            if source:
                                os.fchmod(child, 0o777)
                        finally:
                            os.close(child)
                    else:
                        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                            raise CopyPolicyError("only regular files with one hardlink are allowed")
                        if current.st_size > max_file_bytes or totals["bytes"] + current.st_size > max_bytes:
                            raise CopyPolicyError("byte limit exceeded")
                        target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dst_fd)
                        try:
                            copied = 0
                            while data := os.read(opened, 65536):
                                copied += len(data)
                                totals["bytes"] += len(data)
                                if copied > max_file_bytes or totals["bytes"] > max_bytes:
                                    raise CopyPolicyError("byte limit exceeded")
                                # Handle short writes without reopening the checked destination.
                                view = memoryview(data)
                                while view:
                                    view = view[os.write(target, view):]
                            if os.fstat(opened).st_nlink != 1:
                                raise CopyPolicyError("hardlink changed during copy")
                            if source:
                                os.fchmod(target, 0o777 if current.st_mode & 0o111 else 0o666)
                        finally:
                            os.close(target)
                finally:
                    os.close(opened)

    copy_dir(source_fd, target_fd, 0)
    return totals


def _remove_container(name: str) -> None:
    """Never export while a timed-out/aborted container might still be modifying its output."""
    stopped = subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
    if stopped.returncode and not any(s in stopped.stderr for s in ("No such container", "No such object")):
        raise RuntimeError("cannot confirm sandbox container removal; outputs withheld")


def _execute(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Drain both Docker client streams, keeping only bounded tails in host memory."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tails = {"stdout": bytearray(), "stderr": bytearray()}
    bounds = {"stdout": 4000, "stderr": 2000}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout, bytes(tails["stdout"]), bytes(tails["stderr"]))
                for event, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(event.fd, 65536)
                    if not chunk:
                        selector.unregister(event.fileobj)
                        continue
                    tail = tails[event.data]
                    tail.extend(chunk)
                    del tail[:-bounds[event.data]]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout, bytes(tails["stdout"]), bytes(tails["stderr"]))
            proc.wait(timeout=remaining)
        return subprocess.CompletedProcess(argv, proc.returncode, bytes(tails["stdout"]), bytes(tails["stderr"]))
    except subprocess.TimeoutExpired:
        raise subprocess.TimeoutExpired(argv, timeout, bytes(tails["stdout"]), bytes(tails["stderr"])) from None
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()


def run(src: str | None, command: list[str], *, image: str = DEFAULT_IMAGE, timeout: int = 600,
        memory: str = "2g", cpus: str = "2", out_dir: Path | None = None,
        max_bytes: int = 256 * 1024 * 1024, max_entries: int = 20000,
        max_file_bytes: int = 32 * 1024 * 1024) -> dict:
    if not command or not all(isinstance(x, str) and "\0" not in x for x in command):
        raise ValueError("a command is required")
    if not image or image.startswith("-") or "\0" in image:
        raise ValueError("invalid container image")
    if timeout <= 0 or min(max_bytes, max_entries, max_file_bytes) <= 0:
        raise ValueError("timeout and copy limits must be positive")
    work = Path(tempfile.mkdtemp(prefix="walter-lab-sandbox-"))
    name = "walter-lab-" + uuid.uuid4().hex
    started = False
    stopped = False
    limits = {"max_bytes": max_bytes, "max_entries": max_entries, "max_file_bytes": max_file_bytes}
    try:
        (work / "src").mkdir()
        if src:
            source_fd = _open_directory(Path(src))
            target_fd = _open_directory(work / "src")
            try:
                _copy_tree(source_fd, target_fd, source=True, **limits)
            finally:
                os.close(source_fd)
                os.close(target_fd)
        (work / "out").mkdir()
        # Only these three directories are trusted host paths. Never chmod candidate-controlled paths.
        (work / "src").chmod(0o777)
        (work / "out").chmod(0o777)
        work.chmod(0o755)  # root owns /work; the container user cannot replace src/out
        argv = ["docker", "run", "--rm", "--pull", "never", "--name", name, "--network", "none", "--read-only", "--log-driver", "none",
                "--tmpfs", "/tmp:rw,size=256m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "256", "--memory", memory, "--cpus", cpus, "--user", "65534:65534",
                "-v", f"{work}:/work", "-w", "/work/src", "-e", "HOME=/tmp", image, *command]
        t0 = time.monotonic()
        started = True
        try:
            p = _execute(argv, timeout=timeout)
            rc, stdout, stderr, timed_out = p.returncode, p.stdout, p.stderr, False
        except FileNotFoundError:
            started = False  # Popen could not launch Docker; there is no container to stop.
            raise
        except subprocess.TimeoutExpired as exc:
            rc, stdout, stderr, timed_out = 124, exc.stdout or "", exc.stderr or "", True
        _remove_container(name)
        stopped = True
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "image": image, "command": command,
                  "rc": rc, "timed_out": timed_out, "seconds": round(time.monotonic() - t0, 1),
                  "stdout_tail": stdout[-4000:], "stderr_tail": stderr[-2000:], "network": "none",
                  "copy_policy": {**limits, "symlinks": "reject", "hardlinks": "reject", "special_files": "reject"}}
        # Validate the entire output even when the caller did not request an export.
        source_fd = _open_directory(work / "out")
        export_parent_fd = None
        export_created = False
        export_name = None
        try:
            with tempfile.TemporaryDirectory(prefix="walter-lab-export-") as staging:
                target_fd = _open_directory(Path(staging))
                try:
                    copied = _copy_tree(source_fd, target_fd, source=False, **limits)
                finally:
                    os.close(target_fd)
                result["output_entries"] = copied["entries"]
                result["output_bytes"] = copied["bytes"]
                if out_dir and copied["entries"]:
                    destination = Path(os.path.abspath(out_dir))
                    export_name = destination.name
                    export_parent_fd = _open_directory(destination.parent, create=True)
                    os.mkdir(export_name, 0o700, dir_fd=export_parent_fd)  # never merge/overwrite an existing tree
                    export_created = True
                    staging_fd = _open_directory(Path(staging))
                    target_fd = os.open(export_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=export_parent_fd)
                    try:
                        _copy_tree(staging_fd, target_fd, source=False, **limits)
                    finally:
                        os.close(staging_fd)
                        os.close(target_fd)
                    result["outputs"] = str(out_dir)
        except BaseException:
            if export_created:
                shutil.rmtree(export_name, dir_fd=export_parent_fd)
            raise
        finally:
            os.close(source_fd)
            if export_parent_fd is not None:
                os.close(export_parent_fd)
        return result
    finally:
        if started and not stopped:
            _remove_container(name)
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
  "root_home_visible": os.path.exists("/etc/walter") or os.path.exists("/instances") or os.path.exists("/walter"),
  "internet": reach("1.1.1.1", 443),
  "host_browser_api": reach("172.17.0.1", 9377),
  "host_postgres": reach("172.17.0.1", 5433),
  "can_write_root_fs": os.access("/usr", os.W_OK),
}))
'''


def probe() -> dict:
    """Proof of isolation, measured from inside: run it after any change to the sandbox."""
    r = run(None, ["python3", "-c", PROBE], timeout=120)
    if r.get("rc") != 0 or r.get("timed_out"):
        return {"ok": False, "error": r["stderr_tail"][-300:] or "sandbox probe failed"}
    try:
        seen = json.loads(r["stdout_tail"].strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": r["stderr_tail"][-300:]}
    checks = ("root_home_visible", "internet", "host_browser_api", "host_postgres", "can_write_root_fs")
    if (not isinstance(seen, dict) or type(seen.get("uid")) is not int
            or not isinstance(seen.get("env_keys"), list)
            or not all(isinstance(key, str) for key in seen["env_keys"])
            or not all(type(seen.get(key)) is bool for key in checks)):
        return {"ok": False, "error": "incomplete or invalid sandbox probe evidence"}
    bad = [k for k in checks if seen[k]]
    bad += ["unexpected uid"] if seen["uid"] != 65534 else []
    bad += ["environment leaked: " + ", ".join(seen["env_keys"])] if seen.get("env_keys") else []
    return {"ok": not bad, "seen": seen, "violations": bad}
