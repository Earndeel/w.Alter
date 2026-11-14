"""Agentset rerankers and embeddings leaderboards (RAG retrieval ELO, latency, price)."""
from __future__ import annotations

import html
import re
from datetime import datetime

from walter_router.research.web import _json_array, fetch_text, now, rsc_text

# Agentset RAG leaderboards: pairwise ELO judged on retrieval tasks, average latency, nDCG@10, price per 1M tokens.
AGENTSET_URLS = {"rerank": "https://agentset.ai/rerankers", "embeddings": "https://agentset.ai/embeddings"}


def agentset_board(page: str) -> dict:
    """Leaderboard entries embedded in an Agentset page (rank, name, ELO score, provider, licence, avgLatencyMs,
    avgNdcg10, costPer1MTokens[, dimensions]), its 'Last updated' date and the detail-page slug of each name."""
    text = rsc_text(page) or html.unescape(page)
    m = re.search(r'"entries":\[', text)
    if not m:
        raise ValueError("agentset: no entries in page")
    updated = re.search(r'Last updated: ","([^"]+)"', text)
    slugs = dict(re.findall(r'"name":"([^"]+)","url":"https://agentset\.ai/(?:rerankers|embeddings)/([^"]+)"', text))
    return {"entries": _json_array(text, m.end() - 1), "updated": updated and updated.group(1), "slugs": slugs}


def source_agentset() -> tuple[dict, datetime, str]:
    boards, errors = {}, {}
    for key, url in AGENTSET_URLS.items():
        try:
            board = agentset_board(fetch_text(url))
            if len(board["entries"]) < 5:
                raise ValueError(f"only {len(board['entries'])} entries")
            boards[key] = {"url": url, **board}
        except Exception as exc:  # noqa: BLE001 — one missing board leaves the other usable
            errors[key] = f"{type(exc).__name__}: {exc}"[:200]
    if not boards:
        raise ValueError(f"agentset: no board parsed: {errors}")
    return {"boards": boards, "errors": errors}, now(), "https://agentset.ai/leaderboard"
