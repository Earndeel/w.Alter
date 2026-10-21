"""Invariants of the projection and the policy. Run: python -m pytest -q tests (any Python >= 3.11, stdlib only)."""
from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walter_context import load  # noqa: E402
from walter_context.compress.layers import RECORD_HEADER, Epoch, anchor, project  # noqa: E402
from walter_context.compress.policy import common_prefix, signature  # noqa: E402
from walter_context.compress.session import Session  # noqa: E402
from walter_context.compress.wire import wire_hash  # noqa: E402

CFG = load()
P = CFG.projection


def conversation(turns: int, calls: int = 3, out_chars: int = 5000) -> list[dict]:
    msgs = [{"role": "system", "content": "You are W.Alter."}]
    for t in range(turns):
        msgs.append({"role": "user", "content": f"request {t}\n\n<memory-context>recall {t}</memory-context>"})
        for k in range(calls):
            cid = f"call_{t}_{k}"
            msgs.append({"role": "assistant", "content": "", "reasoning_content": "thinking " * 50,
                         "codex_reasoning_items": [{"type": "reasoning", "encrypted_content": "x" * 400}],
                         "tool_calls": [{"id": cid, "type": "function", "function": {
                             "name": "terminal" if k % 2 else "read_file",
                             "arguments": json.dumps({"path": f"/src/f{t}{k}.py", "command": "pytest -q " + "y" * 600})}}]})
            msgs.append({"role": "tool", "tool_call_id": cid,
                         "content": json.dumps({"output": f"line {t}.{k}\n" * (out_chars // 10), "exit_code": k % 2})})
        msgs.append({"role": "assistant", "content": f"answer {t}: done."})
    return msgs


def test_pure_and_identity_without_epoch():
    m = conversation(3)
    v1, v2 = project(m, Epoch(), P), project(copy.deepcopy(m), Epoch(), P)
    assert v1.messages == m and v2.messages == v1.messages


def test_append_only_within_an_epoch():
    m = conversation(6)
    ep = Epoch(anchor(m, 1 + 8 * 2), anchor(m, 1 + 8 * 4))       # record 2 turns, compact 2 turns
    before = project(m, ep, P)
    grown = m + [{"role": "user", "content": "next"}, {"role": "assistant", "content": "ok"}]
    after = project(grown, ep, P)
    assert after.messages[:len(before.messages)] == before.messages


def test_boundary_keeps_the_compacted_prefix_cached():
    m = conversation(8)
    turn = 8                                               # 1 user + 3*(call, result) + 1 answer
    old = project(m, Epoch(None, anchor(m, 1 + turn * 3)), P)
    new = project(m, Epoch(None, anchor(m, 1 + turn * 6)), P)
    shared = 1 + 3 * (1 + 3 * 2 + 1)                      # head + 3 compacted turns
    assert new.messages[:shared] == old.messages[:shared]
    assert common_prefix(signature(new), signature(old)) > 0


def test_record_grows_by_appending():
    m = conversation(6)
    r3 = project(m, Epoch(anchor(m, 1 + 8 * 3), anchor(m, 1 + 8 * 3)), P).messages[1]["content"]
    r5 = project(m, Epoch(anchor(m, 1 + 8 * 5), anchor(m, 1 + 8 * 5)), P).messages[1]["content"]
    assert r3.startswith(RECORD_HEADER) and r5.startswith(r3) and len(r5) > len(r3)
    assert "request 2" in r3 and "recall 2" not in r3     # per-turn injections never survive a turn


def test_tool_pairs_and_refs():
    m = conversation(5)
    v = project(m, Epoch(None, anchor(m, 1 + 8 * 4)), P)
    seen = set()
    for x in v.messages:
        for tc in x.get("tool_calls") or []:
            seen.add(tc["id"])
        if x.get("role") == "tool":
            assert x["tool_call_id"] in seen
    compacted = [x for x in v.messages[:1 + 8 * 4] if x.get("role") == "tool"]
    assert compacted and all(x["tool_call_id"] in x["content"] and "context_recover" in x["content"] for x in compacted)
    assert all("reasoning_content" not in x and "codex_reasoning_items" not in x for x in v.messages[:1 + 8 * 4])


def test_live_zone_is_byte_identical():
    m = conversation(4)
    v = project(m, Epoch(None, anchor(m, 1 + 8 * 2)), P)
    tail = len(m) - (1 + 8 * 2)
    assert [wire_hash(x) for x in v.messages[-tail:]] == [wire_hash(x) for x in m[-tail:]]


def test_host_rewrite_voids_the_epoch():
    m = conversation(4)
    ep = Epoch(None, anchor(m, 1 + 8 * 2))
    rewritten = [m[0], {"role": "user", "content": "summary"}] + m[1 + 8 * 3:]
    assert project(rewritten, ep, P) is None


def _clock(t):
    return lambda: t[0]


def test_policy_compacts_a_heavy_history_and_keeps_light_ones():
    t = [0.0]
    s = Session(CFG, "gpt-6.1-sol", clock=_clock(t))
    light = conversation(3, out_chars=300)
    assert s.select(light).trace["boundary"] == ""
    s = Session(CFG, "gpt-6.1-sol", clock=_clock(t))
    heavy = conversation(12, calls=3, out_chars=12000)
    s.select(heavy[:-1 - 7])                               # mid last turn: same turn, no decision
    sel = s.select(heavy + [{"role": "user", "content": "new turn"}])
    assert sel.trace["boundary"] in ("compact", "fold"), sel.trace
    assert sel.trace["tokens"] < 0.5 * project(heavy, Epoch(), P).tokens


def test_quiet_turns_stay_append_only():
    t = [0.0]
    s = Session(CFG, "gpt-6.1-sol", clock=_clock(t))
    m = conversation(12, out_chars=12000) + [{"role": "user", "content": "go"}]
    s.select(m)
    prev = s.last
    for k in range(5):                                     # agent loop inside one turn
        t[0] += 5
        m = m + [{"role": "assistant", "content": f"step {k}"}]
        sel = s.select(m)
        assert sel.trace["boundary"] == "" and common_prefix(s.last, prev) == sum(x for _, x in prev)
        prev = s.last


def test_hard_budget_compacts_the_live_turn():
    t = [0.0]
    cfg = replace(CFG, profiles=(replace(CFG.profiles[-1], effective_budget=20000, hard_budget=30000),))
    s = Session(cfg, "x", clock=_clock(t))
    m = [{"role": "system", "content": "s"}, {"role": "user", "content": "one huge turn"}]
    for k in range(20):
        m.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{k}", "type": "function",
                  "function": {"name": "read_file", "arguments": "{}"}}]})
        m.append({"role": "tool", "tool_call_id": f"c{k}", "content": "z" * 10000})
    sel = s.select(m)
    assert sel.trace["boundary"].startswith("live") and sel.trace["tokens"] <= 20000
    assert sel.messages[1]["content"] == "one huge turn" or "one huge turn" in sel.messages[1]["content"]


def test_compact_all_keeps_the_live_request_verbatim():
    s = Session(CFG, "gpt-6.1-sol")
    m = conversation(6) + [{"role": "user", "content": "latest ask"}]
    out = s.compact_all(m)
    assert out[0] == m[0] and out[1]["content"].startswith(RECORD_HEADER) and out[-1] == m[-1]


def test_record_is_bounded_and_condensed_entries_stay_stable():
    from walter_context.compress.policy import condense
    m = conversation(60, calls=2, out_chars=2000)
    cut = len(m) - 6
    ep = Epoch(anchor(m, cut), anchor(m, cut))
    v = project(m, ep, P)
    prof = replace(CFG.profiles[-1], effective_budget=20000)
    dense = condense(m, ep, v, CFG, prof, 1.0)
    assert dense.brief is not None
    small = project(m, dense, P)
    assert small.zones["record"] <= CFG.policy.record_share * 20000
    assert "→ answer" in small.messages[1]["content"]           # brief lines keep request → answer
    # folding later turns into the condensed record only appends
    m2 = m + conversation(2)[1:] + [{"role": "user", "content": "now"}]
    later = project(m2, replace(dense, record=anchor(m2, len(m)), compact=anchor(m2, len(m))), P)
    assert later.messages[1]["content"].startswith(small.messages[1]["content"])


def test_select_is_fast_on_long_cloned_histories():
    import time
    s = Session(CFG, "gpt-6.1-sol")
    m = conversation(80, calls=3, out_chars=4000)
    for k in range(6):
        cur = copy.deepcopy(m + [{"role": "user", "content": f"turn {k}"}])
        t = time.perf_counter()
        s.select(cur)
        dt = time.perf_counter() - t
    assert dt < 0.25, dt
