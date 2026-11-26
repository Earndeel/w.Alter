"""Search-lite backend for Walter Browse (Lot 4 correction).

A deliberately light search route: answers simple current-information
questions ("who won the GP yesterday?") with Google/Brave-style results in a
few hundred milliseconds — no LLM, no browser, no Scrapling. Escalation to
fetch/extract happens only if the caller needs page content.

Backends: Brave Search API (BRAVE_SEARCH_API_KEY, instance search env file);
Parallel Search API (PARALLEL_API_KEY through the Walter Secrets grant
`parallel`, reader `browse` — Bitwarden only, no file fallback; trial since
2026-11-22, explicit backend only: it returns dated results with long
page excerpts, so a caller can often answer without a page read).
Fallback: DuckDuckGo HTML endpoint (no key required) when Brave is absent.

The result shape is markdown-ish text (title + url + snippet), which keeps
the payload compact for the LLM.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SEARCH_TIMEOUT = 8.0
MAX_RESULTS = 8


def _read_env_key(name: str) -> str:
    """Read a key from the Hermes .env without importing python-dotenv."""
    try:
        from walter_paths import search_env_file
        env_path = search_env_file()
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except (OSError, RuntimeError):
        pass
    return os.environ.get(name, "")


PARALLEL_SEARCH_URL = "https://api.parallel.ai/v1beta/search"
PARALLEL_BETA = "search-extract-2025-10-10"
PARALLEL_EXCERPT_CHARS = 1500
PARALLEL_TIMEOUT = 25.0


def _grant_key(name: str) -> str:
    """A key Browse holds through its Walter Secrets grant (consumer `browse`). Empty when not granted."""
    if os.environ.get(name):
        return os.environ[name]
    import subprocess
    import sys
    try:
        root = subprocess.run(["walter", "path", "secrets"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if root and root not in sys.path:
        sys.path.insert(0, root)
    try:
        from walter_secrets import grants
        return grants.env_value(name, "browse")
    except Exception:  # noqa: BLE001 — not granted / vault locked: reported as not configured
        return ""


def parallel_search(query: str, count: int = 5) -> list[dict[str, str]]:
    key = _grant_key("PARALLEL_API_KEY")
    if not key:
        raise RuntimeError("PARALLEL_API_KEY is not granted to browse")
    body = json.dumps({
        "objective": query,
        "search_queries": [query],
        "max_results": min(count, MAX_RESULTS),
        "excerpts": {"max_chars_per_result": PARALLEL_EXCERPT_CHARS},
    }).encode("utf-8")
    request = urllib.request.Request(
        PARALLEL_SEARCH_URL, data=body, method="POST",
        headers={"x-api-key": key, "Content-Type": "application/json", "parallel-beta": PARALLEL_BETA},
    )
    with urllib.request.urlopen(request, timeout=PARALLEL_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    results = []
    for item in payload.get("results") or []:
        url = item.get("url") or ""
        if not url:
            continue
        excerpt = "\n".join(e for e in (item.get("excerpts") or []) if e).strip()
        row = {"title": item.get("title") or "", "url": url, "snippet": excerpt[:PARALLEL_EXCERPT_CHARS]}
        if item.get("publish_date"):
            row["published"] = item["publish_date"]
        results.append(row)
    return results


def brave_search(query: str, count: int = 5) -> list[dict[str, str]]:
    key = _read_env_key("BRAVE_SEARCH_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not configured")
    params = urllib.parse.urlencode({"q": query, "count": min(count, MAX_RESULTS)})
    request = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": key},
    )
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    results = []
    for item in (payload.get("web") or {}).get("results", []) or []:
        title = item.get("title") or ""
        url = item.get("url") or ""
        description = item.get("description") or ""
        if url:
            results.append({"title": title, "url": url, "snippet": description})
    return results


def ddg_search(query: str, count: int = 5) -> list[dict[str, str]]:
    """No-key fallback: DuckDuckGo HTML endpoint (lightweight)."""
    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    request = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?{params}",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT) as response:
        html = response.read().decode("utf-8", errors="replace")
    # Very small parser: result links look like
    # <a class="result__a" href="//duckduckgo.com/l/?uddg=<urlencoded>&...">Title</a>
    import re

    results: list[dict[str, str]] = []
    for match in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html):
        href, title_html = match.group(1), match.group(2)
        url = href
        if "uddg=" in href:
            url = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&", 1)[0])
        title = re.sub(r"<[^>]+>", "", title_html)
        title = re.sub(r"\s+", " ", title).strip()
        if url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= count:
            break
    return results


def search_lite(
    query: str,
    *,
    count: int = 5,
    backend: str = "auto",
) -> dict[str, Any]:
    """Run the search-lite route. No LLM, no browser.

    Returns structured data:
        {success, query, count, results: [{title, url, snippet}], backend, elapsed_ms}
    """
    started = time.perf_counter()
    used_backend = "none"
    results: list[dict[str, str]] = []
    error: str | None = None
    if backend == "parallel":
        try:
            results = parallel_search(query, count=count)
            used_backend = "parallel"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
            results = []
    if backend in ("auto", "brave"):
        try:
            results = brave_search(query, count=count)
            used_backend = "brave"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
            results = []
    if not results and backend in ("auto", "ddg"):
        try:
            results = ddg_search(query, count=count)
            used_backend = "ddg"
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
    return {
        "success": bool(results),
        "query": query,
        "count": len(results),
        "results": results,
        "backend": used_backend,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": error,
    }


def results_to_text(payload: dict[str, Any]) -> str:
    """Compact text form for the LLM (escapes into one JSON string field)."""
    lines = [f"search:{payload.get('query', '')} (backend={payload.get('backend')}, {payload.get('elapsed_ms')}ms)"]
    for index, item in enumerate(payload.get("results", []), start=1):
        lines.append(
            f"{index}. {item.get('title', '')}\n   {item.get('url', '')}\n   {item.get('snippet', '')}"
        )
    return "\n".join(lines)