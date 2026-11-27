"""Shared search pacing (27/11): one cadence per provider across processes, bounded retries spread over the queue."""

from __future__ import annotations

import multiprocessing
import os
import tempfile
import time
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

import search_lite as sl
from search_pace import Pacer

BRAVE_FREE = {"X-RateLimit-Limit": "1, 2000", "X-RateLimit-Policy": "1;w=1, 2000;w=2592000",
              "X-RateLimit-Remaining": "0, 1259", "X-RateLimit-Reset": "1, 303735"}


def _http_error(code: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    return urllib.error.HTTPError("https://search.test", code, "x", msg, None)


def _start_in_child(state_dir: str, queue) -> None:
    wait = Pacer("brave", state_dir=Path(state_dir)).reserve(max_wait=30)
    queue.put(time.time() + wait)


class PacerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_starts_are_spaced_across_processes(self) -> None:
        queue = multiprocessing.get_context("fork").Queue()
        procs = [multiprocessing.get_context("fork").Process(target=_start_in_child, args=(self.tmp.name, queue))
                 for _ in range(5)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(10)
        starts = sorted(queue.get(timeout=5) for _ in procs)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(all(g >= 1.05 for g in gaps), gaps)   # the default Brave cadence, shared by 5 processes

    def test_a_turn_too_far_away_is_refused_so_the_caller_takes_its_fallback(self) -> None:
        pacer = Pacer("brave", state_dir=self.dir)
        waits = [pacer.reserve(max_wait=2.5) for _ in range(5)]
        self.assertEqual(waits[:3], [0.0, waits[1], waits[2]])
        self.assertIsNone(waits[3])

    def test_the_declared_limits_set_the_cadence_and_a_spent_month_closes_the_provider(self) -> None:
        pacer = Pacer("brave", state_dir=self.dir)
        pacer.learn({**BRAVE_FREE, "X-RateLimit-Policy": "20;w=1, 20000000;w=2592000", "X-RateLimit-Remaining": "19, 5"})
        pacer.reserve(max_wait=0)
        self.assertLess(pacer.reserve(max_wait=1), 0.1)        # a paid plan (20/s) keeps the parallelism
        pacer.learn({**BRAVE_FREE, "X-RateLimit-Remaining": "0, 0"})
        self.assertIsNone(pacer.reserve(max_wait=60))          # monthly quota spent: closed until its reset

    def test_a_refusal_pushes_every_start_past_the_reset(self) -> None:
        pacer = Pacer("brave", state_dir=self.dir)
        pacer.refused({"X-RateLimit-Reset": "2, 303735"})
        wait = pacer.reserve(max_wait=10)
        self.assertGreaterEqual(wait, 2.0)


class SearchRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["WALTER_BROWSE_STATE_DIR"] = self.tmp.name
        self.saved = (sl.brave_search, sl.ddg_search, sl.QUEUE_WAIT.copy())
        self.ddg_calls = 0

        def ddg(query, count=5, on_headers=None):
            self.ddg_calls += 1
            return [{"title": "d", "url": "https://d.test", "snippet": ""}]
        sl.ddg_search = ddg

    def tearDown(self) -> None:
        sl.brave_search, sl.ddg_search = self.saved[0], self.saved[1]
        sl.QUEUE_WAIT.clear()
        sl.QUEUE_WAIT.update(self.saved[2])
        os.environ.pop("WALTER_BROWSE_STATE_DIR", None)
        self.tmp.cleanup()

    def test_a_429_is_retried_in_a_later_turn_and_brave_answers(self) -> None:
        answers = [_http_error(429, {"X-RateLimit-Reset": "1, 9"}), [{"title": "b", "url": "https://b.test", "snippet": ""}]]

        def brave(query, count=5, on_headers=None):
            item = answers.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        sl.brave_search = brave
        payload = sl.search_lite("q")
        self.assertEqual(payload["backend"], "brave")
        self.assertEqual(payload["pacing"]["retries"], 1)
        self.assertGreaterEqual(payload["pacing"]["waited_s"], 1.0)
        self.assertEqual(self.ddg_calls, 0)

    def test_temporary_errors_are_bounded_then_the_fallback_answers(self) -> None:
        calls = []

        def brave(query, count=5, on_headers=None):
            calls.append(1)
            raise urllib.error.URLError("timed out")
        sl.brave_search = brave
        payload = sl.search_lite("q")
        self.assertEqual(len(calls), sl.MAX_ATTEMPTS)
        self.assertEqual(payload["backend"], "ddg")
        self.assertTrue(payload["success"])

    def test_a_long_queue_goes_to_the_fallback_without_waiting(self) -> None:
        sl.QUEUE_WAIT["brave"] = 0.0
        Pacer("brave").reserve(max_wait=0)           # someone else holds the current turn
        sl.brave_search = lambda *a, **k: self.fail("brave must not be called")
        started = time.time()
        payload = sl.search_lite("q")
        self.assertEqual(payload["backend"], "ddg")
        self.assertLess(time.time() - started, 0.5)

    def test_a_client_error_is_not_retried(self) -> None:
        calls = []

        def brave(query, count=5, on_headers=None):
            calls.append(1)
            raise _http_error(401)
        sl.brave_search = brave
        sl.search_lite("q")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
