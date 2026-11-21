"""Window decision at an owner-turn boundary (decision A1, 2026-11-11): relevance first, then size, cache-aware."""
from walter_context import load
from walter_context.compress import window

CFG = load()
REL = {"keep_turns": 1, "recent_s": 1800, "verbatim_budget_tokens": 8000, "thread_full_turns": 6,
       "record_budget_tokens": 6000, "min_gain_cold_tokens": 1000, "frame_tokens": 60}
NOW = 1_800_000_000_000
MIN, HOUR, DAY = 60_000, 3_600_000, 86_400_000


def turn(n, at, *, thread=None, request=None, answer=None, tool_chars=0, visible=True, pack=True):
    """One completed turn as the host annotates it: owner message, pack, a tool round, the answer."""
    tok = lambda text: len(text) // 4 if visible else 0                      # noqa: E731
    base = {"turn": n, "visible": visible}
    request, answer = request or f"request {n}", answer or f"answer {n}"
    out = [{**base, "role": "user", "src": "user", "content": request, "at": at, "tok": tok(request)}]
    if pack:
        text = "<walter-context>\nPACK " + "p" * 2000 + "\n</walter-context>"
        out.append({**base, "role": "user", "src": "walter-intake", "content": text, "at": at, "tok": tok(text),
                    **({"thread": thread} if thread else {})})
    if tool_chars:
        out.append({**base, "role": "assistant", "content": "", "at": at + 1000, "tok": 20,
                    "tool_calls": [{"id": f"call-{n}", "type": "function", "function": {"name": "read", "arguments": "{}"}}]})
        out.append({**base, "role": "tool", "tool_call_id": f"call-{n}", "content": "x" * 400, "at": at + 2000,
                    "tok": tool_chars // 4 if visible else 0})
    out.append({**base, "role": "assistant", "content": answer, "at": at + 3000, "tok": tok(answer)})
    return out


def decide(messages, **kw):
    kw.setdefault("now_ms", NOW)
    return window.decide(messages, model="walter/auto", cfg=CFG, rel=REL, **kw)


def test_next_day_message_does_not_carry_yesterdays_tool_outputs():
    """The 2026-11-11 case: a message arrives a day after a heavy turn of the same thread."""
    messages = turn(1, NOW - 2 * DAY, thread="subject:a") + turn(2, NOW - DAY, thread="subject:b", tool_chars=40_000) \
        + turn(3, NOW - DAY + HOUR, thread="subject:a", tool_chars=120_000, answer="Voici le résultat partiel.")
    out = decide(messages, plan={"thread": "subject:a"}, live_turn=4, measured_tokens=48_000)
    assert out["needed"] and out["reason"] == "cold_cache" and out["cut"] == len(messages)
    assert out["turns"] == {"verbatim": 0, "full": 2, "brief": 1, "omitted": 0, "leaving": 3}
    assert out["tokens"]["after"] < 600 and out["tokens"]["gain"] > 38_000
    content = out["content"]
    assert "## User\nrequest 3" in content and "Voici le résultat partiel." in content and "ref call-3" in content
    assert "- [" in content and "request 2 → answer 2" in content            # the other thread: one line
    assert "PACK" not in content and "xxxx" not in content                  # no stale pack, no tool payload


def test_recent_small_turn_stays_verbatim_and_a_warm_cache_is_not_broken_for_little():
    messages = turn(1, NOW - 10 * MIN, thread="subject:a") + turn(2, NOW - 2 * MIN, thread="subject:a")
    out = decide(messages, plan={"thread": "subject:a"}, live_turn=3)
    assert not out["needed"] and out["reason"] == "gain_below_threshold" and out["warm"]
    assert out["turns"]["verbatim"] == 1


def test_recent_heavy_turn_becomes_a_full_entry_even_on_another_thread():
    messages = turn(1, NOW - 3 * MIN, thread="subject:b", tool_chars=100_000)
    out = decide(messages, plan={"thread": "subject:a"}, live_turn=2)
    assert out["needed"] and out["reason"] == "gain" and out["turns"]["full"] == 1 and out["turns"]["verbatim"] == 0
    assert "## Assistant\nanswer 1" in out["content"]


def test_levels_are_recomputed_from_originals_when_the_thread_changes():
    """Turns already behind a record are rendered again from their originals: no summary of a summary."""
    old = turn(1, NOW - 3 * DAY, thread="subject:a", visible=False) + turn(2, NOW - 2 * DAY, thread="subject:b", visible=False)
    messages = old + turn(3, NOW - DAY, thread="subject:b", tool_chars=60_000)
    a = decide(messages, plan={"thread": "subject:a"}, live_turn=4, checkpoint_tokens=300)
    b = decide(messages, plan={"thread": "subject:b"}, live_turn=4, checkpoint_tokens=300)
    assert a["needed"] and b["needed"]
    assert "## User\nrequest 1" in a["content"] and "## User\nrequest 2" not in a["content"]
    assert "## User\nrequest 2" in b["content"] and "## User\nrequest 3" in b["content"] and "## User\nrequest 1" not in b["content"]
    assert "[Session record" not in a["content"][10:]


def test_record_budget_demotes_then_omits_oldest_and_says_so():
    messages = []
    for n in range(1, 81):
        messages += turn(n, NOW - (100 - n) * HOUR, thread="subject:a", request=f"request {n} " + "d " * 300,
                         answer=f"answer {n} " + "t " * 600, tool_chars=4000)
    out = decide(messages, plan={"thread": "subject:a"}, live_turn=81)
    assert out["needed"] and len(out["content"]) // 4 <= REL["record_budget_tokens"]
    assert out["turns"]["omitted"] > 0 and "earlier turns are not shown here" in out["content"]
    assert "request 80 " in out["content"] and "request 1 d" not in out["content"]


def test_pressure_folds_every_completed_turn_and_keeps_the_live_one():
    live = [{"turn": 3, "visible": True, "role": "user", "src": "user", "content": "live request", "at": NOW, "tok": 5},
            {"turn": 3, "visible": True, "role": "assistant", "content": "working", "at": NOW, "tok": 5}]
    messages = turn(1, NOW - 5 * MIN, tool_chars=200_000) + turn(2, NOW - 2 * MIN, tool_chars=200_000) + live
    out = decide(messages, live_turn=3, measured_tokens=120_000)
    assert out["needed"] and out["reason"] == "pressure" and out["prune_tools"]
    assert messages[out["cut"]]["content"] == "live request" and "live request" not in out["content"]


def test_surface_not_shaped_by_this_policy_is_left_alone():
    messages = turn(1, NOW - DAY) + turn(2, NOW - DAY + HOUR, visible=False) + turn(3, NOW - HOUR)
    assert decide(messages, live_turn=4)["reason"] == "irregular_surface"
    assert decide([], live_turn=1)["reason"] == "no_completed_turn"


def test_unknown_thread_and_unmarked_turns_fall_back_to_recency():
    messages = turn(1, NOW - DAY, pack=False, tool_chars=30_000) + turn(2, NOW - 5 * MIN, pack=False, tool_chars=40_000)
    out = decide(messages, plan=None, live_turn=3)
    assert out["needed"] and out["turns"] == {"verbatim": 0, "full": 1, "brief": 1, "omitted": 0, "leaving": 2}


def test_settings_come_from_the_configuration_file():
    assert set(window.settings()) == set(window.RELEVANCE_KEYS)
