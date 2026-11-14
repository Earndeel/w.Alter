#!/usr/bin/env python3
"""Cleanup phase 2: proof, event by event, that the observability events copied into `core.events` (`tool.called`,
`skill.used`) have an exact equivalent in `walter_logs`, one proof per (source, event type).

    obs_dedup_proof.py [--out report.json]       (same as `walter-memory observability proof --out …`)

Read-only (one READ ONLY REPEATABLE READ snapshot); prints counts only, never content. The proof itself lives in
walter_memory/observability.py since 2026-11-09, so that the retirement (`walter-memory observability retire`)
re-runs exactly this classification inside the transaction that deletes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from walter_memory import observability  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = json.dumps(observability.proof(), ensure_ascii=False, indent=1, default=str)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
