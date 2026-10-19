"""Lot 2 Session Manager unit tests: lifecycle, isolation contract helpers,
persistence, cookie scoping, and log hygiene (no secret values)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from browse_session import (
    BrowseSession,
    SessionError,
    SessionManager,
    cookies_for_domain,
    import_cookies_file,
    redact_cookies_for_log,
)


class SessionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = SessionManager(root=self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_temporary_has_expiry(self) -> None:
        session = self.manager.create(identity="anonymous", persistent=False)
        self.assertEqual(session.network, "local")
        self.assertIsNone(session.country)
        self.assertFalse(session.persistent)
        self.assertIsNotNone(session.expires_at)
        self.assertNotIn("value", json.dumps(session.summary()))

    def test_create_persistent_has_no_expiry(self) -> None:
        session = self.manager.create(identity="personal", persistent=True)
        self.assertTrue(session.persistent)
        self.assertIsNone(session.expires_at)

    def test_invalid_identity_rejected(self) -> None:
        with self.assertRaises(SessionError):
            self.manager.create(identity="bogus")
        with self.assertRaises(SessionError):
            self.manager.create(network="bogus")
        with self.assertRaises(SessionError):
            self.manager.create(country="XX")

    def test_account_identity_accepted(self) -> None:
        session = self.manager.create(identity="account:amazon")
        self.assertEqual(session.identity, "account:amazon")

    def test_save_load_roundtrip(self) -> None:
        session = self.manager.create(session_id="persist-1", identity="personal", persistent=True)
        session.cookie_count = 3
        session.authenticated = True
        self.manager.save(
            session,
            storage_state={"cookies": [{"name": "s", "value": "V", "domain": ".x.com"}], "origins": []},
        )
        loaded = self.manager.load("persist-1")
        self.assertEqual(loaded.identity, "personal")
        self.assertTrue(loaded.persistent)
        self.assertEqual(loaded.cookie_count, 3)
        self.assertTrue(loaded.authenticated)
        # The storage file exists and holds the cookie; the state summary never logs value.
        self.assertTrue(self.manager.storage_state_path(loaded).exists())

    def test_refuse_save_temporary(self) -> None:
        session = self.manager.create(persistent=False)
        with self.assertRaises(SessionError):
            self.manager.save(session)

    def test_destroy_removes_disk_and_live(self) -> None:
        session = self.manager.create(session_id="doomed", persistent=True)
        self.manager.save(session, storage_state={"cookies": [], "origins": []})
        self.assertTrue((Path(self.tmp.name) / "doomed").exists())
        self.manager.destroy("doomed")
        self.assertFalse((Path(self.tmp.name) / "doomed").exists())
        with self.assertRaises(SessionError):
            self.manager.get("doomed")

    def test_expire_stale_destroys_only_temporary(self) -> None:
        tmp = self.manager.create(persistent=False, ttl_seconds=1)
        perm = self.manager.create(session_id="perm", persistent=True)
        tmp.expires_at = 1  # long past
        expired = self.manager.expire_stale(now=1_000_000)
        self.assertIn(tmp.id, expired)
        self.assertNotIn(perm.id, expired)
        # Persistent session still reachable
        self.assertEqual(self.manager.get("perm").id, "perm")

    def test_cookies_for_domain_scoping(self) -> None:
        cookies = [
            {"name": "a", "value": "x", "domain": ".example.com", "path": "/"},
            {"name": "b", "value": "y", "domain": "api.example.com", "path": "/"},
            {"name": "c", "value": "z", "domain": "other.org", "path": "/"},
        ]
        scoped = cookies_for_domain(cookies, "example.com")
        self.assertEqual([cookie["name"] for cookie in scoped], ["a"])
        self.assertTrue(all(c["domain"] in (".example.com", "api.example.com") for c in scoped))
        self.assertTrue(all("value" in c for c in scoped))  # needed for HTTP replay

    def test_redaction_hides_values_and_flags_sensitive(self) -> None:
        cookies = [
            {"name": "session_id", "value": "SUPERSECRET", "domain": ".x.com"},
            {"name": "pref", "value": "dark", "domain": ".x.com"},
        ]
        redacted = redact_cookies_for_log(cookies)
        assert redacted is not None
        for entry in redacted:
            self.assertNotIn("value", entry)
        self.assertTrue(any(e["sensitive"] for e in redacted))

    def test_import_cookies_file(self) -> None:
        path = Path(self.tmp.name) / "bucket.json"
        path.write_text(
            json.dumps([
                {"name": "ok", "value": "v1", "domain": ".bucket.test", "path": "/"},
                {"name": "auth", "value": "tok", "domain": ".bucket.test", "path": "/"},
            ])
        )
        session = import_cookies_file(self.manager, path, session_id="bucket")
        self.assertEqual(session.identity, "personal")
        self.assertTrue(session.persistent)
        self.assertEqual(session.cookie_count, 2)
        loaded = self.manager.load("bucket")
        self.assertEqual(loaded.cookie_count, 2)

    def test_log_event_never_contains_secret_kwargs(self) -> None:
        session = self.manager.create(session_id="log", persistent=True)
        line = self.manager.log_event(
            session,
            "SESSION_LOADED",
            cookies=[{"name": "x", "value": "TOPSECRET"}],
            token="leakme",
            domains=1,
        )
        self.assertNotIn("TOPSECRET", line)
        self.assertNotIn("leakme", line)
        self.assertIn("domains=1", line)
        self.assertIn("id=log", line)

    def test_no_global_state(self) -> None:
        # Two managers are fully independent (no singletons).
        other_root = tempfile.mkdtemp()
        other = SessionManager(root=other_root)
        a = self.manager.create(session_id="ga", persistent=True)
        self.manager.save(a, storage_state={"cookies": [], "origins": []})
        self.assertEqual(len(other.list_sessions()), 0)
        self.assertEqual(len(self.manager.list_sessions()), 1)


if __name__ == "__main__":
    unittest.main()