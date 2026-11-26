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


async def _tool_registry(settings: config.Settings, *, with_mcp: bool = True):
    """The tools the engine would offer: its own, then the Walter MCP server's (spawned for this command only)."""
    from .tools import Registry, agents, builtin
    from .tools.mcp import McpClient
    reg = Registry()
    builtin.register(reg)
    agents.register(reg)
    client = McpClient(settings, reg) if with_mcp else None
    if client:
        await client.start()
    return reg, client


def _ask_poste(settings: config.Settings, poste: str, prompt: str, timeout: float = 600) -> str:
    """One model call on a Walter Router poste (the Router picks the model) through walter-llm, under the engine's
    token. A run of channel test (WALTER_RUN_CHANNEL=test) is declared as such and counts in the test budget."""
    import httpx
    headers = {"Authorization": f"Bearer {config.env_value(settings.llm_env_file, 'WALTER_LLM_TOKEN')}"}
    if os.environ.get("WALTER_RUN_CHANNEL") == "test":
        headers["X-Walter-Channel"] = "test"
    r = httpx.post(config.LLM_URL + "/v1/chat/completions", headers=headers, timeout=timeout,
                   json={"model": poste, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def capabilities_cmd(settings: config.Settings, args) -> int:
    """Catalogue, search, contracts and search intents of the tools, as the engine sees them (lot 3e step 3)."""
    from .tools import discovery

    async def go():
        reg, client = await _tool_registry(settings)
        try:
            if args.action == "list":
                return reg.catalog(args.module or "")
            if args.action == "search":
                return reg.search(args.query or "", args.limit)
            if args.action == "describe":
                name = args.query if args.query in reg.tools else "mcp__walter__" + str(args.query)
                return reg.describe(name)
            d = discovery()
            tools = [reg._entry(t) for t in reg._searchable()]
            cards = Path(args.cards) if args.cards else None
            intents = d.load_intents(cards)
            todo = d.stale(tools, intents)
            if args.action == "stale" or args.dry_run:
                return {"tools": len(tools), "stale": todo, "cards": str(cards or d.cards_path())}
            wanted = [t for t in tools if t["name"].removeprefix("mcp__walter__") in set(todo)][: args.limit or None]
            fresh = {}
            for i in range(0, len(wanted), 20):          # one call per 20 tools: answers stay well-formed
                batch = wanted[i:i + 20]
                fresh.update(d.parse_generated(_ask_poste(settings, args.poste, d.generation_prompt(batch)), batch))
            keep = {t["name"].removeprefix("mcp__walter__") for t in tools}
            path = d.save_intents(fresh, cards, keep=keep)
            return {"generated": sorted(fresh), "missing": sorted(set(t["name"].removeprefix("mcp__walter__")
                                                                      for t in wanted) - set(fresh)),
                    "stale_left": d.stale(tools, d.load_intents(cards)), "cards": str(path), "poste": args.poste}
        finally:
            if client:
                await client.close()
    print(json.dumps(asyncio.run(go()), ensure_ascii=False, indent=1, default=str))
    return 0


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
    cap = sub.add_parser("capabilities", help="tool catalogue, search, contracts, search intents (lot 3e)")
    cap.add_argument("action", choices=["list", "search", "describe", "stale", "refresh-cards"])
    cap.add_argument("query", nargs="?", default="")
    cap.add_argument("--module", default="")
    cap.add_argument("--limit", type=int, default=8)
    cap.add_argument("--poste", default="general/L1", help="Walter Router poste that writes the intents")
    cap.add_argument("--dry-run", action="store_true")
    cap.add_argument("--cards", default="", help="intents file (default: @instance/state/core/capabilities/cards.json)")
    args = p.parse_args(argv)
    _logging(args.log_level)
    settings = config.load(Path(args.state) if args.state else None)
    if args.cmd == "serve":
        return asyncio.run(serve(settings))
    if args.cmd == "check":
        return check(settings)
    if args.cmd == "capabilities":
        return capabilities_cmd(settings, args)
    return import_dsh(settings, args)


if __name__ == "__main__":
    sys.exit(main())
