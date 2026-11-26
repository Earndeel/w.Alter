"""Lot 3e step 1 (2026-11-26): every capability is declared by the module that owns it, in its contract, and the
declarations stay consistent with the security policy and the tools' own schemas. Generated view, never a hand list."""
import json
import unittest
from pathlib import Path

from walter_platform import capabilities

CORE = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((CORE / "modules/registry.json").read_text())


class Declarations(unittest.TestCase):
    def setUp(self):
        self.decls = capabilities.declarations(REGISTRY)

    def test_every_presented_tool_is_declared_by_exactly_one_module(self):
        owners = {}
        for m in REGISTRY["modules"]:
            for tool in (m.get("presentation") or {}).get("tools") or []:
                self.assertNotIn(tool, owners, f"{tool} presented by {owners.get(tool)} and {m['id']}")
                owners[tool] = m["id"]
        undeclared = sorted(t for t, d in self.decls.items() if not d["declared"])
        self.assertEqual(undeclared, [])

    def test_the_mcp_tools_have_an_owner(self):
        # the 13 tools that had none before lot 3e (X0)
        for tool, module in {"walter_health": "core", "module_guide": "core", "module_index": "core",
                             "walter_modules": "core", "beeper_read": "core", "devboard_correct": "ops",
                             "task_create": "memory", "task_update": "memory", "tasks_list": "memory",
                             "secret_search": "secrets", "secret_reference": "secrets", "walter_web": "router",
                             "walter_profile": "soul"}.items():
            self.assertEqual(self.decls[tool]["module"], module, tool)

    def test_effects_agree_with_the_policy_classes(self):
        """`effects` is a declaration, never a permission: a tool the policy classes as outgoing or as a change must
        not be declared effect-free (the policy stays the authority; this only catches a declaration that lies)."""
        import sys
        sys.path.insert(0, str(CORE / "security"))
        from walter_security import policy
        doc = policy.load(policy.POLICY, instance_root="/nonexistent-instance")
        for tool, d in self.decls.items():
            cls = policy.classify(doc, f"mcp__walter__{tool}")
            if cls not in ("read", "unknown"):
                self.assertNotEqual(d["effects"], ["none"], f"{tool}: policy class {cls}, declared without effect")
            if "outgoing" in d["effects"]:
                self.assertEqual(cls, "outgoing", f"{tool} sends outside but the policy does not class it outgoing")

    def test_resource_keys_name_real_arguments(self):
        """A lock keyed on an argument the tool does not take would never serialise anything."""
        known ={"beeper_send_message": {"chat_id"}, "task_update": {"task_id"}, "devboard_correct": {"ref"},
                 "walter_browse": {"session_id"}, "browser_session": {"session", "site"}, "walter_web": {"service"},
                 "skill_patch": {"name"}, "skill_propose": {"name"}}
        for tool, args in known.items():
            conc = self.decls[tool]["concurrency"]
            self.assertIsInstance(conc, dict, tool)
            self.assertIn(conc["key"], args, tool)

    def test_a_device_is_one_resource_whatever_the_session(self):
        spec = self.decls["computer_use"]
        a = capabilities.lock_key(spec, {"action": "click", "session": "a"}, session="s1")
        b = capabilities.lock_key(spec, {"action": "type", "session": "b"}, session="s2")
        self.assertEqual(a, b)

    def test_same_browser_session_conflicts_across_tools(self):
        """walter_browse(session_id=x) and browser_session(session=x) drive the same browser profile."""
        a = capabilities.lock_key(self.decls["walter_browse"], {"session_id": "google-me"})
        b = capabilities.lock_key(self.decls["browser_session"], {"site": "google"})
        self.assertEqual(a, b)
        self.assertEqual(a, ("browser-session", "google-me"))

    def test_reads_run_in_parallel(self):
        for tool in ("memory_search", "memory_events", "logs_get", "vault_search", "skills_search", "beeper_read"):
            self.assertEqual(self.decls[tool]["concurrency"], "parallel", tool)
            self.assertIsNone(capabilities.lock_key(self.decls[tool], {}))


class Cursors(unittest.TestCase):
    def test_round_trip_and_refusals(self):
        token = capabilities.page_cursor("skills_index:ops", 40)
        self.assertEqual(capabilities.page_offset("skills_index:ops", token), 40)
        with self.assertRaises(ValueError):          # a cursor of another read (another domain, another tool)
            capabilities.page_offset("skills_index:memory", token)
        with self.assertRaises(ValueError):
            capabilities.page_offset("skills_index:ops", "%%%")
        import base64
        forged = base64.urlsafe_b64encode(json.dumps({"r": "skills_index:ops", "p": {"offset": 0, "domain": "x",
                                                                                     "include_archived": True}}).encode()).decode()
        with self.assertRaises(ValueError):          # never a filter or scope override
            capabilities.page_offset("skills_index:ops", forged)

    def test_cursor_is_added_beside_next_offset(self):
        page = capabilities.with_cursor("module_index:x:y", {"items": [1], "next_offset": 20})
        self.assertEqual(page["next_offset"], 20)
        self.assertEqual(capabilities.page_offset("module_index:x:y", page["cursor"]), 20)
        self.assertNotIn("cursor", capabilities.with_cursor("r", {"items": [], "next_offset": None}))


class Beeper(unittest.TestCase):
    def test_snake_case_aliases_are_added_never_renamed(self):
        import walter_beeper
        out = walter_beeper.with_aliases({"items": [{"id": "!c:x", "accountID": "wa", "preview": {"chatID": "!c:x"}}],
                                          "cursor": "c1"}, chats=True)
        chat = out["items"][0]
        self.assertEqual((chat["id"], chat["chat_id"], chat["accountID"], chat["account_id"]),
                         ("!c:x", "!c:x", "wa", "wa"))
        self.assertEqual(chat["preview"]["chat_id"], "!c:x")
        self.assertEqual(out["cursor"], "c1")


if __name__ == "__main__":
    unittest.main()
