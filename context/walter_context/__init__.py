"""walter-context: builds the payload a model sees on each call, cache first. Runtime-agnostic (no Hermes import).

Core: wire (vocabulary) · digest (tool traffic) · layers (the projection) · policy (boundaries) · session (state).
Ports: ports/hermes (ContextEngine plugin), journal (context_recover over walter_logs), bench (replay).
"""
from .config import Config, load
from .layers import Epoch, View, project
from .session import Selection, Session

__version__ = "0.1.0"
__all__ = ["Config", "Epoch", "Selection", "Session", "View", "load", "project"]
