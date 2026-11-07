"""Entrance A/B bench: does a model still get what it needs from a REDUCED tool output? (LLM-judged)

Real cases from Claude Code transcripts: a large tool output (what the model saw), the owner's request in force, the
tool call, and what the agent wrote next (what it actually used). Then:
  1. a model reads the FULL output + the agent's next message and writes probe questions with gold answers: details
     of the output the agent needed or would plausibly need next (values, paths, error causes, statuses);
  2. the same model answers them twice, from the FULL output (A) and from the entrance reduction (B);
     B may answer "recover" when the excerpt says where the original is and the answer is not in it;
  3. a judge grades each answer against gold: correct / recover / wrong / unknown.
`wrong` on B is the dangerous case (silent loss); `recover` costs a re-read; both are reported with the token cut.

Calls go through walter_memory.llm with a Walter Router poste (no model id in code), privacy guard, budget
'backfill'. Default is an estimate (no call). Cases whose output looks like it holds a secret are skipped.
  walter-python bench/entrance.py [--samples 30] [--poste document] [--run] [--json FILE]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walter_context.compress import entrance as en  # noqa: E402
from walter_context.compress.digest import args_summary  # noqa: E402

PROBE = ("An AI agent ran a tool, then continued its work. Below: the user's request in force, the tool call, the "
         "FULL tool output, and what the agent wrote next. Write {n} short factual questions whose answers are in the "
         "tool output and that the agent needed, or would plausibly need, for its next steps (values, paths, counts, "
         "error causes, statuses, names). Prefer details its next message relies on; avoid trivia. "
         "Reply with JSON only: [{{\"q\": \"...\", \"a\": \"...\"}}].")
ANSWER = ("Answer each question using ONLY the tool output above. Be brief. If the output shown does not contain the "
          "answer but says where the full original can be read again, answer \"recover\". Otherwise, if the answer "
          "is not there, answer \"unknown\". Reply with JSON only: [\"answer 1\", \"answer 2\", ...].\n\n"
          "Questions:\n{qs}")
JUDGE = ("Grade each candidate answer against the gold answer. Labels: correct (same meaning, small wording "
         "differences are fine), recover (the candidate says it would re-read the original), wrong (a different or "
         "invented answer), unknown (says it does not know). Reply with JSON only: [\"label\", ...].\n\n{rows}")
CLIP = 1500


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def cases(cfg: en.Entrance, days: int, root: str) -> list[dict]:
    """Large, non-exempt, non-persisted tool outputs with their request, call and the agent's next message."""
    from walter_memory import privacy
    out, cut = [], time.time() - days * 86400
    for f in glob.glob(f"{root}/*/*.jsonl"):
        if os.path.getmtime(f) < cut:
            continue
        lines = []
        for line in open(f):
            try:
                lines.append(json.loads(line))
            except ValueError:
                continue
        calls, request = {}, ""
        for i, e in enumerate(lines):
            msg = e.get("message") or {}
            content = msg.get("content")
            if e.get("type") == "user" and isinstance(content, str) and not e.get("isMeta"):
                request = content
            if not isinstance(content, list):
                continue
            for b in content:
                if b.get("type") == "text" and e.get("type") == "user" and not e.get("isMeta"):
                    request = b.get("text") or request
                if b.get("type") == "tool_use":
                    calls[b["id"]] = (b["name"], b.get("input") or {})
                if b.get("type") != "tool_result" or b.get("tool_use_id") not in calls:
                    continue
                raw = e.get("toolUseResult")
                if isinstance(raw, dict) and raw.get("persistedOutputPath"):
                    continue
                tool, args = calls[b["tool_use_id"]]
                text = _text(b.get("content"))
                cut_ = en.reduce(tool, text, b["tool_use_id"], cfg, str(args.get("file_path") or ""))
                if cut_ is None or any(c == "secret" for c, _ in privacy.detect(text)):
                    continue
                nxt = next((_text(x.get("message", {}).get("content")) for x in lines[i + 1:i + 8]
                            if x.get("type") == "assistant" and _text(x.get("message", {}).get("content")).strip()), "")
                out.append({"call_id": b["tool_use_id"], "tool": tool, "request": request[:CLIP],
                            "call": args_summary(tool, json.dumps(args, ensure_ascii=False), 300),
                            "full": text, "reduced": cut_["text"], "next": nxt[:CLIP]})
    return out


