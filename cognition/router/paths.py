"""Folders of the Walter Router module (software side; instance data comes from walter_router.instance)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
MIGRATIONS = ROOT / "store" / "migrations"
SITE = ROOT / "interface" / "site"
EVAL = ROOT / "eval"
AGENT_PROMPT = ROOT / "research" / "agent" / "prompt.md"
