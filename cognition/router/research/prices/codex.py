"""Models of the owner's ChatGPT/Codex subscription, read with W.Alter's own Codex session (2026-11-10: no longer
through Hermes; plan/codex_account.py)."""
from __future__ import annotations

from datetime import datetime

from walter_router.plan import codex_account
from walter_router.research.web import now


def source_codex() -> tuple[dict, datetime, str]:
    """Live Codex catalogue of the owner's ChatGPT account (read-only; token never printed)."""
    return {"models": codex_account.catalog()}, now(), "chatgpt.com/backend-api/codex (account catalogue)"
