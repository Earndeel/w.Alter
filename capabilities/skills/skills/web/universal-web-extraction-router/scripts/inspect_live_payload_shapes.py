from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from panel_server import SCENARIOS, spec_for
from universal_extractor import UniversalExtractor

TARGETS = {
    "hotel-availability": "https://www.trip.com/hotels/list?city=359&searchWord=Bangkok",
    "product-monitor": "https://www.ikea.com/fr/fr/search/?q=lampe",
    "social-monitoring": "https://www.reddit.com/search/?q=travel&sort=new",
    "article-discovery": "https://hn.algolia.com/?query=travel",
}
OUT = Path("/tmp/universal-live-payload-shapes.json")


def shape(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {"type": "object", "keys": list(value)[:100]}
        children = {}
        for key, child in list(value.items())[:30]:
            if isinstance(child, (dict, list)):
                children[str(key)] = shape(child, f"{path}.{key}".strip("."))
        if children:
            result["children"] = children
        return result
    if isinstance(value, list):
        result = {"type": "array", "length": len(value)}
        samples = [item for item in value[:3] if isinstance(item, (dict, list))]
        if samples:
            result["sample_shapes"] = [shape(item, path) for item in samples]
        return result
    return {"type": type(value).__name__}


async def main() -> None:
    extractor = UniversalExtractor(
        concurrency=2,
        timeout_ms=90_000,
        candidate_wait_ms=20_000,
        return_wait_ms=400,
        persistent_sessions=True,
        session_max_pages=2,
    )
    try:
        results = await extractor.extract_many(
            [(url, spec_for(SCENARIOS[scenario_id])) for scenario_id, url in TARGETS.items()]
        )
    finally:
        await extractor.close()

    output = {}
    for (scenario_id, url), result in zip(TARGETS.items(), results, strict=True):
        candidate = result.best_candidate
        output[scenario_id] = {
            "url": url,
            "summary": result.summary(),
            "best_payload_shape": shape(candidate.payload) if candidate else None,
        }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value["best_payload_shape"] for key, value in output.items()}, ensure_ascii=False))
    print(f"report={OUT}")


if __name__ == "__main__":
    asyncio.run(main())
