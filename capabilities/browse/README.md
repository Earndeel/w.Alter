# Walter Browse

Shared extraction/search engine, session manager and request validation. Hermes is a thin adapter in ports/hermes; MCP calls walter_browse.browse from the same package. No core import from Hermes. The runtime uses its existing isolated Scrapling Python environment, declared as a dependency.

State: WALTER_BROWSE_STATE_DIR (default /opt/walter-browse/state); shared across harnesses. Search credentials: WALTER_BROWSE_ENV_FILE (default config/search.env, mode 0600). Secrets stay server-side. Engines: plain HTTP, static HTML, Scrapling, Camoufox and Webtop; extraction must satisfy the same semantic contract on every path.

Compatibility: old skill scripts and universal-scraper wrapper point here. hermes_adapter.py is a legacy diagnostic adapter and is excluded from the runtime-independent import boundary; normal calls do not import it. Existing fallback and extraction behavior is preserved.

Test: python -m pytest runtime/test_*.py tests -q. Set WALTER_BROWSE_STATE_DIR to an isolated test directory. No real account needed.
