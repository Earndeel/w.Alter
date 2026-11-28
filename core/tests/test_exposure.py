"""S0 (2026-11-27): a world-readable credential file fails walter check; placeholders, examples and 0600 files do not."""
import os
import tempfile
import unittest
from pathlib import Path

from walter_platform import exposure as E


class Exposure(unittest.TestCase):
    def test_world_readable_credentials_fail_and_safe_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            bad = root / "app" / ".env"
            bad.write_text("API_KEY=Zq8v3kL0pTr7wXy2\nLOG_LEVEL=info\n")
            os.chmod(bad, 0o644)
            (root / "app" / ".env.example").write_text("API_KEY=change-this-in-production\n")
            ok = root / "app" / "prod.env"
            ok.write_text("API_KEY=Zq8v3kL0pTr7wXy2\n")
            os.chmod(ok, 0o600)
            ph = root / "app" / "dev.env"
            ph.write_text("API_KEY=\nTOKEN=${TOKEN}\nPASSWORD=changeme\n")
            os.chmod(ph, 0o644)
            r = E.scan([root])
            self.assertFalse(r["ok"])
            self.assertEqual([f["path"] for f in r["findings"]], [str(bad)])
            self.assertEqual(r["findings"][0]["lines"], 1)
            self.assertNotIn("Zq8v", repr(r))                   # never prints the value
            os.chmod(bad, 0o600)
            self.assertTrue(E.scan([root])["ok"])

    def test_known_prefixes_and_private_keys_count(self):
        self.assertEqual(E.secrets_in("x = 'sk-" + "a" * 30 + "'"), 1)
        self.assertEqual(E.secrets_in("-----BEGIN OPENSSH PRIVATE KEY-----"), 1)
        self.assertEqual(E.secrets_in("# just a comment\nNAME=walter"), 0)


if __name__ == "__main__":
    unittest.main()
