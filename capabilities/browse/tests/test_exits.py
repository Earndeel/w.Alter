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


def test_a_search_returns_several_sources_by_default():
    from walter_browse import facade
    cmd = facade._build_router_command({"query": "prix bitcoin", "min_records": 1})
    assert cmd[cmd.index("--search-count") + 1] == "5"
    cmd = facade._build_router_command({"query": "prix bitcoin", "min_records": 8})
    assert cmd[cmd.index("--search-count") + 1] == "8"


# ── NordVPN exits by country (owner decision, 2026-11-11): explicit, one session = one exit, never a fallback ─────────────
import pytest


def _req(**kw):
    return facade._validate_request({"url": "https://example.com", "content_only": True, **kw})


def test_an_exit_country_becomes_a_vpn_session_for_that_country():
    r = _req(exit_country="JP")
    assert r["exit_country"] == "jp"
    cmd = facade._build_router_command(r)
    assert cmd[cmd.index("--network") + 1] == "vpn" and cmd[cmd.index("--country") + 1] == "jp"


def test_no_exit_country_keeps_the_normal_route():
    assert "--network" not in facade._build_router_command(_req())


@pytest.mark.parametrize("bad", ["france", "j", "1x", "fr;rm"])
def test_an_exit_country_must_be_a_two_letter_code(bad):
    with pytest.raises(ValueError):
        _req(exit_country=bad)


def test_search_never_takes_an_exit_country():
    with pytest.raises(ValueError):
        facade._validate_request({"query": "météo", "exit_country": "us"})
