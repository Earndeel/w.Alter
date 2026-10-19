"""Public entry to Walter Memory's Google API client (Gmail/Calendar OAuth), for other modules.

The implementation lives with the connectors; callers import `walter_memory.google.Google` instead of
reaching into this module's directory.
"""
import importlib.util
from pathlib import Path

_source = Path(__file__).resolve().parents[1] / "connectors" / "google_api.py"
_spec = importlib.util.spec_from_file_location("walter_memory._google_api", _source)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
Google = _module.Google
