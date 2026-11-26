"""Lot 3e step 2 (2026-11-26): the MCP server holds one lock per declared resource, across every client process
(Engine, Claude Code and Codex each run their own server). Same browser session through two tools, through
walter_call, from another process: one at a time. Different keys and reads: in parallel."""
import asyncio
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from walter_platform import capabilities

CORE = Path(__file__).resolve().parents[1]
DECLS = {
    "drive": {**capabilities.DEFAULT_SPEC, "effects": ["external_state"],
              "concurrency": {"resource": "browser-session", "key": "session_id"}},
    "login": {**capabilities.DEFAULT_SPEC, "effects": ["external_state"],
              "concurrency": {"resource": "browser-session", "key": "session", "key_default": "{site}-me"}},
    "look": {**capabilities.DEFAULT_SPEC, "effects": ["none"], "concurrency": "parallel"},
}


def _server(tmp, log):
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("t")

    async def step(name, key):
        log.append(("start", name, key, time.monotonic()))
        await asyncio.sleep(0.05)
        log.append(("end", name, key, time.monotonic()))
        return "ok"

    @mcp.tool()
    async def drive(session_id: str = "") -> str:
        return await step("drive", session_id)

    @mcp.tool()
    async def login(site: str, session: str = "") -> str:
        return await step("login", session or f"{site}-me")

    @mcp.tool()
    async def look(q: str = "") -> str:
        return await step("look", q)

    from walter_capabilities import apply_toolset
    capabilities.install_locks(mcp, DECLS, lock_dir=Path(tmp))
    apply_toolset(mcp, ["drive", "look"])            # login moves behind walter_call
    return mcp


def _most_at_once(log):
    depth = most = 0
    for row in sorted(log, key=lambda r: (r[3], r[0] == "start")):
        depth += 1 if row[0] == "start" else -1
        most = max(most, depth)
    return most


class ServerLocks(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.log = []
        self.mcp = _server(self.tmp.name, self.log)
        self.call = self.mcp._tool_manager.call_tool

    def tearDown(self):
        self.tmp.cleanup()

    def run_all(self, *calls):
        async def go():
            return await asyncio.gather(*(self.call(n, a) for n, a in calls))
        return asyncio.run(go())

    def test_one_browser_session_through_two_tools_and_the_generic_door(self):
        self.run_all(("drive", {"session_id": "google-me"}),
                     ("walter_call", {"tool": "login", "arguments": {"site": "google"}}),
                     ("drive", {"session_id": "google-me"}))
        self.assertEqual(_most_at_once(self.log), 1)
        self.assertEqual(sorted(r[1] for r in self.log if r[0] == "start"), ["drive", "drive", "login"])

    def test_other_sessions_and_reads_run_in_parallel(self):
        self.run_all(("drive", {"session_id": "a"}), ("drive", {"session_id": "b"}),
                     ("look", {"q": "x"}), ("look", {"q": "y"}), ("drive", {}))
        self.assertEqual(_most_at_once(self.log), 5)

    def test_another_process_holding_the_session_is_waited_for(self):
        holder = subprocess.Popen([sys.executable, "-c", f"""
import asyncio, sys, time
sys.path.insert(0, {str(CORE)!r})
from pathlib import Path
from walter_platform import capabilities
async def main():
    locks = capabilities.ResourceLocks(interprocess=True, lock_dir=Path({self.tmp.name!r}))
    async with locks.hold(("browser-session", "google-me")):
        print("held", flush=True)
        await asyncio.sleep(0.6)
asyncio.run(main())
"""], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            t0 = time.monotonic()
            self.run_all(("drive", {"session_id": "google-me"}))
            waited = time.monotonic() - t0
            t1 = time.monotonic()
            self.run_all(("drive", {"session_id": "other"}))
            free = time.monotonic() - t1
        finally:
            holder.wait(5)
        self.assertGreater(waited, 0.3)                 # it waited for the other process
        self.assertLess(free, 0.3)                      # another session did not

    def test_a_refused_or_listing_walter_call_takes_no_lock(self):
        out = self.run_all(("walter_call", {}), ("walter_call", {"tool": "python"}))
        listing = json.loads(out[0])
        self.assertEqual([t["name"] for t in listing["tools"]], ["login"])
        self.assertEqual(self.log, [])

    def test_the_generic_door_checks_arguments_against_the_tool_schema(self):
        from mcp.server.fastmcp.exceptions import ToolError
        with self.assertRaises(ToolError) as cm:
            self.run_all(("walter_call", {"tool": "login", "arguments": {"site": "x", "sesion": "typo"}}))
        err = json.loads(str(cm.exception).split("Error executing tool walter_call: ", 1)[-1])
        self.assertEqual(err["error"], "invalid_request")
        self.assertIn("sesion", err["message"])
        self.assertIn("session", err["parameters"])
        self.assertEqual(self.log, [])


class Unit(unittest.TestCase):
    def test_lock_keys(self):
        self.assertEqual(capabilities.lock_key(DECLS["login"], {"site": "x"}), ("browser-session", "x-me"))
        self.assertIsNone(capabilities.lock_key(DECLS["drive"], {}))          # no session named: nothing shared
        self.assertIsNone(capabilities.lock_key(DECLS["look"], {"q": "x"}))
        whole = {"concurrency": {"resource": "computer-device"}}
        self.assertEqual(capabilities.lock_key(whole, {"session_id": "a"}), ("computer-device", "*"))

    def test_a_wait_is_cancellable(self):
        async def go():
            locks = capabilities.ResourceLocks()
            async with locks.hold(("r", "k")):
                waiter = asyncio.ensure_future(locks.hold(("r", "k")).__aenter__())
                await asyncio.sleep(0.01)
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
            async with locks.hold(("r", "k")):          # released cleanly: free again
                return True
        self.assertTrue(asyncio.run(go()))

    def test_resolve_call(self):
        self.assertEqual(capabilities.resolve_call({}), {"mode": "list"})
        self.assertEqual(capabilities.resolve_call({"tool": "mcp__walter__x", "arguments": '{"a": 1}'}),
                         {"mode": "run", "tool": "x", "arguments": {"a": 1}})
        self.assertEqual(capabilities.resolve_call({"tool": "x", "describe": True})["mode"], "describe")
        self.assertEqual(capabilities.resolve_call({"tool": "x", "arguments": "[1]"})["mode"], "error")
        self.assertEqual(capabilities.resolve_call({"tool": "x", "args": {}})["mode"], "error")

    def test_outcome_unknown_says_whether_a_retry_is_safe(self):
        self.assertIn("safe (idempotent)", capabilities.outcome_unknown("t", {"idempotency": "natural"}, "x")["message"])
        self.assertIn("same request_id", capabilities.outcome_unknown("t", {"idempotency": "key:request_id"}, "x")["message"])
        self.assertIn("check whether", capabilities.outcome_unknown("t", {}, "x")["message"])


if __name__ == "__main__":
    unittest.main()
