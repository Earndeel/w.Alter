"""Arena.ai (LMArena) boards, read from the pages' embedded data."""
from __future__ import annotations

import html
import base64
import json
import subprocess
import uuid
import zlib
import re
import time
from datetime import datetime
from urllib.parse import urlsplit

from walter_router.research.web import MAX_BYTES, _json_array, fetch_text, now

ARENA_URL = "https://arena.ai/leaderboard/"


# Arena.ai page -> board key stored in models.benchmarks.task (benchmark = 'arena')
ARENA_BOARDS = {"chat/text": "text", "text/french": "text_french", "text/coding": "text_coding",
                "text/creative-writing": "text_creative", "code/webdev": "webdev",
                "code/image-to-webdev": "image_to_webdev", "chat/vision": "vision", "chat/document": "document",
                "chat/search": "search", "agent": "agent", "image/text-to-image": "text_to_image",
                "image/image-edit/single-image": "image_edit",   # moved there on 2026-10-10 (was image-edit)
                "video/text-to-video": "text_to_video", "video/image-to-video": "image_to_video", "video/video-edit": "video_edit"}


# Public leaderboard identities observed in the latest complete snapshot and the live canonical pages.
# A site redirect to generic text must never be recorded as French/coding/creative or another modality.
BOARD_NAMES = {'text': 'text-overall-style_control', 'search': 'search-overall-raw', 'vision': 'vision-overall-style_control', 'webdev': 'webdev-overall-raw', 'document': 'document-overall-raw', 'image_edit': 'image_edit-overall-raw', 'video_edit': 'video_to_video-overall-raw', 'text_coding': 'text-coding-style_control', 'text_french': 'text-french-style_control', 'text_creative': 'text-creative_writing-style_control', 'text_to_image': 'text_to_image-overall-raw', 'text_to_video': 'text_to_video-overall-raw', 'image_to_video': 'image_to_video-overall-raw', 'image_to_webdev': 'image_to_webdev-overall-raw'}


def _board_matches(key: str, board: dict | None) -> bool:
    """Keep each result attached to the declared public leaderboard identity."""
    if not board or not board.get("rows"):
        return False
    if key == "agent":
        return board.get("kind") == "agent" and board.get("leaderboard_id") == "agent"
    name = BOARD_NAMES.get(key)
    return bool(name and board.get("kind") == "elo" and str(board.get("leaderboard_id", "")).startswith(
        "leaderboard-sets/public/leaderboards/" + name + "/leaderboard-snapshots/"))


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


BROWSER_TIMEOUT = 90  # one public page, including navigation and bounded CLI reads
BROWSER_BUDGET = 600  # shared across the collection; no per-board timeout multiplication without a ceiling


class ArenaBrowserError(RuntimeError):
    """Public browser transport unavailable; no raw CLI diagnostics or page content is exposed."""


