"""walter-router-guardian check | run [--no-agent] [--no-tests] [--no-notify] [--dry-run] | status"""
from __future__ import annotations

import argparse
import json
import sys

from walter_router.guardian import checks, run
from walter_router.store import db


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-router-guardian")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="what is wrong now (no action, no model)")
    c.add_argument("--no-tests", action="store_true")
    r = sub.add_parser("run", help="one pass: detect, follow incidents, repair, notify")
    r.add_argument("--no-agent", action="store_true", help="deterministic actions only (probe, re-read)")
    r.add_argument("--no-tests", action="store_true")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--dry-run", action="store_true", help="prepare the repair workspace, run no agent, send nothing")
    sub.add_parser("status", help="open incidents and those closed in the last 7 days")
    args = p.parse_args(argv)
    if args.cmd == "check":
        with db.connect() as conn:
            out = checks.detect(conn, with_tests=not args.no_tests)
    elif args.cmd == "run":
        out = run.run(agent=not args.no_agent, tests=not args.no_tests, send=not args.no_notify, dry_run=args.dry_run)
    else:
        out = run.status()
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
