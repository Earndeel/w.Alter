"""One-shot answers from the owner's economic text tier (L1, read from the router — GPT-6 Luna max via Codex today),
through Hermes (`hermes chat --oneshot`, its own Codex session): the proposal recommendation, the plan research on
the web. A router child process (WALTER_ROUTER_CHILD=1) so the router plugin does not route it again."""
from __future__ import annotations

import re
import subprocess

from walter_router import instance
from walter_router.serve import execution

HERMES = instance.hermes_bin()


def ask_l1(conn, prompt: str, source: str, timeout: int = 240, tools: str = "memory", max_turns: int = 1) -> str | None:
    """One-shot answer from the economic tier (L1) through Hermes, as craft_prompt does (tools: Hermes toolsets)."""
    from walter_router.serve import choose
    d = choose.pick(conn, "general", "L1")
    route = next((r for r in execution.routes(conn, d["model_id"], d.get("variant") or "")
                  if r.get("probe_ok") is not False), None)
    if not route:
        return None
    cmd = [str(HERMES), "chat", "-q", prompt, "--oneshot", "-Q", "--provider", route["hermes_provider"], "-m",
           route["model"], "-t", tools, "--max-turns", str(max_turns), "--source", source]
    if route.get("reasoning"):
        cmd += ["--reasoning", route["reasoning"]]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         env=instance.child_env(WALTER_ROUTER_CHILD="1"))
    lines = [ln for ln in re.sub(r"\x1b\[[0-9;]*m", "", out.stdout).splitlines()
             if ln.strip() and not ln.startswith(("session_id:", "⚠", "Warning:")) and "hermes doctor" not in ln]
    text = " ".join(lines).strip().strip('"')
    return text or None
