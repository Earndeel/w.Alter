"""Network exits of walter_browse (owner decision, 2026-10-28): page reads leave through the owner's local exit, never the
server's bare IP; key-authenticated search leaves from the server; inherited proxy settings never leak through."""
from walter_browse import facade


def test_page_reads_go_through_the_local_exit_and_keep_loopback_direct(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://somewhere-else:3128")
    env = facade._router_env({"url": "https://example.com"})
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "WALTER_BROWSE_PROXY"):
        assert env[k] == "http://127.0.0.1:1084"
    assert "127.0.0.1" in env["NO_PROXY"] and "localhost" in env["no_proxy"]   # camoufox-max / webtop APIs stay local


def test_search_leaves_from_the_server_without_any_inherited_proxy(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks5://x:1")
    env = facade._router_env({"query": "café glacé"})
    assert not any(k in env for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "WALTER_BROWSE_PROXY"))


def test_the_local_exit_can_be_overridden_for_tests(monkeypatch):
    monkeypatch.setenv("WALTER_BROWSE_EXIT_LOCAL", "http://127.0.0.1:18999")
    assert facade._router_env({"url": "https://example.com"})["WALTER_BROWSE_PROXY"] == "http://127.0.0.1:18999"
