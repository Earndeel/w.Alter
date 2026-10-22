"""Video understanding: models that watch a video and answer about it (not video generation).

No arena measures it (Artificial Analysis and Arena only rank video generation; Arena's vision board is images).
Two readers, checked 2026-10-22:

- Video-MME-v2 (April 2026, the successor of the saturated Video-MME): measured by its authors, grouped
  "non-linear" score that only credits consistent answers, with and without subtitles. Independent but updated
  rarely (newest rows: Gemini 3, Qwen 3.6). Rows come from the `leaderboardDataRaw` array of its page.
- LLM Stats benchmark pages (LVBench, VideoMMMU, Video-MME, MLVU, LongVideoBench, MVBench): current, but every
  score there is self-reported by the model's vendor (`self_reported`); the analysis weighs them half.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from walter_router.research.web import _json_object, fetch_text, now, rsc_text

VIDEO_MME_V2_URL = "https://video-mme-v2.netlify.app/"
LLM_STATS_URL = "https://llm-stats.com/benchmarks/{board}"
LLM_STATS_BOARDS = ("lvbench", "videommmu", "video-mme", "mlvu", "longvideobench", "mvbench")

_ITEM = re.compile(r"\{\s*name:\s*\"(?P<name>[^\"]+)\"(?P<body>.*?)\}\s*,?\s*(?=\{\s*name:|\])", re.S)


def _pair(body: str, key: str) -> list[float | None] | None:
    m = re.search(rf"\b{key}:\s*\[\s*([0-9.]+|null)\s*,\s*([0-9.]+|null)\s*\]", body)
    return [None if v == "null" else float(v) for v in m.groups()] if m else None


def video_mme_v2_rows(page: str) -> list[dict]:
    """One row per leaderboard entry: name, type, frames, overall [with subtitles, without], avg_acc, stale."""
    start = page.find("leaderboardDataRaw")
    if start < 0:
        raise ValueError("video-mme-v2: no leaderboardDataRaw in page")
    end = page.find("];", start)
    rows = []
    for m in _ITEM.finditer(page[start:end + 1]):
        body = m.group("body")
        kind = re.search(r'\btype:\s*"([^"]+)"', body)
        if kind and kind.group(1) == "human":
            continue
        frames = re.search(r'\bframes:\s*"([^"]*)"', body)
        overall = _pair(body, "overall")
        if not overall or overall[0] is None and overall[1] is None:
            continue
        rows.append({"name": m.group("name"), "type": kind and kind.group(1), "frames": frames and frames.group(1),
                     "overall": overall, "avg_acc": _pair(body, "avg_acc"), "stale": "stale: true" in body})
    return rows


def llm_stats_board(page: str) -> dict:
    """The `initialBenchmarkData` object of an LLM Stats benchmark page (statistics + models with their scores)."""
    text = rsc_text(page) or page
    i = text.find('"initialBenchmarkData":')
    if i < 0:
        raise ValueError("llm-stats: no initialBenchmarkData in page")
    data = json.loads(_json_object(text, text.index("{", i)))
    return {"name": data.get("name"), "updated_at": data.get("updated_at"), "statistics": data.get("statistics"),
            "models": [{k: m.get(k) for k in ("model_id", "model_name", "organization_name", "score", "self_reported",
                                              "verified", "analysis_method", "self_reported_source", "announcement_date")}
                       for m in data.get("models") or []]}


def source_video_evals() -> tuple[dict, datetime, str]:
    doc: dict = {"video_mme_v2": None, "llm_stats": {}, "errors": {}}
    try:
        rows = video_mme_v2_rows(fetch_text(VIDEO_MME_V2_URL))
        if len(rows) < 10:
            raise ValueError(f"only {len(rows)} rows")
        doc["video_mme_v2"] = {"url": VIDEO_MME_V2_URL, "rows": rows}
    except Exception as exc:  # noqa: BLE001 — one missing board leaves the others usable
        doc["errors"]["video_mme_v2"] = f"{type(exc).__name__}: {exc}"[:200]
    for board in LLM_STATS_BOARDS:
        url = LLM_STATS_URL.format(board=board)
        try:
            b = llm_stats_board(fetch_text(url))
            if len(b["models"]) < 3:
                raise ValueError(f"only {len(b['models'])} models")
            doc["llm_stats"][board] = {"url": url, **b}
        except Exception as exc:  # noqa: BLE001
            doc["errors"][f"llm_stats/{board}"] = f"{type(exc).__name__}: {exc}"[:200]
    if not doc["video_mme_v2"] and not doc["llm_stats"]:
        raise ValueError(f"video evals: nothing parsed: {doc['errors']}")
    return doc, now(), VIDEO_MME_V2_URL
