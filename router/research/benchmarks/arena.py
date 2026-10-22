"""Arena.ai (LMArena) boards, read from the pages' embedded data."""
from __future__ import annotations

import html
import re
import time
from datetime import datetime

from walter_router.research.web import _json_array, fetch_text, now

ARENA_URL = "https://arena.ai/leaderboard/"


# Arena.ai page -> board key stored in models.benchmarks.task (benchmark = 'arena')
ARENA_BOARDS = {"text": "text", "text/french": "text_french", "text/coding": "text_coding",
                "text/creative-writing": "text_creative", "code/webdev": "webdev",
                "code/image-to-webdev": "image_to_webdev", "vision": "vision", "document": "document",
                "search": "search", "agent": "agent", "text-to-image": "text_to_image",
                "image/image-edit/single-image": "image_edit",   # moved there on 2026-10-10 (was image-edit)
                "text-to-video": "text_to_video", "image-to-video": "image_to_video", "video-edit": "video_edit"}


def arena_board(page: str) -> dict | None:
    """Leaderboard rows embedded in an Arena.ai page (Next.js flight data): pairwise boards carry 'entries'
    (Elo rating + CI + votes), the agent board carries 'snapshot.rows' (average task score + CI)."""
    text = html.unescape(page).replace('\\"', '"').replace("\\\\", "\\")
    m = re.search(r'"id":"(leaderboard-sets/[^"]+)","entries":\[', text)
    if m:
        return {"leaderboard_id": m.group(1), "kind": "elo", "rows": _json_array(text, m.end() - 1)}
    i = text.find('"snapshot":{"lastUpdated"')
    if i >= 0:
        j = text.index('"rows":[', i) + len('"rows":')
        updated = re.search(r'"lastUpdated":"([^"]+)"', text[i:i + 80])
        return {"leaderboard_id": "agent", "kind": "agent", "updated": updated and updated.group(1),
                "rows": _json_array(text, j)}
    return None


def source_arena(parts: set[str] | None = None) -> tuple[dict, datetime, str]:
    """Every board, or only `parts` (board keys, for a research category run; merged later into the last snapshot)."""
    wanted = {p: k for p, k in ARENA_BOARDS.items() if not parts or k in parts}
    boards, errors = {}, {}
    for attempt in range(2):   # a board missing on the first pass is retried once (2026-10-21: creative writing
        for path, key in wanted.items():   # came back empty once, then fine a few minutes later)
            if key in boards:
                continue
            try:
                board = arena_board(fetch_text(ARENA_URL + path))
                if board and board["rows"]:
                    boards[key] = {"path": path, **board}
                    errors.pop(key, None)
                else:
                    errors[key] = "no leaderboard rows in page"
            except Exception as exc:  # noqa: BLE001 — one missing board leaves the others usable
                errors[key] = f"{type(exc).__name__}: {exc}"[:200]
            time.sleep(0.5)
        if not errors:
            break
        time.sleep(5)
    if len(boards) < max(1, len(wanted) // 2):
        raise ValueError(f"arena: only {len(boards)} boards parsed: {errors}")
    return {"boards": boards, "errors": errors}, now(), ARENA_URL
