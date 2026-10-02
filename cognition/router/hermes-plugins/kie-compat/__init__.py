"""Kie.ai compatibility shim (LLM request middleware; Hermes core untouched).

Kie's Anthropic endpoint (https://api.kie.ai/claude) answers HTTP 429 "Internal error" to any request carrying
``output_config`` — which Hermes adds for Claude 4.6+ adaptive thinking (``output_config.effort``). Hermes then
sees an empty stream and retries for ~3 minutes. Verified 2026-10-02 with direct calls: the same request without
``output_config`` succeeds (adaptive thinking, tools and 128k max_tokens are all accepted).

The shim removes ``output_config`` only for that endpoint; the model keeps adaptive thinking (its own effort).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
KIE_ANTHROPIC = "api.kie.ai/claude"


def _strip_output_config(request: Any = None, base_url: Any = None, api_mode: Any = None, **_: Any):
    if not isinstance(request, dict) or KIE_ANTHROPIC not in str(base_url or "") or "output_config" not in request:
        return None
    if api_mode not in (None, "", "anthropic_messages"):
        return None
    fixed = {k: v for k, v in request.items() if k != "output_config"}
    return {"request": fixed, "source": "kie-compat", "reason": "Kie /claude rejects output_config"}


def register(ctx: Any) -> None:
    if not callable(getattr(ctx, "register_middleware", None)):
        logger.error("KIE_COMPAT_DEGRADED register_middleware_missing")
        return
    ctx.register_middleware("llm_request", _strip_output_config)
