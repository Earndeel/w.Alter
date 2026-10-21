"""Models of the owner's ChatGPT/Codex subscription (read through Hermes)."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from walter_router import instance
from walter_router.research.web import now

HERMES_HOME = instance.hermes_home()
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"


def source_codex() -> tuple[dict, datetime, str]:
    """Live Codex catalogue of the owner's ChatGPT account, read through Hermes (read-only; token never printed)."""
    code = ("import json; from hermes_cli.models import _codex_catalog; "
            "print(json.dumps(_codex_catalog('openai-codex', False)))")
    out = subprocess.run([str(HERMES_PY), "-c", code], cwd=str(HERMES_HOME / "hermes-agent"), capture_output=True,
                         text=True, timeout=120, env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    ids = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 and out.stdout.strip() else []
    if not ids:
        raise ValueError(f"codex: catalogue unavailable (exit {out.returncode})")
    return {"models": ids}, now(), "chatgpt.com/backend-api/codex (account catalogue)"
