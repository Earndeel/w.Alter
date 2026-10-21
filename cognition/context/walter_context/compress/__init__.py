"""compress: the compression engine. History in, the most useful form of it for the budget out; nothing lost.

wire (message vocabulary) · digest (tool traffic) · layers (projection head | record | compact | live) ·
policy (when to cut, priced against the provider cache) · session (per-conversation state, request-only hosts) ·
checkpoint (replacement records for hosts that persist the compacted history).
"""
from .checkpoint import plan, summarize
from .layers import Epoch, View, project
from .session import Selection, Session

__all__ = ["Epoch", "Selection", "Session", "View", "plan", "project", "summarize"]
