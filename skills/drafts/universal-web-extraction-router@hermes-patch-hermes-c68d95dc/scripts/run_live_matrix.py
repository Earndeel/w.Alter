from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from panel_server import SCENARIOS, spec_for
from universal_extractor import UniversalExtractor
from universal_router import CamoufoxMaxClient, UniversalRouter
from webtop_client import WebtopCdpClient

OUT = Path("/tmp/universal-live-matrix-report.json")
TARGET_TIMEOUT_S = 120

# Public, unauthenticated pages chosen to exercise different data shapes.
# A failed target remains evidence: it tells us which fallback/adapter is missing.
TARGETS = [
    {
        "id": "flight-search",
        "url": "https://www.trip.com/flights/showfarefirst?dcity=gva&acity=bkk&ddate=2026-09-25&rdate=2026-09-28&triptype=ow&class=y&lowpricesource=searchform&quantity=1&searchboxarg=t&nonstoponly=off&sort=price&locale=en_xx&curr=EUR",
    },
    {
        "id": "hotel-availability",
        "url": "https://www.trip.com/hotels/list?city=359&searchWord=Bangkok",
    },
    {
        "id": "product-monitor",
        "url": "https://www.ikea.com/fr/fr/search/?q=lampe",
    },
    {
        "id": "social-monitoring",
        "url": "https://mastodon.social/api/v1/timelines/tag/travel?limit=20",
    },
    {
        "id": "article-discovery",
        "url": "https://hn.algolia.com/?query=travel",
    },
    {
        "id": "lead-directory",
        "url": "https://nominatim.openstreetmap.org/search?format=jsonv2&q=hotel%20Bangkok&limit=10",
    },
]


async def main() -> None:
    extractor = UniversalExtractor(
        concurrency=2,
        timeout_ms=90_000,
        candidate_wait_ms=20_000,
        return_wait_ms=400,
        persistent_sessions=True,
        session_max_pages=2,
    )
    router = UniversalRouter(
        scrapling_extractor=extractor,
        camoufox_client=CamoufoxMaxClient(),
        webtop_client=WebtopCdpClient(),
    )
    started = time.perf_counter()
    try:
        semaphore = asyncio.Semaphore(2)

        async def run_target(target: dict[str, str]) -> dict[str, object]:
            async with semaphore:
                try:
                    routed = await asyncio.wait_for(
                        router.extract_one(
                            target["url"],
                            spec_for(SCENARIOS[target["id"]]),
                            mode="auto",
                        ),
                        timeout=TARGET_TIMEOUT_S,
                    )
                    summary = routed.summary()
                    best = summary.get("best_candidate") or {}
                    return {
                        "profile": target["id"],
                        "url": target["url"],
                        "state": "accepted" if summary["valid_candidate_count"] else "rejected_or_blocked",
                        "error": summary["error"],
                        "elapsed_s": summary["elapsed_s"],
                        "valid_candidate_count": summary["valid_candidate_count"],
                        "record_count": summary["record_count"],
                        "best_path": best.get("path"),
                        "best_method": best.get("method"),
                        "best_status": best.get("status"),
                        "best_score": best.get("score"),
                        "matched_fields": best.get("matched_fields", []),
                        "records": summary["records"],
                        "json_candidates": summary["json_candidates"],
                        "route": summary["route"],
                        "attempts": summary["attempts"],
                        "escalation": summary["escalation"],
                    }
                except asyncio.TimeoutError:
                    return {
                        "profile": target["id"],
                        "url": target["url"],
                        "state": "timeout",
                        "error": f"TimeoutError: target exceeded {TARGET_TIMEOUT_S}s",
                        "elapsed_s": TARGET_TIMEOUT_S,
                        "valid_candidate_count": 0,
                        "record_count": 0,
                        "best_path": None,
                        "best_method": None,
                        "best_status": None,
                        "best_score": None,
                        "matched_fields": [],
                        "records": [],
                        "json_candidates": [],
                        "route": "unknown",
                        "attempts": [],
                        "escalation": {"recommended_backend": "webtop-cdp", "reason": "target timeout"},
                    }

        rows = await asyncio.gather(*(run_target(target) for target in TARGETS))
    finally:
        await router.close()

    report = {
        "engine": "universal-extraction-router",
        "mode": "auto-router-live-network",
        "wall_elapsed_s": round(time.perf_counter() - started, 2),
        "concurrency": extractor.concurrency,
        "target_timeout_s": TARGET_TIMEOUT_S,
        "route": {
            "primary": "scrapling",
            "fallback": "camoufox-max",
            "fallback_2": "webtop-cdp-dom-or-json",
            "escalation": "brave-mac-cdp",
        },
        "targets": rows,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "wall_elapsed_s": report["wall_elapsed_s"],
                "accepted": sum(row["state"] == "accepted" for row in rows),
                "rejected_or_blocked": sum(row["state"] != "accepted" for row in rows),
                "targets": [
                    {
                        "profile": row["profile"],
                        "state": row["state"],
                        "records": row["record_count"],
                        "path": row["best_path"],
                        "error": row["error"],
                    }
                    for row in rows
                ],
                "report": str(OUT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
