from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from pathlib import Path

from universal_extractor import UniversalExtractor, trip_spec

OUT = Path("/tmp/universal-trip-extraction-report.json")
QUERIES = [
    ("GVA", date(2026, 9, 25)),
    ("GVA", date(2026, 9, 26)),
    ("PAR", date(2026, 9, 25)),
]


def make_url(origin: str, departure: date) -> str:
    return (
        "https://www.trip.com/flights/showfarefirst?"
        f"dcity={origin.lower()}&acity=bkk&ddate={departure.isoformat()}"
        "&rdate=2026-09-28&triptype=ow&class=y&lowpricesource=searchform"
        "&quantity=1&searchboxarg=t&nonstoponly=off&sort=price"
        "&locale=en_xx&curr=EUR"
    )


async def main() -> None:
    requests = [(make_url(origin, departure), trip_spec()) for origin, departure in QUERIES]
    extractor = UniversalExtractor(
        concurrency=3,
        candidate_wait_ms=45_000,
        return_wait_ms=250,
        persistent_sessions=True,
        session_max_pages=3,
    )
    started = time.perf_counter()
    try:
        results = await extractor.extract_many(requests)
    finally:
        await extractor.close()
    report = {
        "engine": "universal-json-first-extractor",
        "wall_elapsed_s": round(time.perf_counter() - started, 2),
        "concurrency": extractor.concurrency,
        "results": [result.summary() for result in results],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "wall_elapsed_s": report["wall_elapsed_s"],
        "success_count": sum(result.best_candidate is not None for result in results),
        "endpoints": [
            result.best_candidate.summary()["path"] if result.best_candidate else None
            for result in results
        ],
        "record_counts": [len(result.records) for result in results],
        "best_scores": [round(result.best_candidate.score, 2) if result.best_candidate else None for result in results],
        "report": str(OUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