def _close_browser(session: str, *, timeout: float = 5) -> None:
    """Close only the dedicated public collection session, with a bounded wait."""
    try:
        result = subprocess.run(["walter-browser", "-s", session, "close"], capture_output=True,
                                text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise ArenaBrowserError("public browser cleanup unavailable or timed out") from None
    if result.returncode:
        raise ArenaBrowserError("public browser cleanup failed")


def _browser_text(url: str, *, timeout: float = BROWSER_TIMEOUT, session: dict | None = None) -> str:
    """Read a public Arena page via the supported CLI, isolated session, no login or cookie export.

    The CLI caps eval output at 20k characters. Gzip/base64 chunks stay below that bound; decompression and
    metadata have the same MAX_BYTES limit as HTTP. Browser/exit availability is an optional dependency.
    """
    own_session = session is None
    state = session if session is not None else {}
    state.setdefault("id", "arena-public-" + uuid.uuid4().hex)
    session_id = state["id"]
    deadline = time.monotonic() + timeout

    def command(action, *args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ArenaBrowserError("public browser deadline exceeded")
        try:
            result = subprocess.run(["walter-browser", "-s", session_id, action, *args], capture_output=True,
                                    text=True, timeout=remaining)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArenaBrowserError("public browser command unavailable or timed out") from None
        if result.returncode or len(result.stdout) > 20000:
            raise ArenaBrowserError("public browser command failed")
        if action != "eval":
            return result.stdout
        try:
            value = json.loads(result.stdout)
            if not isinstance(value, dict) or value.get("ok") is not True:
                raise ValueError()
            return value["result"]
        except (ValueError, KeyError):
            raise ArenaBrowserError("public browser returned invalid JSON") from None

    primary_error = None
    try:
        if not state.get("opened"):
            command("new", "arena-public")
            state["opened"] = True
        command("nav", url)
        meta = command("eval", '(async()=>{const h=document.documentElement.outerHTML;'
                       'const s=new Blob([h]).stream().pipeThrough(new CompressionStream("gzip"));'
                       'const a=new Uint8Array(await new Response(s).arrayBuffer());let b="";'
                       'for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));'
                       'window.__walterArenaPublic=btoa(b);return {url:location.href,'
                       'htmlBytes:new TextEncoder().encode(h).length,encodedLength:window.__walterArenaPublic.length};})()')
        if (not isinstance(meta, dict) or type(meta.get("htmlBytes")) is not int
                or not 0 < meta["htmlBytes"] <= MAX_BYTES or type(meta.get("encodedLength")) is not int
                or not 0 < meta["encodedLength"] <= MAX_BYTES * 2 or not isinstance(meta.get("url"), str)):
            raise ArenaBrowserError("public browser response exceeds limits or has invalid metadata")
        target = urlsplit(meta["url"])
        if target.scheme != "https" or target.netloc != "arena.ai" or not target.path.startswith("/leaderboard/"):
            raise ArenaBrowserError("public browser left the Arena leaderboard origin")
        chunks = []
        for offset in range(0, meta["encodedLength"], 16000):
            piece = command("eval", f"window.__walterArenaPublic.slice({offset},{offset + 16000})")
            if not isinstance(piece, str) or len(piece) != min(16000, meta["encodedLength"] - offset):
                raise ArenaBrowserError("public browser returned an incomplete page")
            chunks.append(piece)
        try:
            decoder = zlib.decompressobj(31)
            page = decoder.decompress(base64.b64decode("".join(chunks), validate=True), MAX_BYTES + 1)
            if len(page) != meta["htmlBytes"] or not decoder.eof or decoder.unused_data:
                raise ValueError()
            return page.decode("utf-8")
        except (ValueError, zlib.error, UnicodeError):
            raise ArenaBrowserError("public browser returned invalid or oversized compressed HTML") from None
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        # A close failure rejects a successful read, but must not hide the primary transport failure.
        if own_session:
            try:
                _close_browser(session_id, timeout=min(5, timeout))
            except ArenaBrowserError:
                if primary_error is None:
                    raise
                primary_error.add_note("public browser cleanup also failed; dedicated session may remain")


def source_arena(parts: set[str] | None = None) -> tuple[dict, datetime, str]:
    """Every board, or only requested keys. A challenged HTTP transport falls back for this collection only.

    One anonymous CLI session is shared by fallback reads, then closed. BROWSER_BUDGET bounds browser work,
    plus at most five seconds of cleanup; the initial existing HTTP/FlareSolverr attempt has its own timeouts.
    """
    wanted = {p: k for p, k in ARENA_BOARDS.items() if not parts or k in parts}
    boards, errors = {}, {}
    browser_used = 0.0
    browser_session = {}
    http_unavailable = False
    primary_error = None
    try:
        for attempt in range(2):
            for path, key in wanted.items():
                if key in boards:
                    continue
                try:
                    board = None
                    if not http_unavailable:
                        try:
                            board = arena_board(fetch_text(ARENA_URL + path))
                        except Exception:
                            pass
                        if not _board_matches(key, board):
                            # Avoid repeating a challenged HTTP/FlareSolverr request for every board.
                            http_unavailable = True
                    if not _board_matches(key, board):
                        remaining = BROWSER_BUDGET - browser_used
                        if remaining <= 0:
                            raise ArenaBrowserError("public browser collection budget exhausted")
                        started = time.monotonic()
                        try:
                            board = arena_board(_browser_text(ARENA_URL + path,
                                timeout=min(BROWSER_TIMEOUT, remaining), session=browser_session))
                        finally:
                            browser_used += max(0, time.monotonic() - started)
                    if _board_matches(key, board):
                        boards[key] = {"path": path, **board}
                        errors.pop(key, None)
                    else:
                        errors[key] = "missing rows or leaderboard identity does not match requested board"
                except Exception as exc:
                    errors[key] = f"{type(exc).__name__}: {exc}"[:200]
                time.sleep(0.5)
            if not errors:
                break
            time.sleep(5)
        if len(boards) < max(1, len(wanted) // 2):
            raise ValueError(f"arena: only {len(boards)} boards parsed: {errors}")
        return {"boards": boards, "errors": errors}, now(), ARENA_URL
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if browser_session.get("id"):
            try:
                _close_browser(browser_session["id"])
            except ArenaBrowserError:
                if primary_error is None:
                    raise
                primary_error.add_note("public browser cleanup also failed; dedicated session may remain")