def frame(c: dict, output: str) -> str:
    return (f"User request in force:\n{c['request']}\n\nTool call: {c['call']}\n\nTool output:\n<<<\n{output}\n>>>")


def _json(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0) if m else text)


def run_case(c: dict, ask, n: int) -> dict:
    probes = _json(ask(frame(c, c["full"]) + f"\n\nWhat the agent wrote next:\n{c['next'] or '(nothing)'}\n\n"
                       + PROBE.format(n=n), "probe"))[:n]
    qs = "\n".join(f"{i + 1}. {p['q']}" for i, p in enumerate(probes))
    row = {"call_id": c["call_id"], "tool": c["tool"], "full_chars": len(c["full"]), "reduced_chars": len(c["reduced"])}
    for arm, output in (("A_full", c["full"]), ("B_reduced", c["reduced"])):
        answers = _json(ask(frame(c, output) + "\n\n" + ANSWER.format(qs=qs), "answer"))
        table = "\n".join(f"{i + 1}. Q: {p['q']}\n   gold: {p['a']}\n   candidate: {answers[i] if i < len(answers) else ''}"
                          for i, p in enumerate(probes))
        row[arm] = [str(x).lower().strip() for x in _json(ask(JUDGE.format(rows=table), "judge"))][:len(probes)]
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--probes", type=int, default=3)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--poste", default="document", help="Walter Router task (the router picks the model)")
    ap.add_argument("--usd-per-m", type=float, default=4.0, help="estimate only: blended price of the routed model")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run", action="store_true", help="really call the model (spends the backfill budget)")
    ap.add_argument("--json", help="write rows (labels and sizes only, no content) to this file")
    a = ap.parse_args(argv)
    cfg = en.load()
    pool = cases(cfg, a.days, a.root)
    random.Random(a.seed).shuffle(pool)
    pts = pool[: a.samples]
    tok = lambda s: len(s) / cfg.chars_per_token        # noqa: E731
    est_in = sum(2 * tok(c["full"]) + tok(c["reduced"]) + tok(c["next"]) + 3 * tok(c["request"]) + 1500 for c in pts)
    est = {"poste": a.poste, "pool": len(pool), "samples": len(pts), "input_tokens_est": round(est_in),
           "usd_est": round(est_in / 1e6 * a.usd_per_m * 1.3, 2),     # +30 % for outputs
           "chars_full": sum(len(c["full"]) for c in pts), "chars_reduced": sum(len(c["reduced"]) for c in pts)}
    print(json.dumps(est, indent=2))
    if not a.run:
        return 0
    from walter_memory import llm
    ask = lambda prompt, purpose: llm.chat([{"role": "user", "content": prompt}], poste=a.poste,  # noqa: E731
                                           processor="walter-context.entrance-bench", privacy_class="cloud_allowed",
                                           budget="backfill", purpose=purpose)["content"]
    rows = []
    def one(c):
        try:
            return run_case(c, ask, a.probes)
        except Exception as exc:  # noqa: BLE001 — one bad sample never stops the bench
            return {"call_id": c["call_id"], "tool": c["tool"], "error": str(exc)[:300]}
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, pts))
    tally = {"A_full": {}, "B_reduced": {}}
    for r in rows:
        for arm in tally:
            for lab in r.get(arm) or []:
                tally[arm][lab] = tally[arm].get(lab, 0) + 1
    ok = [r for r in rows if "error" not in r]
    res = {"cases_ok": len(ok), "errors": len(rows) - len(ok), "labels": tally,
           "chars_full": sum(r["full_chars"] for r in ok), "chars_reduced": sum(r["reduced_chars"] for r in ok),
           "by_tool": {}}
    for r in ok:
        t = res["by_tool"].setdefault(r["tool"], {"cases": 0, "B_wrong": 0, "B_recover": 0})
        t["cases"] += 1
        t["B_wrong"] += (r.get("B_reduced") or []).count("wrong")
        t["B_recover"] += (r.get("B_reduced") or []).count("recover")
    print(json.dumps({"estimate": est, "result": res}, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps({"estimate": est, "result": res, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
