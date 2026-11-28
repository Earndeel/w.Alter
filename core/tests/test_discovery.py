"""Lot 3e step 3 (2026-11-26): capability discovery. Cards are derived, never written by hand: a generated intent
is used only while its source (name, description, parameters, declaration) is unchanged, and a hand-edited entry is
ignored. Offline: no model, no service."""
import json
import tempfile
import unittest
from pathlib import Path

from walter_platform import discovery as D

TOOLS = [
    {"name": "mcp__walter__walter_health", "description": "Is everything working? Status and health of the stack.",
     "parameters": {"type": "object", "properties": {}}, "module": "core",
     "spec": {"effects": ["none"], "produces": [], "consumes": []}},
    {"name": "mcp__walter__vault_search", "description": "Search the Raw Vault: photos, pictures, documents (quotes, invoices).",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "kind": {"type": "string"}}},
     "module": "vault", "spec": {"effects": ["none"], "produces": ["object"], "consumes": []}},
    {"name": "walter_browse_like", "description": "Look something up on the web: search the internet or read a page.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}, "module": "browse",
     "spec": {"effects": ["external_state"]}},
    {"name": "write", "description": "Write a file.", "parameters": {"type": "object", "properties": {
        "file_path": {"type": "string"}}}, "module": "core", "spec": {"effects": ["local_write"]}},
]


def _entry(tool, **intents):
    e = {"source": D.source_hash(tool), **{k: intents.get(k, []) for k in D.INTENTS_PER_TOOL}}
    e["card"] = D._entry_hash(e)
    return e


class Words(unittest.TestCase):
    def test_accents_case_stop_words_and_plurals(self):
        self.assertEqual(D.tokens("Les Mémoires d'été"), ["memoir", "ete"])
        self.assertEqual(D.tokens("photos"), D.tokens("photo"))

    def test_french_words_also_read_as_the_tools_english(self):
        q = D.query_tokens("retrouve la photo")
        self.assertIn(D._stem("find"), q)
        self.assertIn(D._stem("image"), q)


class Search(unittest.TestCase):
    def test_french_needs_find_english_tools(self):
        idx = D.Index(TOOLS)
        for need, tool in (("vérifie si tout fonctionne", "mcp__walter__walter_health"),
                           ("retrouve la photo du devis", "mcp__walter__vault_search"),
                           ("cherche sur internet les horaires", "walter_browse_like")):
            self.assertEqual(idx.search(need, 3)[0]["name"], tool, need)

    def test_rows_carry_owner_and_effects_and_respect_the_limit(self):
        rows = D.Index(TOOLS).search("file", 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["name"], rows[0]["module"], rows[0]["effects"]), ("write", "core", ["local_write"]))

    def test_guide_lines_naming_the_tool_join_its_card(self):
        texts = {"vault": "- `vault_search(text)` — the scanned bill of the plumber, any receipt"}
        self.assertEqual(D.Index(TOOLS, texts).search("receipt", 1)[0]["name"], "mcp__walter__vault_search")
        self.assertEqual(D.Index(TOOLS).search("receipt", 1), [])

    def test_an_empty_need_lists_tools_by_name(self):
        self.assertEqual([r["name"] for r in D.Index(TOOLS).search("", 2)],
                         ["mcp__walter__vault_search", "mcp__walter__walter_health"])


class GeneratedIntents(unittest.TestCase):
    def test_fresh_intents_count_and_stale_ones_are_ignored(self):
        tool = TOOLS[3]
        fresh = {"write": _entry(tool, intents_fr=["enregistre ce brouillon sur le disque"])}
        self.assertEqual(D.Index(TOOLS, intents=fresh).search("brouillon", 1)[0]["name"], "write")
        changed = [{**t, "description": "Write a file (new wording)."} if t["name"] == "write" else t for t in TOOLS]
        self.assertEqual(D.Index(changed, intents=fresh).search("brouillon", 1), [])
        self.assertEqual(D.stale(changed, fresh), sorted(["walter_health", "vault_search", "walter_browse_like", "write"]))
        self.assertEqual(D.Index(changed, intents=fresh).cards[3]["intents"], "stale")

    def test_the_source_is_the_short_name_whatever_the_door(self):
        a = {**TOOLS[0]}
        b = {**TOOLS[0], "name": "walter_health"}
        self.assertEqual(D.source_hash(a), D.source_hash(b))

    def test_a_declaration_change_makes_intents_stale(self):
        tool = TOOLS[0]
        e = _entry(tool, keywords=["status"])
        moved = {**tool, "spec": {**tool["spec"], "effects": ["record"]}}
        self.assertEqual(D.stale([tool], {"walter_health": e}), [])
        self.assertEqual(D.stale([moved], {"walter_health": e}), ["walter_health"])

    def test_cache_round_trip_hand_edits_are_ignored_and_removed_tools_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cards.json"
            answer = json.dumps({"cards": {"write": {"intents_fr": ["écris ça"], "intents_en": ["save it"],
                                                     "keywords": ["file"]},
                                           "not_asked": {"intents_fr": ["x"]}}})
            got = D.parse_generated("Voici : " + answer, [TOOLS[3]])
            self.assertEqual(list(got), ["write"])                       # only the tools it was asked about
            D.save_intents(got, p)
            self.assertEqual(D.load_intents(p)["write"]["intents_fr"], ["écris ça"])
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            doc = json.loads(p.read_text())
            doc["tools"]["write"]["intents_fr"].append("tapé à la main")   # a hand edit
            p.write_text(json.dumps(doc))
            self.assertEqual(D.load_intents(p), {})
            D.save_intents(got, p)
            D.save_intents({}, p, keep={"other"})
            self.assertEqual(D.load_intents(p), {})

    def test_a_malformed_answer_gives_nothing(self):
        self.assertEqual(D.parse_generated("no json here", TOOLS), {})
        self.assertEqual(D.parse_generated('{"cards": []}', TOOLS), {})

    def test_the_prompt_carries_only_the_source(self):
        prompt = D.generation_prompt([TOOLS[1]])
        self.assertIn("### vault_search", prompt)
        self.assertIn("Raw Vault", prompt)
        self.assertNotIn("mcp__walter__", prompt)


if __name__ == "__main__":
    unittest.main()
