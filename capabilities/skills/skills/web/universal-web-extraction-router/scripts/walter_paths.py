"""Runtime-independent storage; all harnesses share the same Walter state."""
import os
from pathlib import Path

def state_home() -> Path:
    return Path(os.environ.get("WALTER_BROWSE_STATE_DIR", "/walter/capabilities/browse/state"))
