"""walter-context CLI: recover (originals from walter_logs) and the benches (replay, quality, acceptance, threads)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["bench"], ["quality"], ["acceptance"], ["threads"]):
        sys.path.insert(0, __file__.rsplit("/walter_context/", 1)[0])
        if argv[0] == "bench":
            from bench.replay import main as run
        elif argv[0] == "threads":
            from bench.threads import main as run
        elif argv[0] == "quality":
            from bench.quality import main as run
        else:
            from bench.acceptance import main as run
        return run(argv[1:])
    ap = argparse.ArgumentParser(prog="walter-context")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recover", help="original of a compacted tool output")
    r.add_argument("ref")
    r.add_argument("--offset", type=int, default=0)
    r.add_argument("--max-privacy", default="cloud_allowed", choices=["cloud_allowed", "redacted_cloud", "local_only"])
    r.add_argument("--own", help="exact caller session id: its own outputs are returned as first seen")
    capability = sub.add_parser("capability", help="prepare a trusted module note for the stable context layer")
    capability.add_argument("module", choices=["router", "all"])
    capability.add_argument("--tool", action="append", dest="tools", help="actual tool name available in this harness (repeat)")
    capability.add_argument("--form", choices=["full", "m0"], default="full",
                            help="all: full = every module's M1 (default); m0 = one line per module + M1 of --m1")
    capability.add_argument("--m1", action="append", default=[], help="all, form m0: module to show in M1 (repeat)")
    capability.add_argument("--write", action="store_true",
                            help="all: publish @instance/state/context/modules.md for file profiles (Codex, DSH)")
    sub.add_parser("bench", help="replay bench: tokens, cache, cost (see bench/replay.py --help)")
    sub.add_parser("quality", help="retention probes, LLM-judged; --estimate by default (see bench/quality.py)")
    sub.add_parser("threads", help="thread (fil) attachment bench on the real stream; offline, read-only")
    sub.add_parser("acceptance", help="synthetic exact-retention corpus; no private data or external model calls")
    sub.add_parser("preflight-questions",
                   help="the exact decision payload the preflight would send for one case (JSON on stdin: message, "
                        "previous {message, answer, age_s, thread_id}, candidates); no model call, nothing recorded")
    a = ap.parse_args(argv)
    if a.cmd == "preflight-questions":
        print(json.dumps(preflight_questions(json.load(sys.stdin)), ensure_ascii=False))
        return 0
    if a.cmd == "capability":
        from .capabilities import compose, router_note, write_layer
        if a.write:
            if a.module != "all":
                raise SystemExit("--write applies to the module layer (all)")
            print(json.dumps(write_layer(), ensure_ascii=False))
            return 0
        result = compose(a.tools, a.form, a.m1) if a.module == "all" else router_note(a.tools)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["injection_allowed"] else 1
    if a.cmd == "recover":
        from .recover import recover
        print(json.dumps(recover(a.ref, a.offset, a.max_privacy, a.own), ensure_ascii=False))
    return 0


def preflight_questions(case: dict) -> dict:
    """The decision payload of one owner message, built by the preflight's own code (decision bench of Walter Router,
    2026-11-13: the bench asks the models exactly what production asks). `fast_path` = rules settle it without a
    model call in production (the bench then leaves the case out)."""
    from .preflight import Exchange, Request, fast_path, questions
    prev = case.get("previous") or None
    req = Request(turn_id="bench", message=str(case.get("message") or ""),
                  previous=Exchange(message=str(prev.get("message") or ""), answer=str(prev.get("answer") or ""),
                                    age_s=prev.get("age_s"), thread_id=prev.get("thread_id")) if prev else None,
                  candidates=[c for c in case.get("candidates") or [] if isinstance(c, dict)])
    state, q = questions(req)
    fast = fast_path(req)
    return {"state": state, "questions": q, "fast_path": fast.fast_path if fast else None}


if __name__ == "__main__":
    raise SystemExit(main())
