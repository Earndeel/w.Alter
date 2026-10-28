"""walter-backup — status | check | run <kind> | verify | git | checkpoint | checkpoints  (JSON on stdout)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-backup", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="conformity, backup health and restorability, separately")
    sub.add_parser("check", help="the module's watchdog: Incident v1 list (exit 0 even with incidents)")
    r = sub.add_parser("run", help="start an existing backup mechanism (systemd unit, not waited for)")
    r.add_argument("kind")
    v = sub.add_parser("verify", help="cheap proofs on the newest local copies (+ a Raw Vault sample)")
    v.add_argument("--sample", type=int, default=None)
    sub.add_parser("git", help="Git Manager inventory: every Walter repository, uncommitted work, remotes, checkpoints")
    c = sub.add_parser("checkpoint", help="protect a state before a risky change")
    c.add_argument("--level", choices=["git", "files", "db"], required=True)
    c.add_argument("--scope", default="", help="git/files: a directory; db: ignored")
    c.add_argument("--schema", action="append", default=[], help="db: schema to dump (repeatable)")
    c.add_argument("--note", default="")
    sub.add_parser("checkpoints", help="the recorded checkpoints and how to restore each (restores are never run)")
    a = p.parse_args(argv)
    if a.cmd == "status":
        out = core.status()
    elif a.cmd == "check":
        out = core.check()
    elif a.cmd == "run":
        kinds = core.config().get("kinds") or {}
        if a.kind not in kinds:
            print(json.dumps({"error": f"unknown kind; known: {sorted(kinds)}"})); return 2
        unit = kinds[a.kind]["unit"]
        rc = subprocess.run(["systemctl", "start", "--no-block", f"{unit}.service"]).returncode
        out = {"started": unit, "ok": rc == 0, "follow": f"journalctl -u {unit}.service -f"}
    elif a.cmd == "verify":
        out = core.verify(a.sample)
    elif a.cmd == "git":
        out = core.git_inventory()
    elif a.cmd == "checkpoint":
        try:
            out = core.checkpoint(a.level, a.scope, schemas=a.schema, note=a.note)
        except (ValueError, RuntimeError) as exc:
            print(json.dumps({"error": str(exc)})); return 1
    else:
        out = core.checkpoints()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
