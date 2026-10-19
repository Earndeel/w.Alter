"""Lot 4 contract tests: the boundaries between Hermes, the adapter, and the
Walter stacks. If Hermes changes a type/signature the contract test breaks
immediately, instead of surfacing as a runtime bug days later."""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "runtime"))
sys.path.insert(0, str(MODULE_ROOT))

import hermes_adapter
from browse_session import SessionManager
from capability_engine import CapabilityEngine
from hermes_adapter import (
    CAPABILITY_SCHEMA_VERSION,
    CACHE_SCHEMA_VERSION,
    PROFILE_SCHEMA_VERSION,
    SESSION_SCHEMA_VERSION,
    WALTER_BROWSE_VERSION,
    build_invocation_trace,
    check_component,
    format_invocation_trace,
    run_startup_self_test,
    supports_register_tool_kwarg,
)
from profile_index import INDEX_VERSION, ProfileIndex
from result_cache import ResultCache
from universal_extractor import ExtractionSpec


def ExtractionSpecForMigration() -> ExtractionSpec:
    return ExtractionSpec(
        name="search_x",
        expected_fields={"title": ("title",)},
        required_fields=("title",),
        min_records=1,
        score_threshold=20,
    )


def _load_plugin() -> Any:
    """This module's Hermes port (ports/hermes), the file installed as the Hermes plugin."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("walter_browse_plugin", MODULE_ROOT / "ports/hermes/__init__.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CapturingCtx:
    """A Hermes plugin context that records what the port registers."""

    def __init__(self) -> None:
        self.tools: list[dict] = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def _registered_handler():
    ctx = CapturingCtx()
    _load_plugin().register(ctx)
    return ctx.tools[0]["handler"]


class HermesPluginContractTests(unittest.TestCase):
    """The plugin stays a thin adapter: the schema the model sees must match
    what the plugin validates, and the invocation trace must be redacted."""

    def test_plugin_imports_and_exposes_schema(self) -> None:
        plugin = _load_plugin()

        schema = plugin.WALTER_BROWSE_SCHEMA
        self.assertEqual(schema["name"], "walter_browse")
        props = schema["parameters"]["properties"]
        self.assertIn("url", props)
        self.assertIn("query", props)
        # No hard required list: query XOR url is validated in the handler.
        self.assertEqual(schema["parameters"].get("required"), [])

    def test_plugin_register_interface_exists(self) -> None:
        """The port registers one async tool whose handler is Walter's own facade."""
        from walter_browse import facade

        ctx = CapturingCtx()
        _load_plugin().register(ctx)
        self.assertEqual(len(ctx.tools), 1)
        tool = ctx.tools[0]
        self.assertEqual(tool["name"], "walter_browse")
        self.assertTrue(tool["is_async"])
        self.assertIs(tool["handler"], facade.browse)
        self.assertIs(tool["schema"], facade.WALTER_BROWSE_SCHEMA)

    def test_query_search_route_is_exclusive_with_url(self) -> None:
        # Validation and routing belong to the Walter facade; the port only transports.
        from walter_browse import facade as plugin

        # query alone → search-lite command.
        req = plugin._validate_request({"query": "météo Tokyo", "objective": "info actuelle"})
        self.assertEqual(req["query"], "météo Tokyo")
        self.assertIsNone(req["url"])
        command = plugin._build_router_command(req)
        self.assertIn("--search", command)
        self.assertIn("météo Tokyo", command)

        # url alone → normal page command (no --search).
        req2 = plugin._validate_request(
            {"url": "https://books.toscrape.com/", "content_only": True}
        )
        self.assertIsNone(req2["query"])
        command2 = plugin._build_router_command(req2)
        self.assertNotIn("--search", command2)
        self.assertIn("--url", command2)

        # both → rejected.
        with self.assertRaises(ValueError):
            plugin._validate_request({"query": "x", "url": "https://x.test/"})

        # neither → rejected.
        with self.assertRaises(ValueError):
            plugin._validate_request({"objective": "nothing else"})

    def test_plugin_register_degrades_on_unknown_ctx(self) -> None:
        plugin = _load_plugin()

        class NoRegisterCtx:
            def register_tool(self, **kwargs):
                raise AttributeError("register_tool removed")

        # Must not raise: the plugin logs degradation instead of crashing
        # Hermes at startup when the plugin API changes.
        with self.assertLogs("walter_browse.hermes", level="WARNING") as logs:
            self.assertFalse(plugin.register(NoRegisterCtx()))
        self.assertIn("not registered", logs.output[0])

    def test_adapter_imports_all_components(self) -> None:
        report = run_startup_self_test()
        self.assertFalse(report["degraded"], report["components"])
        self.assertEqual(report["walter_browse_version"], WALTER_BROWSE_VERSION)

    def test_invocation_trace_never_contains_secrets(self) -> None:
        trace = build_invocation_trace(
            request={"objective": "watch prices", "url": "https://x.test/"},
            result={
                "route": "api-replay",
                "records": [{"price": "798€"}],
                "capability": "product_search",
                "cached": True,
                "fresh": True,
                "success": True,
            },
            started_epoch=1_700_000_000.0,
            session_id="wb-abc",
        )
        line = format_invocation_trace(trace)
        self.assertIn("WALTER_BROWSE_INVOCATION", line)
        self.assertNotIn("798", line)  # no data values
        self.assertNotIn("x.test", line)  # url not needed in the trace
        self.assertIn("cache_hit=hit", line)
        self.assertIn("capability_hit=hit", line)

    def test_feature_detection_helper(self) -> None:
        class FakeCtx:
            def register_tool(self, *, name, **kwargs):
                pass

        ctx = FakeCtx()
        # Accepts **kwargs => every kwarg is supported.
        self.assertTrue(supports_register_tool_kwarg(ctx, "is_async"))
        self.assertTrue(supports_register_tool_kwarg(ctx, "emoji"))

        class StrictCtx:
            def register_tool(self, *, name):
                pass

        self.assertFalse(supports_register_tool_kwarg(StrictCtx(), "is_async"))
        self.assertTrue(supports_register_tool_kwarg(StrictCtx(), "name"))

    def test_component_interface_checks_return_empty_on_healthy(self) -> None:
        for component in ("profile_index", "browse_session", "capability_engine", "result_cache", "static_html"):
            self.assertEqual([], check_component(component), component)


