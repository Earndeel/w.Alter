"""walter-ops — backup | git | check | status | recovery | deploy | install | onboard   (JSON on stdout).

  walter-ops backup <status|check|run|verify|git|checkpoint|checkpoints> ...   = walter-backup ... (same outputs)
  walter-ops git                     repositories, uncommitted work, remotes, checkpoints
  walter-ops check                   the module's guardian watchdog (Incident v1)
  walter-ops status                  backup status + where each Ops sub-component stands
  walter-ops recovery drill|test     start the isolated restore drill / the offsite restore test (systemd, not waited)
  walter-ops deploy <inspect|environments|rollback|export|install> ...   the core platform's release mechanism
  walter-ops install migrations-check [--keep-dumps DIR]   replay every module's migrations on a disposable database
                                     and compare its structure with the live one (Walter Clean, PostgreSQL part)
  walter-ops install data-check      every table classified (contracts/data-classes.json); reference rows a clean
                                     install would carry, searched for the instance's private markers (counts only)
  walter-ops install seed-export DIR  reference rows of every declared table (CSV.zst + manifest; a release artifact)
  walter-ops install clean-db-check [--seeds DIR | --keep-seeds DIR]   build the Walter Clean database (migrations +
                                     reference rows) on a disposable PostgreSQL and prove it: counts, and no private
                                     marker in any row of any table (counts only)
  walter-ops install clean|personal, walter-ops onboard ...            designed, not built yet: answer "planned"
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from walter_backup import cli as backup_cli
from walter_backup import core as backup

PLAN = "addendum architectural du 2026-10-29 (Ops, Walter Clean, Walter Personal), rapport de l'instance"
COMPONENTS = {"backup": "built (walter_backup)", "git": "built (walter_backup.git_inventory, checkpoints)",
              "recovery": "built: restore drill + monthly offsite restore test (implementations in walter-memory "
                          "and host units, started by Ops)",
              "deploy": "wraps `walter release|install|export` (core platform)",
              "installer": "planned: clean-install, onboarding, personal-restore", "guardian": "built (walter-ops check)"}
RECOVERY = {"drill": "restore_drill", "test": "restore_test"}
DEPLOY = {"inspect": ["release", "inspect"], "environments": ["release", "environments"],
          "rollback": ["release", "rollback"], "export": ["export"], "install": ["install"]}


def _print(out) -> None:
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "backup":
        return backup_cli.main(rest)
    if cmd in ("git", "check"):
        return backup_cli.main([cmd, *rest])
    if cmd == "status":
        _print({"backup": backup.status(), "components": COMPONENTS})
        return 0
    if cmd == "recovery":
        if not rest or rest[0] not in RECOVERY:
            _print({"error": f"usage: walter-ops recovery {'|'.join(RECOVERY)}"}); return 2
        return backup_cli.main(["run", RECOVERY[rest[0]]])
    if cmd == "deploy":
        if not rest or rest[0] not in DEPLOY:
            _print({"error": f"usage: walter-ops deploy {'|'.join(DEPLOY)} ..."}); return 2
        if not shutil.which("walter"):
            _print({"error": "dependency_unavailable", "detail": "the core platform command `walter` is not on PATH"})
            return 1
        return subprocess.run(["walter", *DEPLOY[rest[0]], *rest[1:]]).returncode
    if cmd == "install" and rest[:1] == ["migrations-check"]:
        from pathlib import Path
        from . import clean
        keep = Path(rest[rest.index("--keep-dumps") + 1]) if "--keep-dumps" in rest else None
        out = clean.migrations_check(keep_dumps=keep)
        _print(out)
        return 0 if out.get("ok") else 1
    if cmd == "install" and rest[:1] == ["data-check"]:
        from . import data
        out = data.check()
        _print(out)
        return 0 if out.get("ok") else 1
    if cmd == "install" and rest[:1] in (["seed-export"], ["clean-db-check"]):
        from pathlib import Path
        from . import seeds
        if rest[0] == "seed-export":
            if len(rest) < 2:
                _print({"error": "usage: walter-ops install seed-export <new directory>"}); return 2
            m = seeds.export(Path(rest[1]))
            _print({"tables": {t: v["rows"] for t, v in m["tables"].items()}, "dir": rest[1]}); return 0
        opt = lambda flag: Path(rest[rest.index(flag) + 1]) if flag in rest else None     # noqa: E731
        out = seeds.clean_db_check(seeds=opt("--seeds"), keep_seeds=opt("--keep-seeds"))
        _print(out)
        return 0 if out.get("ok") else 1
    if cmd in ("install", "onboard"):
        _print({"status": "planned", "component": "installer", "detail": f"walter-ops {cmd} is designed, not built",
                "design": PLAN})
        return 2
    _print({"error": f"unknown command {cmd!r}; see walter-ops --help"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
