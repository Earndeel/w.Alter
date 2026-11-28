#!/usr/bin/env python3
"""Verify that Scena's three canonical D1 schemas bootstrap cleanly.

This is intentionally local and read-only: each schema is applied to a fresh
in-memory SQLite database. It does not inspect or modify production D1.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

SCHEMAS = (
    "d1/schema.sql",
    "d1/scena-saas-db.sql",
    "d1/scena-ops-db.sql",
)


def verify(repo: Path, relative_path: str) -> dict[str, object]:
    path = repo / relative_path
    result: dict[str, object] = {"schema": relative_path, "ok": False}
    if not path.is_file():
        result["error"] = "file not found"
        return result

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(path.read_text(encoding="utf-8"))
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        result.update(ok=True, tables=[row[0] for row in tables])
    except sqlite3.Error as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        connection.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".", help="Scena repository root")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    results = [verify(repo, schema) for schema in SCHEMAS]
    print(json.dumps({"repo": str(repo), "results": results}, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
