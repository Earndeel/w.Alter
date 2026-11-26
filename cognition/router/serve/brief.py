"""What an agent must know about Walter Router to use it: what it is for, how to call it, and the parameters that
matter — specialities, thinking levels, generation and analysis abilities, video objectives, hard constraints.
Never a model or provider name: choosing them is the router's job.

Generated from the database (tasks, video roles), so a new task or role reaches every agent without editing a prompt.
One text for every runtime: the tools carry the same names everywhere (Hermes plugin, walter MCP for Claude Code /
Codex / DSH). Hermes reads it as a system-prompt section (4 000 characters at most), the walter MCP server as its
instructions, the Codex / DSH profiles through the public file the refresh writes (`write`).
"""
from __future__ import annotations

import re
import hashlib
import json
import os
import tempfile

from walter_router import instance
from walter_router.serve.choose import REQUIREMENTS

MAX_CHARS = 4000
ANALYSIS = ("vision", "document", "long_context")   # chat tasks that read what they are given
GENERATION = (("Images", ("image",)), ("Video", ("video",)), ("Audio", ("audio", "music")))


def _short(text: str | None) -> str:
    """First sentence of a role description, without where it runs (« Via Flow… »: the router's business)."""
    first = re.split(r"(?<=[.!?])\s", (text or "").strip())[0]
    return first.split(" : ")[0].rstrip(".")


def _tasks(rows: list[dict], interfaces: tuple[str, ...], only: tuple[str, ...] = (), skip: tuple[str, ...] = ()) -> str:
    return " · ".join(f'`{r["task"]}` {r["label"]}' for r in rows if r["interface"] in interfaces
                      and (not only or r["task"] in only) and r["task"] not in skip)


def _web_quick() -> str:
    """The intents the owner's rule gives to a web chat service (knowledge.json web_services), as task keys."""
    from walter_router.analysis import knowledge
    try:
        rules = knowledge.load().get("web_services") or {}
    except (OSError, ValueError):
        return ""
    tasks = dict.fromkeys(t for k, r in rules.items() if not k.startswith("_") and isinstance(r, dict)
                          for t in (r.get("tasks") or {}))
    return " · ".join(f"`{t}`" for t in tasks)


def text(conn, owner: str | None = None) -> str:
    """Compact operational guidance, independent of current model names, prices and provider choices."""
    owner = owner or instance.owner()
    rows = list(conn.execute("""select task, label, interface from models.tasks
                                where not internal and interface <> 'tool' order by interface, task"""))
    roles = list(conn.execute("""select distinct on (role) role, label, description from models.preferences
                                 where task in ('text_to_video', 'image_to_video') order by role, priority"""))
    roles.sort(key=lambda r: {"default": 0, "premium": 1, "action": 2, "ugc": 3, "budget": 4}.get(r["role"], 9))
    quick = _web_quick()
    keys = lambda interfaces, only=(), skip=(): " · ".join(
        f"`{r['task']}`" for r in rows if r["interface"] in interfaces
        and (not only or r["task"] in only) and r["task"] not in skip)
    out = [
        "## Walter Router — choose and run a model for a sub-task",
        "You define the work, its constraints and its context; the router picks the model and provider from "
        "benchmarks, costs, subscriptions and " + owner + "'s preferences. You check the result and integrate it.",
        "Use it when a speciality or a distinct sub-task is worth the cost and latency of the hand-off. "
        "Every call must carry the facts and constraints the work needs.",
        "- `walter_run` executes. Give `request`, `task`, a complete `goal` for text, useful `context`. "
        "The executor does not see this conversation. Call it directly when the need is clear.",
        "- `walter_route` examines the choice, routes and prices without executing; useful to check or plan, "
        "never a prerequisite of `walter_run`. Without `task`, the router classifies the request; "
        "`conversation` explains a link with earlier exchanges.",
        "- `walter_decide` settles a short or repeated choice: `question`, `options` (at least two, name → meaning), "
        "`context`. For a long analysis, use a text task.",
        "- `walter_plans` reads the subscriptions; changing one must be asked by their owner.",
        "- `walter_web` converses with a web chat service enabled by " + owner + " (`message`, `files` as paths, "
        "`model` only if asked); verbatim answer, produced files as paths. Slow; on request.",
        *(["Quick question (" + quick + "): `walter_run` with `request` alone; the decision model hands it to the "
           "web chat service " + owner + " chose (usual route, and a notice if it fails)."] if quick else []),
        "`task=general`: L1 everyday, simple summary; L2 multi-step analysis or careful writing; "
        "L3 complex reasoning or high stakes. Specialities have their own ranking; do not impose a general level on them.",
        "Text: " + keys(("chat",), skip=ANALYSIS + ("general",)),
        "Analysis: " + keys(("chat",), only=ANALYSIS),
    ]
    for title, interfaces in GENERATION:
        line = keys(interfaces)
        if line:
            out.append(title + ": " + line)
    if roles:
        out.append("Video objective `role`: " + " · ".join(f"`{r['role']}`" for r in roles))
    out += [
        "Constraints `require`: `open_weights` open weights; `unrestricted` compatible content policy; "
        "`video_input` a route able to read a video (`task=vision`). Provide the sources; selection alone attaches no media.",
        "If the user names a model, pass `model` (optionally /variant) and `provider` if they impose one; "
        "no substitute. Favourites do not change without their decision.",
        "For text, limit `toolsets`, `max_turns`, `budget_seconds` as needed. Native tools: terminal/code and files; "
        "other capabilities through their commands if the terminal is allowed. Tools act on the router's host, "
        "with its rights; a remote harness's permissions are not inherited automatically.",
        "Never pass secrets or local_only data to a cloud model; the harness controls access classes.",
        "Paid media generation: only at the user's request; `image_urls`, `role`, "
        "`aspect_ratio`, `duration`, `resolution` depending on the medium. `paid_fallback` allows a planned manual paid route.",
        "Text: a failing provider → the next provider of the same model, history kept. "
        "All fail → explicit failure. A named provider restriction stays strict.",
        "Read `ok`, `routed`, `attempts`, `tools` and the errors. If `user_notification_required`, "
        "pass `user_notice` to the user, even on failure. Never announce success on selection alone.",
        "Text example: {\"request\":\"Fix this bug\",\"task\":\"coding\",\"goal\":\"…\",\"context\":\"…\"}. "
        "Transcription, embeddings, rerank and internal tasks serve the modules; do not offer them as usual tasks.",
    ]
    body = "\n".join(out)
    if len(body) > MAX_CHARS:
        raise ValueError(f"brief too long ({len(body)} > {MAX_CHARS} characters)")
    return body


def document(conn, owner: str | None = None) -> dict:
    content = text(conn, owner)
    return {"schema_version": 1, "note_version": 1, "id": "walter-router.usage", "module": "router",
            "format": "text/markdown", "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "chars": len(content), "required_tools": ["walter_route", "walter_run", "walter_decide", "walter_plans"],
            "placement": "stable_capabilities", "refresh": "next_owner_message",
            "source": {"command": "walter-router", "args": ["brief", "--json"]}}


def write(conn) -> bool:
    """Publish both representations from the same producer; keep unchanged bytes stable."""
    note = document(conn)
    contents = {"brief.md": note["content"] + "\n", "brief.json": json.dumps(note, ensure_ascii=False, indent=2) + "\n"}
    changed = False
    for name, new in contents.items():
        path = instance.state_file(name)
        if path.exists() and path.read_text() == new:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            f.write(new)
            temporary = f.name
        os.replace(temporary, path)
        changed = True
    return changed
