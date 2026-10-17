"""Hermes transport adapter. Routing and validation are Walter-owned."""
import inspect
import sys
sys.path.insert(0, "/opt/walter-browse")
from walter_browse.facade import browse, WALTER_BROWSE_SCHEMA


def register(ctx):
    kwargs = dict(name="walter_browse", toolset="walter-web", schema=WALTER_BROWSE_SCHEMA,
                  handler=browse, is_async=True, emoji="🌐")
    parameters = inspect.signature(ctx.register_tool).parameters
    if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in parameters}
    ctx.register_tool(**kwargs)
