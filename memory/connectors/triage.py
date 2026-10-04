#!/usr/bin/env python3
"""Triage runner (V3): decide what to do with every new incoming event (see walter_memory/triage.py).
Usage: triage.py [--limit N] [--dry]     (--dry: decide and print, write nothing)"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import ingestion, triage  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    ingestion.register_connector(triage.CONNECTOR, "beeper", "pull",
                                 "Triage of new incoming events (Beeper, Gmail, Calendar) by Clef + Monsieur rules",
                                 timedelta(minutes=15))
    try:
        out = triage.run(a.limit, a.dry)
        if not a.dry:
            ingestion.mark_success(triage.CONNECTOR)
        print(json.dumps(out, default=str))
    except Exception as e:
        if not a.dry:
            ingestion.record_failure(triage.CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
