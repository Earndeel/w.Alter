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
