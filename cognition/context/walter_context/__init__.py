"""walter-context: decides what enters a model's window on each call: what, how much, where, in what form.

Sub-modules: compress (the compression engine) · recover (originals behind compacted refs, from walter_logs) ·
config (the only tunables) · bridge (versioned JSON bridge for out-of-process hosts) · cli.
Planned (spec CONTEXT-ENGINE.md): sense · intent (understands the input in its conversation) · gather · compose. Runtime-agnostic: no host import here;
hosts plug in through ports/.
"""
from .compress import Epoch, Selection, Session, View, project
from .config import Config, load

__version__ = "0.3.0"
__all__ = ["Config", "Epoch", "Selection", "Session", "View", "load", "project"]
