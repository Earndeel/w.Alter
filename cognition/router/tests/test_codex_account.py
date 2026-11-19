from walter_router.plan import codex_account as c


def test_ranked_hides_hidden_and_sorts_by_priority():
    entries = [{"slug": "b", "priority": 2}, {"slug": "hidden", "visibility": "hide", "priority": 0},
               {"slug": "a", "priority": 1}, {"slug": "a", "priority": 5}, "junk"]
    assert c.ranked(entries) == ["a", "b"]


def test_windows_named_by_duration_not_position():
    w = c.windows({"plan_type": "plus", "rate_limit": {"primary_window": {
        "used_percent": 69, "limit_window_seconds": 604800, "reset_at": 0}}})
    assert w == [{"window": "weekly", "used_percent": 69.0, "resets_at": "1970-01-01T00:00:00+00:00",
                  "detail": {"plan": "plus"}}]


def test_headers_never_fail_on_an_opaque_token():
    assert c.headers("opaque")["Authorization"] == "Bearer opaque"


def test_a_401_reads_the_grant_again_once(monkeypatch):
    """19/11: the quota reader kept an expired token and read 401 for hours while the vault's token was valid."""
    from urllib.error import HTTPError
    tokens, seen = iter(["old", "new"]), []
    monkeypatch.setattr(c, "_TOKEN", [])
    monkeypatch.setattr(c.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": next(tokens)})())

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": 1}'

    def fake(req, timeout):
        seen.append(req.headers["Authorization"])
        if req.headers["Authorization"] == "Bearer old":
            raise HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return Resp()
    monkeypatch.setattr(c, "urlopen", fake)
    assert c._get("/wham/usage") == {"ok": 1}
    assert seen == ["Bearer old", "Bearer new"]
