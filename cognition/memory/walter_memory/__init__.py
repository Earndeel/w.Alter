"""walter_memory — Walter Memory core library (spec: /root/.hermes/docs/walter-memory/ARCHITECTURE.md).

Truth = core.events (append-only, observed) + core.objects (Raw Vault). Everything else is derived.
Connectors write only through this library or the HTTP gateway (never directly into Kardex/Hindsight).
"""
from .events import get_events, record_event, record_events, upsert_identity
from .objects import get_object, put_object

__all__ = ["record_event", "record_events", "get_events", "upsert_identity", "put_object", "get_object"]
