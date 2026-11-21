"""Walter Engine — command line (2026-11-17).

  walter-python -m walter_engine serve        run the engine: Engine API (loopback) + web interface, until SIGTERM
  walter-python -m walter_engine check        configuration, doors and state, without starting anything
  walter-python -m walter_engine import-dsh   take over DSH's conversations, bindings and web sign-in (idempotent;
                                              DSH's files are only read)

Ports and state can be redirected for a side-by-side run (`WALTER_ENGINE_STATE`, `WALTER_ENGINE_API_PORT`,
`WALTER_ENGINE_WEB_PORT`, `WALTER_ENGINE_API_STATE`, `WALTER_ENGINE_LOGIN_URL`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from . import config


def _logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def serve(settings: config.Settings) -> int:
    from . import server
    from .engine import Engine
    log = logging.getLogger("walter_engine")
    engine = Engine(settings)
    api, servers, auth = server.build(engine, settings)
    await engine.start()
    auth.write_login_url()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    tasks = [loop.create_task(s.serve()) for s in servers]
    log.info("walter engine up: api 127.0.0.1:%s, web %s:%s, state %s", settings.api_port, settings.web_host,
             settings.web_port, settings.state)
    if os.environ.get("NOTIFY_SOCKET"):
        try:
            import socket
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                addr = os.environ["NOTIFY_SOCKET"]
                s.connect("\0" + addr[1:] if addr.startswith("@") else addr)
                s.sendall(b"READY=1")
        except OSError:
            pass
    waiter = loop.create_task(stop.wait())
    done, _ = await asyncio.wait([waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
    failed = [t for t in tasks if t in done and (t.exception() if not t.cancelled() else None)]
    log.info("walter engine stopping")
    for s in servers:
        s.should_exit = True
    await engine.stop()
    await asyncio.wait(tasks, timeout=5)
    waiter.cancel()
    if failed:
        log.error("a server stopped: %s", failed[0].exception())
        return 1
    if any(t in done for t in tasks) and not stop.is_set():
        log.error("a server exited on its own (port taken?)")
        return 1
    return 0


def check(settings: config.Settings) -> int:
    rows = []

    def row(name, ok, detail=""):
        rows.append({"check": name, "ok": bool(ok), "detail": detail})

    row("instance config", not settings.config_error, settings.config_error or "readable")
    row("state", settings.state.parent.exists(), str(settings.state))
    row("instructions", not settings.instructions or Path(settings.instructions).exists(), settings.instructions)
    row("engine llm token", bool(config.env_value(settings.llm_env_file, "WALTER_LLM_TOKEN")), str(settings.llm_env_file))
    row("memory gateway token", bool(os.environ.get("WALTER_MEMORY_GATEWAY_TOKEN")
                                     or config.env_value(settings.memory_env_file, "WALTER_MEMORY_GATEWAY_TOKEN")), "")
    row("api token", settings.api_token_file.exists(), str(settings.api_token_file))
    row("python interpreter", Path(settings.python_interpreter).exists(), settings.python_interpreter)
    row("kernel runtime", (config.KERNEL_RUNTIME_DIR / "walter_kernel.py").exists(), str(config.KERNEL_RUNTIME_DIR))
    row("api loopback", settings.api_host in ("127.0.0.1", "::1", "localhost"), settings.api_host)
    row("budget levels", bool((settings.budget or {}).get("levels")), ",".join(sorted((settings.budget or {}).get("levels", {}))))
    try:
        import httpx
        for name, url in (("walter-llm", config.LLM_URL + "/health"), ("memory gateway", config.MEMORY_URL + "/health"),
                          ("context preflight", config.PREFLIGHT_URL + "/health")):
            try:
                r = httpx.get(url, timeout=3)
                row(name, r.status_code < 500, f"{url} → {r.status_code}")
            except httpx.HTTPError as e:
                row(name, False, f"{url}: {type(e).__name__}")
    except ImportError:
        row("httpx", False)
    print(json.dumps({"ok": all(r["ok"] for r in rows), "checks": rows}, ensure_ascii=False, indent=1))
    return 0 if all(r["ok"] for r in rows) else 1


def import_dsh(settings: config.Settings, args) -> int:
    from . import importer
    dsh_home = Path(args.dsh_home or settings.dsh_home)
    bindings = Path(args.bindings) if args.bindings else settings.api_state / "bindings.json"
    rep = importer.import_sessions(dsh_home, settings.sessions_dir, bindings,
                                   only=set(args.only.split(",")) if args.only else None,
                                   workspace=str(settings.workspace))
    if rep.get("open_turns"):                   # the engine's recovery closes them at its next start
        f = settings.state / "active.json"
        try:
            cur = json.loads(f.read_text())
        except (OSError, ValueError):
            cur = []
        f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        f.write_text(json.dumps(sorted(set(cur) | set(rep["open_turns"]))))
        os.chmod(f, 0o600)
    rep["open_turns"] = len(rep.get("open_turns", []))
    rep["web_secret"] = importer.import_web_secret(dsh_home, settings.state) if not args.no_secret else "skipped"
    rep["missing"] = len(rep["missing"])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if not rep["errors"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-engine")
    p.add_argument("--state", help="engine state directory (default: @instance/state/core/engine/native)")
    p.add_argument("--log-level", default=os.environ.get("WALTER_ENGINE_LOG", "info"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("check")
    imp = sub.add_parser("import-dsh")
    imp.add_argument("--dsh-home")
    imp.add_argument("--bindings", help="bindings file to read and complete (default: the engine's API state)")
    imp.add_argument("--only", help="comma-separated DSH session ids")
    imp.add_argument("--no-secret", action="store_true")
    args = p.parse_args(argv)
    _logging(args.log_level)
    settings = config.load(Path(args.state) if args.state else None)
    if args.cmd == "serve":
        return asyncio.run(serve(settings))
    if args.cmd == "check":
        return check(settings)
    return import_dsh(settings, args)


if __name__ == "__main__":
    sys.exit(main())
