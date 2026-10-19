"""walter_memory — Walter Memory core library (spec: /root/.hermes/docs/walter-memory/ARCHITECTURE.md).

Truth = core.events (append-only, observed) + core.objects (Raw Vault). Everything else is derived.
Connectors write only through this library or the HTTP gateway (never directly into Kardex/Hindsight).
"""
from importlib import import_module

__all__ = ["record_event", "record_events", "get_events", "upsert_identity", "put_object", "get_object"]


def __getattr__(name):
    # The stdlib HTTP client is usable from a harness without installing DB/S3 dependencies.
    if name not in __all__:
        raise AttributeError(name)
    module = 'objects' if name in {'put_object', 'get_object'} else 'events'
    value = getattr(import_module('.' + module, __name__), name)
    globals()[name] = value
    return value
