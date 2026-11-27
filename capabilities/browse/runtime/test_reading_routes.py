"""Routing by intent and resource (2026-11-27): a page read does not wait for Scrapling's JSON capture, the probe's own
body is the read for Markdown/text and for pages that keep their content in <noscript>, a page that does not exist is
answered at once, a server error gets one browser attempt, a domain's record per operation kind orders the routes,
and the result reports the whole access time."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import universal_router as mod
from profile_index import ProfileIndex
from universal_extractor import ExtractionResult, ExtractionSpec, ResponseCandidate, finalize_extraction_result
from universal_router import UniversalRouter, _visible_text

READ = ExtractionSpec(expected_fields={"content": ("content", "text")})
EXTRACT = ExtractionSpec(expected_fields={"title": ("title",), "price": ("price",)})


class _Backend:
    """Records its calls; answers a readable page, or fails."""

    def __init__(self, ok: bool = True) -> None:
        self.calls = 0
        self.ok = ok

    async def extract_one(self, url: str, spec: ExtractionSpec) -> ExtractionResult:
        self.calls += 1
        if not self.ok:
            return finalize_extraction_result(url, spec, 0.0, [], error="no usable content")
        payload = {"content": "x" * 600} if "content" in spec.expected_fields else {"title": "t", "price": 1}
        cand = ResponseCandidate(url=url, method="DOM", status=200, content_type="text/html", response_bytes=600,
                                 elapsed_ms=1, payload=payload, matched_fields=set(payload), record_count=1, score=100)
        return finalize_extraction_result(url, spec, 0.0, [cand])


def _probe(status=200, ctype="text/html", body="", challenge=False):
    async def fake(url, *, timeout=0.0, content_hints=None, **_):
        return {"status": status, "content_type": ctype, "bytes": len(body), "is_json": body.lstrip().startswith("{"),
                "has_scripts": "<script" in body, "html_ratio": 0.5, "looks_spa": False, "content_present": False,
                "challenge": challenge, "redirect_target": None, "error": None, "probe_ms": 40, "body": body,
                "truncated": False}
    return fake


class ReadingRoutesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.index = ProfileIndex(Path(self.tmp.name) / "profiles.json")
        self.scrapling, self.camoufox = _Backend(), _Backend()
        self.router = UniversalRouter(scrapling_extractor=self.scrapling, camoufox_client=self.camoufox,
                                      fallback_to_webtop=False, profile_index=self.index)
        self.original = mod.http_probe

    def tearDown(self) -> None:
        mod.http_probe = self.original
        self.tmp.cleanup()

    async def _go(self, url, spec, **probe):
        mod.http_probe = _probe(**probe)
        return await self.router.extract_one(url, spec)

    async def test_a_page_read_goes_to_the_browser_without_scrapling(self) -> None:
        routed = await self._go("https://spa.test/a", READ, body="<html><body><div id=app></div></body></html>")
        self.assertEqual(routed.route, "camoufox-max")
        self.assertEqual(self.scrapling.calls, 0)

    async def test_an_extraction_still_starts_with_scrapling(self) -> None:
        routed = await self._go("https://shop.test/a", EXTRACT, body="<html><body><div id=app></div></body></html>")
        self.assertEqual(routed.route, "scrapling")
        self.assertEqual(self.camoufox.calls, 0)

    async def test_markdown_is_read_from_the_probe(self) -> None:
        md = "# API\n\n" + "The endpoint returns a JSON object with the generated video. " * 5
        routed = await self._go("https://docs.test/api.md", READ, ctype="text/markdown; charset=utf-8", body=md)
        self.assertEqual(routed.route, "static-html")
        self.assertIn("TEXT_CONTENT_DIRECT", routed.trace)
        self.assertIn("generated video", routed.result.records[0]["content"])
        self.assertEqual(self.scrapling.calls + self.camoufox.calls, 0)

    async def test_a_page_whose_content_lives_in_noscript_is_read_from_the_probe(self) -> None:
        pre = "## Pricing\n\n| Model | Input | Output |\n" + "| model-x | $0.10 | $0.40 |\n" * 20
        body = (f"<html><head><title>Pricing</title></head><body><app-root></app-root>"
                f"<noscript><pre>{pre}</pre></noscript><noscript>Enable JavaScript</noscript></body></html>")
        self.assertIn("| model-x | $0.10 |", _visible_text(body))
        routed = await self._go("https://ai.docs.test/pricing", READ, body=body)
        self.assertEqual(routed.route, "static-html")
        self.assertEqual(self.scrapling.calls + self.camoufox.calls, 0)

    async def test_noscript_noise_is_not_read_when_the_page_has_its_own_text(self) -> None:
        body = "<html><body><p>" + "Real article text. " * 40 + "</p><noscript>Please enable JavaScript</noscript>"
        text = _visible_text(body)
        self.assertIn("Real article text.", text)
        self.assertNotIn("enable JavaScript", text)

    async def test_a_missing_page_is_answered_at_once(self) -> None:
        routed = await self._go("https://reviews.test/headphones/guess", READ, status=404,
                                body="<html><body><h1>Page not found</h1></body></html>")
        self.assertEqual(routed.route, "probe-http")
        self.assertIn("NOT_FOUND", routed.trace)
        self.assertIn("page not found (HTTP 404)", routed.result.error)
        self.assertEqual(self.scrapling.calls + self.camoufox.calls, 0)

    async def test_a_404_challenge_is_not_taken_for_a_missing_page(self) -> None:
        routed = await self._go("https://guarded.test/a", READ, status=404, challenge=True, body="<html>cf</html>")
        self.assertNotIn("NOT_FOUND", routed.trace)
        self.assertEqual(routed.route, "camoufox-max")

    async def test_a_server_error_gets_one_browser_attempt(self) -> None:
        self.camoufox.ok = False
        routed = await self._go("https://app.test/a", EXTRACT, status=500, body="<html>oops</html>")
        self.assertEqual([a["backend"] for a in routed.attempts], ["camoufox-max"])
        self.assertEqual(self.scrapling.calls, 0)
        self.assertIn("SERVER_ERROR_ONE_ATTEMPT", routed.trace)

    async def test_the_domain_record_moves_a_failing_route_last_only_after_several_pages(self) -> None:
        self.camoufox.ok = False
        self.scrapling.ok = True
        shell = "<html><body><div id=app></div></body></html>"
        # One page: Scrapling worked there for an extraction; the order stays the default (Scrapling first anyway).
        # Reads: Camoufox failed on two distinct pages and never worked -> moved after Scrapling for reads.
        self.index.observe_route("https://site.test/p1", "read", "camoufox-max", False)
        self.assertEqual(self.index.domain_hint("https://site.test/x", "read")["skip"], [])
        self.index.observe_route("https://site.test/p2", "read", "camoufox-max", False)
        self.assertEqual(self.index.domain_hint("https://site.test/x", "read")["skip"], ["camoufox-max"])
        self.assertEqual(self.index.domain_hint("https://site.test/x", "extract")["skip"], [])  # per kind
        self.assertEqual(self.index.domain_hint("https://other.test/x", "read")["skip"], [])     # per domain

    async def test_the_domain_record_prefers_what_worked_on_several_pages(self) -> None:
        for path in ("p1", "p2"):
            self.index.observe_route(f"https://docs2.test/{path}", "extract", "camoufox-max", True)
        routed = await self._go("https://docs2.test/p3", EXTRACT, body="<html><body><div id=app></div></body></html>")
        self.assertEqual(routed.attempts[0]["backend"], "camoufox-max")
        self.assertEqual(routed.signals["domain_hint"]["prefer"], "camoufox-max")

    async def test_reads_are_learned_per_route(self) -> None:
        await self._go("https://spa2.test/a", READ, body="<html><body><div id=app></div></body></html>")
        await self._go("https://spa2.test/b", READ, body="<html><body><div id=app></div></body></html>")
        self.assertEqual(self.index.domain_hint("https://spa2.test/c", "read")["prefer"], "camoufox-max")

    async def test_the_result_reports_the_whole_access_and_each_attempt(self) -> None:
        self.scrapling.ok = False
        routed = await self._go("https://shop3.test/a", EXTRACT, body="<html><body><div id=app></div></body></html>")
        summary = routed.summary()
        self.assertIsNotNone(routed.total_s)
        self.assertGreaterEqual(summary["elapsed_s"], 0)
        self.assertIn("last_attempt_s", summary)
        self.assertTrue(all("elapsed_s" in a for a in summary["attempts"]))

    async def test_an_app_shell_with_menus_only_is_rendered_by_the_browser(self) -> None:
        body = ("<html><body><ul>" + "<li>Headphones</li><li>Compare</li>" * 15 + "</ul>"
                + "<script>window.__APP__={}</script>" * 800 + "</body></html>")
        routed = await self._go("https://reviews2.test/r/1", READ, body=body)
        self.assertEqual(routed.route, "camoufox-max")

    async def test_a_short_static_page_is_still_read_from_the_probe(self) -> None:
        body = "<html><body><h1>Example</h1><p>" + "A short but real page of text. " * 6 + "</p></body></html>"
        routed = await self._go("https://small.test/", READ, body=body)
        self.assertEqual(routed.route, "static-html")

    async def test_a_read_the_probe_cannot_parse_as_json_goes_to_the_browser(self) -> None:
        routed = await self._go("https://shop4.test/p", READ, body="[broken json <html>")
        self.assertEqual(routed.route, "camoufox-max")
        self.assertEqual(self.scrapling.calls, 0)


    async def test_a_read_asking_for_links_gets_the_page_anchors(self) -> None:
        spec = ExtractionSpec(expected_fields={"content": ("content",), "links": ("links",)})
        body = ("<html><body><article><p>" + "We study sparse experts at scale. " * 10 + "</p>"
                "<a href='/pdf/2501.00001'>PDF</a> <a href='https://github.com/x/y#readme'>Code</a>"
                "<a href='#top'>top</a><a href='javascript:void(0)'>x</a></article></body></html>")
        routed = await self._go("https://arxiv.test/abs/1", spec, body=body)
        self.assertEqual(routed.route, "static-html")
        links = routed.result.records[0]["links"]
        self.assertEqual([l["url"] for l in links], ["https://arxiv.test/pdf/2501.00001", "https://github.com/x/y"])
        self.assertEqual(self.scrapling.calls + self.camoufox.calls, 0)

    async def test_markdown_links_are_returned_from_a_text_resource(self) -> None:
        spec = ExtractionSpec(expected_fields={"content": ("content",), "links": ("links",)})
        md = "# Model card\n\n" + "Weights and evaluation details follow. " * 5 + "\n[Paper](https://arxiv.org/abs/1)"
        routed = await self._go("https://hf.test/README.md", spec, ctype="text/markdown", body=md)
        self.assertEqual(routed.result.records[0]["links"], [{"text": "Paper", "url": "https://arxiv.org/abs/1"}])

    async def test_a_plain_read_carries_no_links(self) -> None:
        body = "<html><body><p>" + "Plain article text. " * 20 + "<a href='/a'>a</a></p></body></html>"
        routed = await self._go("https://plain.test/a", READ, body=body)
        self.assertNotIn("links", routed.result.records[0])

if __name__ == "__main__":
    unittest.main()
