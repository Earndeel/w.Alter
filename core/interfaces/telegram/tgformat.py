"""Telegram rendering of the engine's answers (lot E7): Markdown → the small HTML subset Telegram accepts, chunks.

Telegram refuses a whole message on one bad tag, so the conversion is conservative: everything is HTML-escaped first,
then only fenced code, inline code, bold, italic, headings and links become tags. Callers fall back to plain text
when Telegram still refuses (`plain`)."""
from __future__ import annotations

import html
import re

LIMIT = 3900          # Telegram: 4096 characters per message, margin for tags

_FENCE = re.compile(r"```[^\n`]*\n?(.*?)```", re.S)
_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITAL = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_HEAD = re.compile(r"^#{1,6}\s+(.+)$", re.M)
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


def to_html(md: str) -> str:
    """Markdown → Telegram HTML. Code is protected from the other rules."""
    slots: list[str] = []

    def keep(fragment: str) -> str:
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    text = html.escape(md or "", quote=False)
    text = _FENCE.sub(lambda m: keep(f"<pre>{m.group(1).rstrip()}</pre>"), text)
    text = _CODE.sub(lambda m: keep(f"<code>{m.group(1)}</code>"), text)
    text = _LINK.sub(lambda m: keep(f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>'), text)
    text = _HEAD.sub(lambda m: f"<b>{m.group(1).strip()}</b>", text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _ITAL.sub(lambda m: f"<i>{m.group(1)}</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def plain(md: str) -> str:
    return md or ""


def chunks(text: str, limit: int = LIMIT) -> list[str]:
    """Split on paragraph, then line, then hard boundaries; never an empty chunk. Code fences stay balanced."""
    text = (text or "").strip()
    if not text:
        return []
    out: list[str] = []
    cur = ""
    for block in re.split(r"(\n\n)", text):
        if len(cur) + len(block) <= limit:
            cur += block
            continue
        if cur.strip():
            out.append(cur)
        cur = ""
        while len(block) > limit:
            cut = block.rfind("\n", 0, limit)
            cut = cut if cut > limit // 2 else limit
            out.append(block[:cut])
            block = block[cut:]
        cur = block
    if cur.strip():
        out.append(cur)
    fixed: list[str] = []
    carry = False                      # a fence opened in the previous chunk: reopen it here
    for c in out:
        c = c.strip("\n")
        if carry:
            c = "```\n" + c
        carry = c.count("```") % 2 == 1
        fixed.append(c + ("\n```" if carry else ""))
    return fixed


TOOL_LABELS = {
    "memory": "mémoire", "person_lookup": "personnes", "walter_browse": "web", "walter_web": "web",
    "browse": "web", "web_search": "web", "skills": "skills", "skill_read": "skills", "walter_route": "router",
    "walter_call": "outil Walter", "subagent": "sous-agent", "bash": "commande", "read": "lecture",
    "write": "écriture", "edit": "écriture", "vault": "coffre de fichiers", "secret": "secrets",
}


# what the owner reads while a turn works (2026-11-27): the capability at work, never « python »; from the engine's
# own events (progress=1 stream), no model call. None = internal bookkeeping, not shown.
PROGRESS = (
    (("memory_", "person_lookup", "tasks_list", "task_"), "🧠 mémoire"),
    (("walter_browse", "browser_session", "browser_sites"), "🔎 recherche web"),
    (("walter_web",), "💬 service web"),
    (("skills_", "skill_read"), "📖 procédures"),
    (("subagent", "send_message"), "🧩 délégation"),
    (("audio_transcribe",), "🎙 transcription"),
    (("vault_",), "🗂 fichiers du coffre"),
    (("logs_", "context_recover"), "📜 journaux"),
    (("module_guide", "module_index", "walter_modules", "walter_profile"), "📚 documentation"),
    (("walter_health",), "🩺 état de Walter"),
    (("computer_use",), "🖥 Mac"),
    (("secret_",), "🔐 coffre-fort"),
    (("beeper_",), "💬 messages"),
    (("walter_route", "walter_plans", "walter_decide"), "🧭 Router"),
    (("bash", "read", "grep", "glob", "write", "edit", "read_image"), "💻 fichiers et commandes"),
)
RUN_TASKS = {"image": "🎨 génération d'image", "video": "🎬 génération vidéo", "voice": "🎵 audio", "music": "🎵 audio",
             "tts": "🎵 audio", "stt": "🎙 transcription", "front": "🖌 interface", "code": "🛠 code", "coding": "🛠 code"}
SILENT = ("job_output", "job_list", "job_kill", "list_agents", "interrupt_agent", "present", "ask_user_question")


def progress_label(name: str, task: str = "") -> str | None:
    """A capability called during a turn as the owner reads it (`mcp__walter__walter_browse` → « 🔎 recherche web »;
    walter_run on the image poste → « 🎨 génération d'image »). None: not worth showing."""
    short = (name or "").split("__")[-1].lower()
    if short in SILENT:
        return None
    if short == "python":
        return "⚙️ analyse"
    if short in ("walter_run",):
        base = (task or "").split("/")[0]
        return RUN_TASKS.get(base) or next((v for k, v in RUN_TASKS.items() if base.startswith(k)), "⚙️ modèle spécialisé")
    for keys, label in PROGRESS:
        if any(short == k or (k.endswith("_") and short.startswith(k)) for k in keys):
            return label
    return "⚙️ " + short.replace("_", " ")


def tool_label(name: str) -> str:
    """A tool as the owner reads it: `mcp__walter__memory_search` → « mémoire »."""
    short = (name or "").split("__")[-1].lower()
    for key, label in TOOL_LABELS.items():
        if short == key or short.startswith(key):
            return label
    return short.replace("_", " ") or "outil"
