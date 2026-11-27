"""Protocol tests of walter_kernel (no engine, no bubble): run with the kernel's interpreter,
    /services/python/engine-python/bin/python -m pytest -q /walter/core/engine/plugins/python/runtime/test_kernel.py
or directly (`python test_kernel.py`), which runs every test_* function."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Kernel:
    def __init__(self, workdir: str):
        env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(HERE), "HOME": workdir,
               "WALTER_KERNEL_SNAPSHOT": os.path.join(workdir, ".snapshot", "state.pkl")}
        self.p = subprocess.Popen([sys.executable, "-c", "import walter_kernel; walter_kernel.main()"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  cwd=workdir, env=env, text=True, bufsize=1)
        self.events: list[dict] = []
        self.cv = threading.Condition()
        self.host_handler = None
        threading.Thread(target=self._read, daemon=True).start()
        self.wait(lambda e: e.get("event") == "ready")

    def _read(self):
        for line in self.p.stdout:
            ev = json.loads(line)
            if ev.get("event") == "host" and self.host_handler:
                self.send({"type": "host_reply", "id": ev["id"], **self.host_handler(ev)})
            with self.cv:
                self.events.append(ev)
                self.cv.notify_all()

    def send(self, req: dict):
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()

    def wait(self, pred, timeout=20) -> dict:
        deadline = time.time() + timeout
        with self.cv:
            while True:
                for e in self.events:
                    if pred(e):
                        return e
                left = deadline - time.time()
                assert left > 0, f"timeout; events: {self.events[-5:]}"
                self.cv.wait(left)

    def run(self, cid: str, code: str, **extra) -> tuple[dict, str, list[str]]:
        self.send({"type": "execute", "id": cid, "code": code, **extra})
        done = self.wait(lambda e: e.get("event") == "done" and e.get("id") == cid, timeout=extra.get("t", 20))
        out = "".join(e["text"] for e in self.events if e.get("event") == "out" and e.get("id") == cid)
        results = [e["text"] for e in self.events if e.get("event") == "result" and e.get("id") == cid]
        return done, out, results

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(10)
        except Exception:  # noqa: BLE001
            self.p.kill()


def kernel():
    return Kernel(tempfile.mkdtemp(prefix="wk-"))


def test_persistent_namespace_and_trailing_expression():
    k = kernel()
    done, out, res = k.run("c1", "x = 40\nprint('hello')\nx + 2")
    assert done["status"] == "ok" and "hello" in out and res == ["42"]
    assert any(n["name"] == "x" for n in done["names"])
    done, _, res = k.run("c2", "x * 2")
    assert res == ["80"]
    k.close()


def test_top_level_await_and_error():
    k = kernel()
    done, _, res = k.run("a", "import asyncio\nawait asyncio.sleep(0.05)\n'ok'")
    assert done["status"] == "ok" and res == ["'ok'"]
    done, _, _ = k.run("b", "1/0")
    assert done["status"] == "error" and done["error"]["type"] == "ZeroDivisionError"
    assert "<cell" in done["error"]["traceback"]
    done, _, res = k.run("c", "'still alive'")
    assert res == ["'still alive'"]
    k.close()


def test_interrupt_async_and_sync():
    k = kernel()
    k.send({"type": "execute", "id": "s1", "code": "await asyncio.sleep(60)"})
    time.sleep(0.5)
    k.send({"type": "interrupt"})
    done = k.wait(lambda e: e.get("event") == "done" and e.get("id") == "s1", timeout=10)
    assert done["status"] == "interrupted"
    k.send({"type": "execute", "id": "s2", "code": "import time\nwhile True:\n    time.sleep(0.01)"})
    time.sleep(0.5)
    k.send({"type": "interrupt"})
    done = k.wait(lambda e: e.get("event") == "done" and e.get("id") == "s2", timeout=10)
    assert done["status"] == "interrupted"
    done, _, res = k.run("s3", "21 * 2")
    assert res == ["42"]
    k.close()


def test_bash_and_background_job():
    k = kernel()
    done, _, res = k.run("b1", "r = await bash('echo out; echo err >&2; exit 3')\n(r.code, r.stdout.strip(), r.stderr.strip())")
    assert res == ["(3, 'out', 'err')"], res
    done, _, res = k.run("b2", "j = bash('sleep 0.5; echo bg-done', background=True)\nj")
    assert done["status"] == "ok" and done.get("jobs") and "running" in res[0]
    start = k.wait(lambda e: e.get("event") == "job" and e.get("state") == "start")
    end = k.wait(lambda e: e.get("event") == "job" and e.get("job") == start["job"] and e["state"] != "start")
    assert end["state"] == "completed" and "bg-done" in end["result"]
    done, _, res = k.run("b3", "r = await bash('sleep 5', timeout=0.5)\n(r.timed_out, r.ok)")
    assert res == ["(True, False)"]
    # awaiting the launch hands the job back at once; .wait() is the explicit, bounded wait
    t0 = time.time()
    done, _, res = k.run("b4", "j2 = await bash('sleep 1; echo later', background=True)\nj2.done()")
    assert res == ["False"] and time.time() - t0 < 0.9, (res, time.time() - t0)
    done, _, res = k.run("b5", "r = await j2.wait(5)\nr.stdout.strip()")
    assert res == ["'later'"], (done, res)
    k.close()


def test_host_calls():
    k = kernel()
    seen = []

    def handler(ev):
        seen.append(ev)
        if ev["method"] == "tool" and ev["params"]["name"] == "echo":
            return {"ok": True, "result": {"echo": ev["params"]["arguments"]}}
        if ev["method"] == "search":
            return {"ok": True, "result": [{"name": "echo", "description": "echoes"}]}
        return {"ok": False, "error": "WALTER_POLICY_DENIED: no"}
    k.host_handler = handler
    done, _, res = k.run("h1", "await tools.echo(a=1)", tools=["echo"])
    assert res == ["{'echo': {'a': 1}}"], (done, res)
    done, _, res = k.run("h2", "await tools.search('ec')")
    assert "echo" in res[0]
    done, _, res = k.run("h3", "try:\n    await tools.rm(path='/')\nexcept ToolError as e:\n    msg = str(e)\nmsg")
    assert "WALTER_POLICY_DENIED" in res[0]
    done, _, res = k.run("h4", "rs = await asyncio.gather(*(tools.echo(i=i) for i in range(5)))\nlen(rs)")
    assert res == ["5"]
    assert seen[0]["cell"] == "h1"
    k.close()


def test_snapshot_restore_across_kernels():
    wd = tempfile.mkdtemp(prefix="wk-")
    k = Kernel(wd)
    code = ("import json\nbase = 10\ndata = {'a': [1, 2, 3]}\n"
            "def add(n):\n    return base + n\n"
            "class Counter:\n    def __init__(self):\n        self.n = 0\n    def inc(self):\n        self.n += base\n        return self.n\n"
            "c = Counter()\nc.inc()\nimport socket\nsock = socket.socket()")
    done, _, _ = k.run("p1", code)
    assert done["status"] == "ok", done
    k.send({"type": "snapshot", "id": "snap"})
    snap = k.wait(lambda e: e.get("id") == "snap")
    assert snap["status"] == "ok" and "sock" in snap["snapshot"]["skipped"], snap
    k.close()     # EOF → final snapshot as well
    k2 = Kernel(wd)
    k2.send({"type": "restore", "id": "r"})
    r = k2.wait(lambda e: e.get("id") == "r")
    assert r["status"] == "ok" and r["restore"]["restored"] >= 5, r
    done, _, res = k2.run("p2", "base = 100\n(add(1), c.inc(), data['a'], json.dumps([1]))")
    assert res == ["(101, 110, [1, 2, 3], '[1]')"], (done, res)
    k2.close()


def test_eof_snapshots_and_exits():
    wd = tempfile.mkdtemp(prefix="wk-")
    k = Kernel(wd)
    k.run("e1", "kept = 'yes'")
    k.close()
    assert k.p.returncode == 0
    assert (Path(wd) / ".snapshot" / "state.pkl").exists()


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t0 = time.time()
            try:
                fn()
                print(f"ok    {name} ({time.time() - t0:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name}: {exc!r}")
    sys.exit(1 if failed else 0)


def test_a_background_delegation_is_awaited_without_polling():
    """Observation 2026-11-27: `await h` waits through the engine's job wait (one blocking call per 10 min slice)."""
    import asyncio
    import walter_kernel as wk
    calls = []

    class Tools:
        async def job_output(self, **k):
            calls.append(k)
            if len(calls) == 1:
                return {"job": {"status": "running"}}
            return {"job": {"status": "completed", "result": "réponse entière"}, "output": "…fin", "truncated_before": 120}
    old = wk.tools
    wk.tools = Tools()
    try:
        h = wk.Delegation("agent-1", "job-1", "chercher")
        assert asyncio.run(h.wait(60)) == "réponse entière" and h.status == "completed"
        assert all(c["wait"] is True and c["job_id"] == "job-1" for c in calls) and len(calls) == 2
    finally:
        wk.tools = old
