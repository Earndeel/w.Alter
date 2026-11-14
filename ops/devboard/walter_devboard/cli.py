"""walter-devboard — the development board (README.md)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="walter-devboard", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply the schema migrations")
    sub.add_parser("sync-docs", help="read documents and decisions (no model)")
    a = ap.parse_args(argv)
    from . import config, db
    if a.cmd == "migrate":
        out = {"applied": db.migrate()}
    elif a.cmd == "sync-docs":
        from . import docs
        cfg = config.load()
        with db.connection() as c:
            out = docs.sync(c, cfg)
    print(json.dumps(out, ensure_ascii=False, default=str, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