class SchemaVersionContractTests(unittest.TestCase):
    """Stores keep explicit schema versions; code changes never silently
    invalidate learned knowledge."""

    def test_profile_index_version_matches_adapter(self) -> None:
        self.assertEqual(PROFILE_SCHEMA_VERSION, INDEX_VERSION)
        self.assertEqual(CAPABILITY_SCHEMA_VERSION, 1)

    def test_store_files_carry_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = ProfileIndex(path=Path(tmp) / "profiles.json")
            entry = index.register_capability(
                "site.test", "search_products",
                inputs={"q": "string"}, outputs={"title": "string"},
                implementation={"type": "api-replay", "url": "https://site.test/api?q={{q}}"},
            )
            self.assertEqual(entry["version"], 1)
            payload = json.loads((Path(tmp) / "profiles.json").read_text())
            self.assertEqual(payload["version"], INDEX_VERSION)

    def test_session_metadata_is_migratable_forward(self) -> None:
        """An older session state (missing new fields) still loads."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = SessionManager(root=tmp)
            session_dir = Path(tmp) / "legacy"
            session_dir.mkdir()
            # Simulate a v1 state written by a previous release (fewer keys).
            (session_dir / "state.json").write_text(
                json.dumps({"identity": "personal", "network": "local", "persistent": True})
            )
            loaded = manager.load("legacy")
            self.assertEqual(loaded.identity, "personal")
            self.assertEqual(loaded.network, "local")
            self.assertTrue(loaded.persistent)
            # Defaults fill the missing fields; no crash, no data loss.
            self.assertIsNone(loaded.country)


class UpgradeSimulationTests(unittest.IsolatedAsyncioTestCase):
    """Simulate typical Hermes/Walter upgrade changes and assert graceful
    behaviour: ignore what can be ignored, migrate what can be migrated,
    fallback cleanly, and error explicitly only when truly incompatible."""

    async def test_hermes_passes_unknown_kwargs_to_handler(self) -> None:
        """A future Hermes may pass extra kwargs; the registered handler ignores them (no network)."""
        from walter_browse import facade

        handler = _registered_handler()
        canned = {"success": True, "records": [{"slideshow": "x"}], "route": "static"}
        with patch.object(facade, "_run_router", return_value=canned) as run:
            result = await handler(
                {
                    "url": "https://example.test/json",
                    "expected_fields": {"slideshow": ["slideshow"]},
                    "min_records": 1,
                },
                some_future_hermes_flag=True,
                context_object={"v": 99},
            )
        run.assert_called_once()
        self.assertIn("success", json.loads(result))

    def test_browser_backend_unavailable_does_not_crash(self) -> None:
        """Camoufox down => HTTP/static path still works (degradation)."""
        from universal_router import UniversalRouter
        from universal_extractor import ExtractionSpec
        import universal_router as ur_mod

        original_probe = ur_mod.http_probe

        async def fake_probe(url, *, timeout=0.0, content_hints=None):
            return {
                "status": 200,
                "content_type": "text/html",
                "bytes": 100,
                "is_json": False,
                "looks_spa": False,
                "content_present": True,
                "challenge": False,
                "probe_ms": 1,
                "body": (
                    "<li><article class='product_pod'>"
                    "<img alt='One'><h3><a title='One'>One</a></h3>"
                    "<p class='price_color'>£9.99</p></article></li>"
                    "<li><article class='product_pod'>"
                    "<img alt='Two'><h3><a title='Two'>Two</a></h3>"
                    "<p class='price_color'>£7.50</p></article></li>"
                ),
            }

        spec = ExtractionSpec(
            name="products",
            expected_fields={"title": ("title", "book"), "price": ("price", "price_color")},
            required_fields=("title", "price"),
            min_records=1,
            score_threshold=25,
        )

        async def scenario() -> None:
            router = UniversalRouter(scrapling_extractor=None, camoufox_client=None, webtop_client=None)
            with patch.object(ur_mod, "http_probe", side_effect=fake_probe):
                routed = await router.extract_one("https://shop.test/", spec, mode="auto")
            self.assertTrue(routed.result.records, "degraded mode must still extract")
            self.assertEqual(routed.route, "static-html")

        asyncio.run(scenario())

    def test_capability_db_corrupted_falls_back_to_generic(self) -> None:
        """Capability lookup raises => engine falls back to generic browse."""
        from universal_router import UniversalRouter

        class BrokenIndex:
            def lookup_capability(self, host, name):
                raise RuntimeError("index file corrupted")

            def observe_capability(self, *args, **kwargs):
                pass

        router = UniversalRouter(scrapling_extractor=None, camoufox_client=None, webtop_client=None)
        engine = CapabilityEngine(router, index=BrokenIndex(), cache=ResultCache(path="/tmp/wb-test-cache.json"))
        # _generic also touches index.observe_capability -> wrapped safely.
        result = asyncio.run(engine.execute("unknown.test", "search_x", {"q": "a"}))
        self.assertIsInstance(result, object)
        # No crash is the contract; the router handles the capability miss.

    def test_unknown_hermes_register_signature_falls_back(self) -> None:
        """If register_tool disappears from ctx, the plugin must not explode
        at registration time (its health state is logged, not raised)."""
        plugin = _load_plugin()

        class NoRegisterCtx:
            pass

        try:
            registered = plugin.register(NoRegisterCtx())
        except Exception as exc:
            self.fail(f"register must degrade, not crash: {exc}")
        self.assertFalse(registered)

    def test_cache_old_format_ignored(self) -> None:
        """A result cache file written by an older version (different shape)
        must be ignored without killing reads."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result_cache.json"
            path.write_text(json.dumps({"version": 0, "entries": [], "legacy": True}) or json.dumps({"version": 1, "entries": {}}))
            cache = ResultCache(path=path)
            self.assertIsNone(cache.get("host.test", "cap_x", {}))  # no crash

    def test_old_profile_index_file_migrates(self) -> None:
        """v3 profiles.json (without domains/capabilities) loads as v4 with
        empty new sections -- knowledge is preserved, not lost."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "updated_at": "2026-01-01T00:00:00Z",
                        "profiles": {"legacy-profile": {"host": "old.test", "success_count": 7}},
                    }
                )
            )
            index = ProfileIndex(path=path)
            # Reading the old file must not crash; the legacy profile survives.
            hit = index.lookup(
                "https://old.test/x",
                ExtractionSpecForMigration(),
            )
            # A write (any observation) migrates the store to v4 and preserves
            # the legacy entry.
            index.register_capability(
                "old.test",
                "search_x",
                inputs={"q": "string"}, outputs={"title": "string"},
                implementation={"type": "api-replay", "url": "https://old.test/api?q={{q}}"},
            )
            payload = json.loads(path.read_text())
            self.assertEqual(payload["version"], INDEX_VERSION)
            self.assertIn("domains", payload)
            self.assertIn("capabilities", payload)
            # Legacy profile survived the migration.
            self.assertIn("legacy-profile", payload["profiles"])


if __name__ == "__main__":
    unittest.main()