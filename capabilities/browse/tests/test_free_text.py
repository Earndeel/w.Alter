"""Free-text requests (27/11): facts, conclusions, quotes or links in an article are acquired as a read, not as a
Scrapling extraction waiting for JSON; data fields, listings, profiles, capabilities and explicit engines stay
structured."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "runtime")]
from walter_browse import facade  # noqa: E402

ARXIV = "https://arxiv.org/abs/2501.00001"


def _command(args):
    request = facade._validate_request(args)
    command = facade._build_router_command(request)
    fields = json.loads(command[command.index("--expected-fields") + 1])
    return request, command, fields


class FreeTextTests(unittest.TestCase):
    def test_facts_and_links_in_an_article_are_read_with_the_page_links(self):
        request, command, fields = _command({"url": ARXIV, "objective": "key facts",
                                             "expected_fields": {"facts": ["facts"], "links": ["links"]}})
        self.assertTrue(request["content_only"])
        self.assertEqual(request["free_text_fields"], ["facts", "links"])
        self.assertEqual(set(fields), {"content", "links"})
        self.assertEqual(command[command.index("--required-field") + 1], "content")

    def test_the_observed_shapes_are_reads(self):
        for shape in ({"facts": "details"}, {"key_findings": ["findings"], "title": ["title"]},
                      {"mainConclusions": ["conclusion"]}, {"quotes": ["quote"], "author": ["author"]},
                      {"summary": ["abstract"], "references": ["references"]}):
            self.assertIsNotNone(facade._validate_request({"url": ARXIV, "expected_fields": shape})["free_text_fields"],
                                 shape)

    def test_data_fields_stay_a_structured_extraction(self):
        for shape in ({"price": ["price"], "title": ["title"]}, {"rating": ["rating"], "facts": ["facts"]},
                      {"sku": ["sku"]}, {"title": ["title"], "description": ["description"]}):
            request, command, fields = _command({"url": "https://shop.test/p", "expected_fields": shape})
            self.assertFalse(request["content_only"], shape)
            self.assertIsNone(request["free_text_fields"])
            self.assertEqual(set(fields), set(shape))

    def test_a_listing_an_explicit_engine_and_a_capability_are_not_turned_into_reads(self):
        listing = facade._validate_request({"url": "https://shop.test/s", "min_records": 10,
                                            "expected_fields": {"title": ["title"], "url": ["url"]}})
        self.assertIsNone(listing["free_text_fields"])
        forced = facade._validate_request({"url": ARXIV, "mode": "scrapling", "expected_fields": {"facts": ["facts"]}})
        self.assertIsNone(forced["free_text_fields"])

    def test_a_plain_read_is_unchanged(self):
        request, command, fields = _command({"url": ARXIV, "content_only": True})
        self.assertEqual(set(fields), {"content"})
        self.assertIsNone(request["free_text_fields"])


if __name__ == "__main__":
    unittest.main()
