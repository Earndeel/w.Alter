"""walter-lab — run | history | list   (measured experiments on Walter; proposals only, never applied)."""
from __future__ import annotations

import argparse
import json
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-lab", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("experiment"); r.add_argument("--repeats", type=int)
    h = sub.add_parser("history"); h.add_argument("experiment")
    sub.add_parser("list")
    a = p.parse_args(argv)
    if a.cmd == "list":
        out = [{"name": e.stem, "hypothesis": core.load(e.stem)["hypothesis"]}
               for e in sorted((core.MODULE / "experiments").glob("*.yaml"))]
    elif a.cmd == "history":
        out = core.history(a.experiment)
    else:
        rep = core.run(a.experiment, a.repeats)
        out = {k: rep[k] for k in ("experiment", "hypothesis", "at", "repeats", "summary", "decision", "file")}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
