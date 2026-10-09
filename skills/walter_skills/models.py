"""Model access for the curator postes, without holding provider keys in this module.

  editor : OpenAI via W.Alter's own Codex subscription session (`codex exec`, its own login — never Hermes' session,
           whose rotating refresh token must stay single-writer). Fallback: none (the action is postponed).
  judge  : a different family from the editor — Anthropic via walter_memory.llm (OpenRouter, budget-guarded).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/opt/walter-memory")

EDITOR_MODEL = "gpt-6.1-sol"                 # provisional holder of poste skills.editor
JUDGE_MODEL = "anthropic/claude-sonnet-5.5"  # provisional holder of poste skills.judge (other family than editor)


def codex_ready() -> bool:
    try:
        r = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and "not logged in" not in (r.stdout + r.stderr).lower()
    except Exception:
        return False


def editor(prompt: str, timeout: int = 900, effort: str = "high", model: str | None = None) -> str | None:
    """One-shot completion through `codex exec` (read-only sandbox, ephemeral, no repo). None if unavailable."""
    if not codex_ready():
        return None
    with tempfile.TemporaryDirectory(prefix="walter-curator-") as d:
        out = Path(d) / "last.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
               "-m", model or EDITOR_MODEL, "-c", f"model_reasoning_effort={effort}", "-o", str(out), "-"]
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or not out.exists():
            return None
        return out.read_text(errors="replace")


def judge(prompt: str) -> dict | None:
    from walter_memory import llm
    try:
        res = llm.chat([{"role": "user", "content": prompt}], model=JUDGE_MODEL, processor="skills.judge",
                       privacy_class="cloud_allowed", budget="recurring", timeout=180, purpose="curator review")
    except Exception:
        return None
    return parse_json(res["content"])


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
