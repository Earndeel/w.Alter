"""Real tests of conversational capabilities: real Camoufox (:9377), real keyboard paste,
real streaming over HTTP from the controlled chat UI (tests/fixtures/chat_fixture.py).

Skipped when the engine is down. Isolated state (WALTER_BROWSE_STATE_DIR = temp dir), engine
sessions prefixed ``convtest-`` and deleted at the end. This validates the mechanism on a
controlled UI, not any external service.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "runtime"))
sys.path.insert(0, str(HERE / "fixtures"))

import chat_fixture  # noqa: E402

ENGINE = os.environ.get("WALTER_CAMOUFOX_URL", "http://127.0.0.1:9377")
RUN = uuid.uuid4().hex[:6]
ALICE, BOB = f"convtest-alice-{RUN}", f"convtest-bob-{RUN}"


def _engine_up() -> bool:
    try:
        return urllib.request.urlopen(ENGINE + "/health", timeout=3).status == 200
    except OSError:
        return False


def _post(url: str, body: dict) -> None:
    urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(),
                                                  headers={"Content-Type": "application/json"}), timeout=10).read()


def _delete_session(user: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(f"{ENGINE}/sessions/{user}", method="DELETE"), timeout=10).read()
    except OSError:
        pass


@unittest.skipUnless(_engine_up(), "Camoufox engine not running")
class ConversationLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["WALTER_BROWSE_STATE_DIR"] = cls.tmp.name
        import conversation
        from profile_index import ProfileIndex
        cls.conv = conversation
        cls.index = ProfileIndex()
        chat_fixture.reset()
        cls.server, port = chat_fixture.serve(0)
        cls.base = f"http://127.0.0.1:{port}"
        cls.host = f"127.0.0.1:{port}"
        cls.timings = []

    @classmethod
    def tearDownClass(cls):
        for user in (ALICE, BOB):
            _delete_session(user)
        cls.server.shutdown()
        cls.tmp.cleanup()
        if cls.timings:
            print("\nTimings (ms):", file=sys.stderr)
            for name, t in cls.timings:
                print(f"  {name:28s} " + " ".join(f"{k}={v}" for k, v in t.items()), file=sys.stderr)

    def send(self, message, *, session=ALICE, label=None, **kw):
        out = self.conv.send(self.host, "chat", message, session=session, index=self.index, **kw)
        if label:
            self.timings.append((label, out.get("timings", {})))
        return out

    def sent_count(self) -> int:
        return sum(1 for c in chat_fixture.STATE["convs"].values() for m in c["messages"] if m["role"] == "user")

    # -- 1. first visit: discovery registers a structural recipe ---------------------------
    def test_01_discovery_registers_recipe(self):
        out = self.conv.send(None, "chat", "Bonjour, premier message", session=ALICE, index=self.index,
                             start_url=f"{self.base}/?user=alice")
        self.timings.append(("discovery", out["timings"]))
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["mode"], "discovery")
        self.assertIn("Réponse à : Bonjour, premier message", out["reply"])
        self.assertTrue(out["reply"].endswith("FIN"))
        self.assertRegex(out["url"], r"/c/[0-9a-f]{8}$")
        cap = self.index.lookup_capability(self.host, "chat")
        impl = cap["implementation"]
        self.assertEqual(impl["kind"], "conversation")
        self.assertEqual(cap["status"], "active")
        for key in ("input", "user", "reply", "busy"):
            self.assertTrue(impl[key], key)
            self.assertNotRegex(impl[key], r"\d+px|nth|:\d")   # structural selectors, no coordinates/positions
        self.assertEqual(out["input_method"], "paste")

    # -- 2. second visit: deterministic replay, same tab, multi-turn context --------------
    def test_02_replay_multiturn(self):
        before = self.sent_count()
        a = self.send("Deuxième message", label="replay #1")
        b = self.send("Troisième message", label="replay #2")
        for out in (a, b):
            self.assertTrue(out["ok"], out)
            self.assertEqual((out["mode"], out["match"]), ("replay", "recipe"))
            self.assertTrue(out["tab_reused"])
        self.assertIn("tour 2", a["reply"])
        self.assertIn("(précédent : Deuxième message)", b["reply"])
        self.assertEqual(a["url"], b["url"])
        self.assertEqual(self.sent_count(), before + 2)
        self.assertLess(b["timings"]["walter_ms"], 400)
        self.assertTrue(b["busy_seen"])                     # short settle only after the stop element was seen

    # -- 3. idempotency: one request_id = one message, the retry returns the same reply ---
    def test_03_idempotent_request(self):
        before = self.sent_count()
        rid = "tg-msg-" + RUN
        a = self.send("Message unique", request_id=rid)
        b = self.send("Message unique", request_id=rid)
        self.assertTrue(a["ok"] and b["ok"])
        self.assertTrue(b.get("duplicate"))
        self.assertEqual(a["reply"], b["reply"])
        self.assertEqual(self.sent_count(), before + 1)

    # -- 4. two simultaneous conversations, same engine session, separate tabs -----------
    def test_04_two_simultaneous_conversations(self):
        chat_fixture.STATE["token_ms"] = 40
        results = {}

        def run(name):
            results[name] = self.send(f"Parallèle {name}", conversation=name, label=f"parallel {name}")
        t0 = time.perf_counter()
        threads = [threading.Thread(target=run, args=(n,)) for n in ("p1", "p2")]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        wall = (time.perf_counter() - t0) * 1000
        chat_fixture.STATE["token_ms"] = 20
        p1, p2 = results["p1"], results["p2"]
        self.assertTrue(p1["ok"], p1)
        self.assertTrue(p2["ok"], p2)
        self.assertIn("Parallèle p1", p1["reply"])
        self.assertNotIn("p2", p1["reply"])
        self.assertIn("Parallèle p2", p2["reply"])
        self.assertNotEqual(p1["url"], p2["url"])
        self.assertEqual((p1["input_method"], p2["input_method"]), ("paste", "paste"))   # incl. the background tab
        self.assertIn("tour 1", p1["reply"])
        # generations overlap: wall time below the sum of both
        self.assertLess(wall, p1["timings"]["total_ms"] + p2["timings"]["total_ms"])

    # -- 5. long progressive reply is complete --------------------------------------------
    def test_05_long_reply(self):
        out = self.send("Une réponse long s'il te plaît", label="long reply")
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["reply"].endswith("FIN"))
        self.assertIn("mot399", out["reply"])
        self.assertGreater(out["timings"]["generation_ms"], 5000)

    # -- 6. DOM change (site update): repaired, new recipe version, then replay ----------
    def test_06_dom_change_repair(self):
        v_before = self.index.lookup_capability(self.host, "chat")["version"]
        chat_fixture.STATE["variant"] = "b"
        self.conv.close(self.host, "chat", session=ALICE)          # the update arrives on the next page load
        out = self.send("Après la mise à jour", label="repair")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["mode"], "repair")
        self.assertIn("Après la mise à jour", out["reply"])
        cap = self.index.lookup_capability(self.host, "chat")
        self.assertEqual(cap["version"], v_before + 1)
        self.assertIn("textarea", cap["implementation"]["input"])
        again = self.send("Encore après", label="replay v2")
        self.assertTrue(again["ok"], again)
        self.assertEqual((again["mode"], again["match"]), ("replay", "recipe"))
        self.assertIn("(précédent : Après la mise à jour)", again["reply"])

    # -- 7. engine session expired (30 min idle): tab recreated at the conversation URL ----
    def test_07_engine_session_expiry(self):
        prev = self.send("Avant expiration")
        _delete_session(ALICE)
        out = self.send("Après expiration", label="after engine expiry")
        self.assertTrue(out["ok"], out)
        self.assertFalse(out["tab_reused"])
        self.assertEqual(out["url"], prev["url"])
        self.assertIn("(précédent : Avant expiration)", out["reply"])

    # -- 8. service login expired: error reported, next request recovers ----------------
    def test_08_service_login_expiry(self):
        _post(self.base + "/admin/expire", {})
        bad = self.send("Message pendant expiration")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["status"], "error")
        self.assertIn("Session expirée", bad["error"])
        again = self.send("Message pendant expiration", request_id=bad["request_id"])
        self.assertTrue(again.get("duplicate"))                    # never resent under the same id
        out = self.send("Après reconnexion", label="after login expiry")
        self.assertTrue(out["ok"], out)
        self.assertIn("Après reconnexion", out["reply"])

    # -- 9. timeout → incomplete, retry resumes without resending ------------------------
    def test_09_timeout_then_resume(self):
        chat_fixture.STATE["token_ms"] = 60
        before = self.sent_count()
        rid = "slow-" + RUN
        first = self.send("Lente et long", request_id=rid, timeout_s=3)
        self.assertFalse(first["ok"])
        self.assertEqual(first["status"], "incomplete")
        self.assertTrue(first["reply"])
        self.assertNotIn("FIN", first["reply"])
        second = self.send("Lente et long", request_id=rid, timeout_s=60, label="resume")
        chat_fixture.STATE["token_ms"] = 20
        self.assertTrue(second["ok"], second)
        self.assertTrue(second["resumed"])
        self.assertTrue(second["reply"].endswith("FIN"))
        self.assertEqual(self.sent_count(), before + 1)

    # -- 10. cancellation clicks the stop element ----------------------------------------
    def test_10_cancel(self):
        chat_fixture.STATE["token_ms"] = 60
        res = {}
        th = threading.Thread(target=lambda: res.setdefault("o", self.send("Long à annuler", timeout_s=60)))
        th.start()
        time.sleep(2.0)
        self.assertTrue(self.conv.cancel(self.host, "chat", session=ALICE))
        th.join(30)
        chat_fixture.STATE["token_ms"] = 20
        out = res["o"]
        self.assertEqual(out["status"], "cancelled", out)
        self.assertFalse(out["ok"])
        nxt = self.send("Après annulation")
        self.assertTrue(nxt["ok"], nxt)

    # -- 11. isolation between users / engine sessions ------------------------------------
    def test_11_no_leak_between_sessions(self):
        cap = self.index.lookup_capability(self.host, "chat")
        impl = dict(cap["implementation"], start_url=f"{self.base}/?user=bob")
        self.index.register_capability(self.host, "chat-bob", inputs={"message": "text"},
                                       outputs={"reply": "text"}, implementation=impl)
        out = self.conv.send(self.host, "chat-bob", "Bonjour de Bob", session=BOB, index=self.index)
        self.assertTrue(out["ok"], out)
        self.assertIn("tour 1", out["reply"])
        self.assertNotIn("Après", out["reply"])
        alice_url = json.loads(next(p for p in Path(self.tmp.name, "conversations").glob("*.json")
                                    if json.loads(p.read_text()).get("session") == ALICE).read_text())["url"]
        eng = self.conv.Engine("camoufox", BOB)
        tab = eng.new_tab()
        eng.navigate(tab, alice_url)
        self.assertEqual(eng.evaluate(tab, "document.body.innerText.trim()"), "Introuvable")
        eng.call("/tab/close", {"tabId": tab})
        for p in Path(self.tmp.name, "conversations").glob("*.json"):
            raw = p.read_text()
            self.assertNotIn("sid=", raw)
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")

    # -- 12. the existing CapabilityEngine dispatches a conversational recipe -------------
    def test_12_capability_engine_dispatch(self):
        import asyncio
        from capability_engine import CapabilityEngine
        engine = CapabilityEngine(router=None, index=self.index)
        res = asyncio.run(engine.execute(self.host, "chat", {"message": "Via le moteur de capacités",
                                                             "session": ALICE}))
        self.assertEqual(res.route, "conversation")
        self.assertIsNone(res.error)
        self.assertIn("Via le moteur de capacités", res.records[0]["reply"])
        self.assertEqual(res.records[0]["mode"], "replay")

    # -- 13. busy selector the site no longer matches: quiescence, never a truncated reply --
    def test_13_stale_busy_selector(self):
        cap = self.index.lookup_capability(self.host, "chat")
        good = dict(cap["implementation"])
        self.index.bump_capability_version(self.host, "chat", implementation=dict(good, busy="button[data-gone]"),
                                           notes="test: stale busy")
        chat_fixture.STATE["token_ms"] = 400                # pauses between tokens longer than settle_ms
        try:
            out = self.send("Court mais lent", label="stale busy")
        finally:
            chat_fixture.STATE["token_ms"] = 20
            self.index.bump_capability_version(self.host, "chat", implementation=good, notes="test: restore")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["match"], "recipe")
        self.assertFalse(out["busy_seen"])
        self.assertTrue(out["reply"].endswith("FIN"), out["reply"])

    # -- 14. long conversation whose old turns are unmounted (count of user turns unchanged) --
    def test_14_virtualized_turns(self):
        chat_fixture.STATE["window"] = 4                    # 2 exchanges mounted, like ChatGPT's ~7 turns
        self.conv.close(self.host, "chat", session=ALICE)
        try:
            outs = [self.send(f"Fenêtre {i}", label=f"virtualized #{i}") for i in range(3)]
        finally:
            chat_fixture.STATE["window"] = 0
        for i, out in enumerate(outs):
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["match"], "recipe", out)
            self.assertIn(f"Réponse à : Fenêtre {i}", out["reply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
