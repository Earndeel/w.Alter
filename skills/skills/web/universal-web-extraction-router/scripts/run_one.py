from __future__ import annotations

import asyncio
import json
import time

from universal_extractor import UniversalExtractor, trip_spec

URL = (
    "https://www.trip.com/flights/showfarefirst?"
    "dcity=gva&acity=bkk&ddate=2026-09-25"
    "&rdate=2026-09-28&triptype=ow&class=y&lowpricesource=searchform"
    "&quantity=1&searchboxarg=t&nonstoponly=off&sort=price&locale=en_xx&curr=EUR"
)


async def main() -> None:
    extractor = UniversalExtractor(concurrency=1, candidate_wait_ms=20_000, return_wait_ms=100)
    started = time.perf_counter()
    try:
        result = await extractor.extract_one(URL, trip_spec())
    finally:
        await extractor.close()
    print(json.dumps({
        "wall_elapsed_s": round(time.perf_counter() - started, 2),
        "summary": result.summary(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
