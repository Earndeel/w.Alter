"""walter-context CLI: recover (journal), bench (replay), explain (one session's projection)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["bench"], ["quality"]):
        sys.path.insert(0, __file__.rsplit("/walter_context/", 1)[0])
        if argv[0] == "bench":
            from bench.replay import main as run
        else:
            from bench.quality import main as run
        return run(argv[1:])
    ap = argparse.ArgumentParser(prog="walter-context")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recover", help="original of a compacted tool output")
    r.add_argument("ref")
    r.add_argument("--offset", type=int, default=0)
    r.add_argument("--max-privacy", default="cloud_allowed", choices=["cloud_allowed", "redacted_cloud", "local_only"])
    r.add_argument("--own", help="caller's session prefix: its own outputs are returned as first seen")
    sub.add_parser("bench", help="replay bench: tokens, cache, cost (see bench/replay.py --help)")
    sub.add_parser("quality", help="retention probes, LLM-judged; --estimate by default (see bench/quality.py)")
    a = ap.parse_args(argv)
    if a.cmd == "recover":
        from .journal import recover
        print(json.dumps(recover(a.ref, a.offset, a.max_privacy, a.own), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
