"""Runtime-independent storage; all harnesses share the same Walter state, kept in the active instance."""
import functools
import os
import subprocess
from pathlib import Path


@functools.lru_cache(maxsize=1)
def instance_root() -> Path:
    """The active Walter instance, asked once through its public interface (`walter instance path`)."""
    out = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=30)
    if out.returncode or not out.stdout.strip():
        raise RuntimeError("no active Walter instance (walter instance path failed)")
    return Path(out.stdout.strip())


def state_home() -> Path:
    if os.environ.get("WALTER_BROWSE_STATE_DIR"):
        return Path(os.environ["WALTER_BROWSE_STATE_DIR"])
    return instance_root() / "state" / "browse"


def search_env_file() -> Path:
    """Search API keys of the instance (until `walter connect` serves them from its vault)."""
    if os.environ.get("WALTER_BROWSE_ENV_FILE"):
        return Path(os.environ["WALTER_BROWSE_ENV_FILE"])
    return instance_root() / "bootstrap" / "browse-search.env"
