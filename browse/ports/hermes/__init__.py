"""Hermes transport adapter. Routing and validation are Walter-owned."""
import inspect
import logging
import sys
sys.path.insert(0, "/opt/walter-browse")
from walter_browse.facade import browse, WALTER_BROWSE_SCHEMA

log = logging.getLogger("walter_browse.hermes")


def register(ctx):
    """Register walter_browse with Hermes. Returns False, with a warning, when the host's plugin API has changed:
    a missing or broken register_tool must degrade the tool, never stop Hermes from starting."""
    register_tool = getattr(ctx, "register_tool", None)
    if not callable(register_tool):
        log.warning("walter_browse not registered: this Hermes plugin context has no register_tool")
        return False
    kwargs = dict(name="walter_browse", toolset="walter-web", schema=WALTER_BROWSE_SCHEMA,
                  handler=browse, is_async=True, emoji="🌐")
    try:
        parameters = inspect.signature(register_tool).parameters
    except (TypeError, ValueError):
        parameters = {}
    if parameters and not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in parameters}
    try:
        register_tool(**kwargs)
    except (AttributeError, TypeError) as exc:
        log.warning("walter_browse not registered: Hermes register_tool rejected it (%s)", exc)
        return False
    return True
