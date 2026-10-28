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
    sb = sub.add_parser("sandbox", help="run an approved source copy in a disposable container without network access")
    sb.add_argument("action", choices=["run", "probe"]); sb.add_argument("--src")
    sb.add_argument("--image", default=None); sb.add_argument("--timeout", type=int, default=600)
    argv = list(sys.argv[1:] if argv is None else argv)
    tail = argv[argv.index("--") + 1:] if "--" in argv else []     # the sandboxed command, verbatim
    argv = argv[:argv.index("--")] if "--" in argv else argv
    a = p.parse_args(argv)
    a.command = tail
    if a.cmd == "sandbox":
        from . import sandbox
        if a.action == "probe":
            out = sandbox.probe()
        else:
            from datetime import datetime, timezone
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out = sandbox.run(a.src, a.command, image=a.image or sandbox.DEFAULT_IMAGE, timeout=a.timeout,
                              out_dir=core.instance_root() / "state" / "lab" / "sandbox" / stamp)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0 if out.get("ok", out.get("rc") == 0) else 1
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
