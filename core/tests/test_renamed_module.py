"""A renamed module (walter-backup -> ops, 2026-10-29): its former id resolves, its former paths are checked as
compatibility links, and the supervisor carries its open incidents over without closing or reopening them."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from walter_platform import paths

SRC = Path(__file__).resolve().parent.parent / "bin" / "walter-guardians"
_loader = importlib.machinery.SourceFileLoader("walter_guardians_renamed", str(SRC))
_spec = importlib.util.spec_from_loader("walter_guardians_renamed", _loader)
G = importlib.util.module_from_spec(_spec); _loader.exec_module(G)


class RenamedModule(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fs = Path(self.temp.name)
        self.catalog = self.fs / "catalog.json"
        self.catalog.write_text(json.dumps({"schema_version": 1, "modules": [
            {"id": "ops", "target": "ops", "legacy": "/opt/walter-backup", "aliases": ["backup"],
             "compat_links": ["/walter/backup", "/opt/walter-ops"], "manifest": "contracts/ops.json"}]}))
        env = mock.patch.dict(os.environ, {"WALTER_ROOT": "/walter"})
        env.start(); self.addCleanup(env.stop)
        (self.fs / "walter" / "ops").mkdir(parents=True)
        (self.fs / "opt").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def link(self, at, to):
        (self.fs / at.lstrip("/")).symlink_to(self.fs / to.lstrip("/"))

    def test_former_id_resolves_to_the_new_module(self):
        self.assertEqual(str(paths.module_root("backup", catalog=self.catalog, filesystem=self.fs)), "/walter/ops")
        with self.assertRaises(ValueError):
            paths.entry("nope", catalog=self.catalog)

    def test_layout_checks_every_compatibility_link(self):
        for at in ("/opt/walter-backup", "/walter/backup", "/opt/walter-ops"):
            self.link(at, "/walter/ops")
        lay = paths.layout(catalog=self.catalog, filesystem=self.fs)
        self.assertTrue(lay["ok"])
        self.assertEqual(set(lay["modules"][0]["compat_links"].values()), {"compat-link"})
        (self.fs / "opt" / "walter-ops").unlink(); (self.fs / "opt" / "walter-ops").mkdir()   # a real dir = conflict
        self.assertFalse(paths.layout(catalog=self.catalog, filesystem=self.fs)["ok"])


def test_supervisor_carries_incidents_of_a_renamed_module():
    state = {"modules": {"backup": {"ok": True}}, "open": {
        "backup:restore:disk": {"incident": {"module": "backup", "key": "restore:disk", "severity": "warning"},
                                "first_seen": "t0", "notified": True},
        "router:x": {"incident": {"module": "router", "key": "x", "severity": "info"}}}}
    out = G._renamed(json.loads(json.dumps(state)))
    assert set(out["open"]) == {"ops:restore:disk", "router:x"} and set(out["modules"]) == {"ops"}
    kept = out["open"]["ops:restore:disk"]
    assert kept["first_seen"] == "t0" and kept["notified"] is True and kept["incident"]["module"] == "ops"
    assert G._renamed(json.loads(json.dumps(out))) == out                     # idempotent
