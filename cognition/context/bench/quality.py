"""C0 quality bench: does the walter-context payload keep what the model needs? (retention probes, LLM-judged)

At real decision points (first call of a turn, in long sessions, where walter-context compacted something):
  1. a model reads the FULL history and writes probe questions with gold answers about earlier details a continuation
     may need (paths, values, decisions, outcomes, constraints), never about the latest turn;
  2. the same answering model answers them twice: with the full history, and with the walter-context payload
     (refs allowed: an answer that points to the right context_recover ref counts as recoverable);
  3. a judge grades each answer against gold: correct / recoverable / wrong / unknown.
Pass: walter-context retention (correct + recoverable) is not significantly below full-history retention.

Calls go through walter_memory.llm (privacy guard, budget 'backfill', accounting). Default is --estimate (no call).
  walter-context quality [--samples 30] [--model openai/gpt-6-luna] [--run]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench.replay import chains, messages  # noqa: E402
from walter_context import load  # noqa: E402
from walter_context.session import Session  # noqa: E402
from walter_context.wire import MEMO, text_of  # noqa: E402

PROBE = ("You audit an assistant's memory. Below is a full conversation between a user and an AI agent (tool calls "
         "and outputs included). Write {n} short factual questions whose answers appear in the conversation BEFORE "
         "its last user message and that the agent could plausibly need to continue the work (file paths, commands, "
         "values, error causes, decisions and their reasons, user constraints, outcomes). Avoid trivia and anything "
         "only in the last user message. Reply with JSON only: [{{\"q\": \"...\", \"a\": \"...\"}}].")
ANSWER = ("Answer each question using ONLY the conversation above. Be brief. If the answer is not in the "
          "conversation say \"unknown\"; if it is only reachable through a context_recover ref, give that ref. "
          "Reply with JSON only: [\"answer 1\", \"answer 2\", ...].\n\nQuestions:\n{qs}")
JUDGE = ("Grade each candidate answer against the gold answer. Labels: correct (same meaning), recoverable (gives "
         "a context_recover ref instead of the content), wrong, unknown (says it does not know). Reply with JSON "
         "only: [\"label\", ...].\n\n{rows}")


def flatten(msgs: list[dict]) -> str:
    """A payload as plain text for a single prompt (roles, tool calls, outputs)."""
    out = []
    for m in msgs:
        role = m.get("role")
        if role == "system":
            continue
        text = text_of(m.get("content"))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            text += f"\n[tool call {tc.get('id')}] {fn.get('name')}({fn.get('arguments')})"
        if role == "tool":
            text = f"[tool output {m.get('tool_call_id')}]\n{text}"
        out.append(f"### {role}\n{text}")
    return "\n\n".join(out)


def points(conn, cfg, samples: int, seed: int) -> list[tuple[str, list[dict], list[dict]]]:
    """(chain id, full history, walter-context payload) at turn starts where something was compacted."""
    MEMO.enabled = True
    cands = []
    for ch in chains(conn, 14, 15, 60):
        msgs, calls = messages(conn, ch)
        now = [0.0]
        s = Session(cfg, clock=lambda: now[0])
        seen = None
        for idx, at, model in calls:
            now[0] = at
            s.set_model(model)
            sel = s.select(msgs[:idx])
            starts = [i for i, m in enumerate(msgs[:idx]) if m.get("role") == "user"]
            if starts and starts[-1] != seen:
                seen = starts[-1]
                z = sel.trace["zones"]
                if (z["record"] + z["compact"]) > 2000 and sel.trace["tokens"] < 200_000:
                    cands.append((ch[0]["session_id"], msgs[:idx], sel.messages))
    random.Random(seed).shuffle(cands)
    per_chain: dict[str, int] = {}
    out = []
    for c in cands:                                   # spread samples over sessions
        if per_chain.get(c[0], 0) < 3:
            per_chain[c[0]] = per_chain.get(c[0], 0) + 1
            out.append(c)
        if len(out) >= samples:
            break
    return out


def _json(text: str):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text[text.find("["):text.rfind("]") + 1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="walter-context quality")
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--probes", type=int, default=4)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run", action="store_true", help="really call the model (spends the backfill budget)")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    from walter_memory import llm
    from walter_memory.db import connection
    cfg = load()
    with connection() as conn:
        pts = points(conn, cfg, a.samples, a.seed)
    full_tok = sum(len(flatten(f)) // 4 for _, f, _ in pts)
    wc_tok = sum(len(flatten(w)) // 4 for _, _, w in pts)
    est = {"samples": len(pts), "input_tokens_est": 2 * full_tok + wc_tok, "full_mean": full_tok // max(1, len(pts)),
           "walter_context_mean": wc_tok // max(1, len(pts)),
           "balance_usd": llm.account_balance(), "budget": llm.budget_status("backfill")}
    print(json.dumps(est, default=str, indent=2))
    if not a.run:
        return 0
    ask = lambda prompt, purpose: llm.chat([{"role": "user", "content": prompt}], model=a.model,  # noqa: E731
                                           processor="walter-context.quality", privacy_class="cloud_allowed",
                                           budget="backfill", purpose=purpose)["content"]
    tally = {"full": {}, "walter-context": {}}
    rows, cost = [], 0.0
    for sid, full, wc in pts:
        try:
            probes = _json(ask(flatten(full) + "\n\n" + PROBE.format(n=a.probes), "probe"))[:a.probes]
            qs = "\n".join(f"{i + 1}. {p['q']}" for i, p in enumerate(probes))
            for name, payload in (("full", full), ("walter-context", wc)):
                answers = _json(ask(flatten(payload) + "\n\n" + ANSWER.format(qs=qs), "answer"))
                table = "\n".join(f"{i + 1}. Q: {p['q']}\n   gold: {p['a']}\n   candidate: {answers[i] if i < len(answers) else ''}"
                                  for i, p in enumerate(probes))
                labels = _json(ask(JUDGE.format(rows=table), "judge"))
                for lab in labels:
                    tally[name][lab] = tally[name].get(lab, 0) + 1
                rows.append({"session": sid, "policy": name, "probes": probes, "answers": answers, "labels": labels})
        except Exception as exc:  # noqa: BLE001 — one bad sample never stops the bench
            rows.append({"session": sid, "error": str(exc)[:300]})
    res = {k: {**v, "retention": round((v.get("correct", 0) + v.get("recoverable", 0)) / max(1, sum(v.values())), 3)}
           for k, v in tally.items()}
    print(json.dumps({"estimate": est, "result": res}, default=str, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps({"estimate": est, "result": res, "rows": rows}, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
