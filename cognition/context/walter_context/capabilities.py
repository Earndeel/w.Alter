"""Trusted module notes for the stable capability layer; no model call or compaction change.

The host supplies its actual tool inventory and a turn id. One snapshot per turn is retained
in memory by the host-owned TurnNotes instance. A new owner message starts a new snapshot.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess

from .config import capability_settings


def router_note(available_tools: list[str] | None = None) -> dict:
    base = {"version": 1, "engine": "walter-context", "id": "walter-router.usage",
            "injection_allowed": False, "placement": "stable_capabilities", "refresh": "next_owner_message"}
    try:
        settings = capability_settings()
    except (OSError, ValueError, KeyError, TypeError):
        return {**base, 'status': 'invalid', 'error': 'capability_settings_invalid'}
    if not settings['router_enabled']:
        return {**base, "status": "disabled"}
    try:
        out = subprocess.run(['walter-router','brief','--json'], capture_output=True, text=True,
                             timeout=settings['timeout_seconds'])
        if out.returncode:
            return {**base, 'status': 'unavailable', 'error': 'router_note_command_failed'}
        # The producer is trusted installation software; reject oversized output before parsing.
        if len(out.stdout) > settings['max_chars'] * 4:
            raise ValueError('oversized envelope')
        note = json.loads(out.stdout)
        content = note.get('content')
        if (note.get('schema_version') != 1 or note.get('note_version') != 1
                or note.get('id') != base['id'] or note.get('module') != 'router'
                or note.get('format') != 'text/markdown' or note.get('placement') != base['placement']
                or note.get('refresh') != base['refresh']
                or not isinstance(content,str) or not content or len(content) > settings['max_chars']
                or note.get('chars') != len(content)
                or note.get('sha256') != hashlib.sha256(content.encode()).hexdigest()):
            raise ValueError('invalid note')
        required = note.get('required_tools')
        if not isinstance(required,list) or not required or not all(isinstance(t,str) and t for t in required):
            raise ValueError('invalid tool requirements')
        if available_tools is not None and (not isinstance(available_tools,list) or not all(isinstance(t,str) for t in available_tools)):
            raise ValueError('invalid tool inventory')
        missing = sorted(set(required) - set(available_tools or []))
        allowed = available_tools is not None and not missing
        return {**base, 'status': 'ready' if allowed else 'missing_tools' if available_tools is not None else 'needs_tool_inventory',
                'injection_allowed': allowed, 'missing_tools': missing,
                'note_version': note['note_version'], 'sha256': note['sha256'], 'chars': note['chars'],
                'content': content if allowed else None, 'required_tools': required}
    except (OSError, subprocess.TimeoutExpired):
        return {**base, 'status': 'unavailable', 'error': 'router_note_unavailable'}
    except (ValueError, TypeError, AttributeError):
        return {**base, 'status': 'invalid', 'error': 'router_note_invalid'}


class TurnNotes:
    """Owned by a host context session; no global cache, file cache, thread or identity store."""
    def __init__(self):
        self._turn = None
        self._snapshot = None

    def prepare(self, turn_id: str, available_tools: list[str]) -> dict:
        if not isinstance(turn_id,str) or not turn_id:
            raise ValueError('owner turn id required')
        if turn_id != self._turn:
            self._snapshot = router_note(available_tools)
            self._turn = turn_id
        result = copy.deepcopy(self._snapshot)
        missing = sorted(set(result.get('required_tools') or []) - set(available_tools))
        if missing:
            result.update(injection_allowed=False, content=None, status='missing_tools', missing_tools=missing)
        return result


# ---- Module layer: every agent-facing module presents itself (level 1, manifest/MANIFEST.md), composed per owner turn
# Source: `walter present notes` (walter-core's declared CLI), which reads module contracts and runs the brief
# commands they declare. Level 2 (index) and the detailed guide stay behind the module_index / module_guide tools.

LAYER_ID = "walter-modules.layer"
LAYER_TOOLS = ("module_index", "module_guide")
HEADER = ("## Modules W.Alter\n"
          "Chaque module branché se présente ci-dessous (niveau 1 : ce que c'est, son organisation, comment s'en servir), "
          "depuis le dossier manifest/ du module. Pour aller plus loin, seulement si la tâche le demande : "
          "`module_index(module, section)` liste ce qu'il contient, tenu à jour par le module ; "
          "`module_guide(module)` donne son guide détaillé (D3) ; puis l'outil de l'élément.")
HEADER_M0 = ("## Modules W.Alter\n"
             "Chaque module branché tient en une ligne (D1). Sa fiche d'utilisation (D2 : outils, paramètres, "
             "conventions) accompagne un message quand elle est utile et se lit à tout moment avec "
             "`module_guide(module, depth=\"D2\")` ; `depth=\"D3\"` donne sa documentation détaillée, "
             "`module_index(module, section)` ce qu'il contient. Lire une documentation n'oblige pas à utiliser le "
             "module.")
HEADER_BARE = "## Modules W.Alter"


def _valid_note(note: dict, max_chars: int) -> bool:
    content = note.get("content")
    required = note.get("required_tools")
    return (note.get("schema_version") == 1 and note.get("note_version") == 1
            and isinstance(note.get("id"), str) and note["id"] and isinstance(note.get("module"), str)
            and note.get("format") == "text/markdown" and note.get("placement") == "stable_capabilities"
            and note.get("refresh") == "next_owner_message"
            and isinstance(content, str) and content and len(content) <= max_chars and note.get("chars") == len(content)
            and note.get("sha256") == hashlib.sha256(content.encode()).hexdigest()
            and isinstance(required, list) and all(isinstance(t, str) and t for t in required))


def module_notes(available_tools: list[str] | None, form: str = "full", m1: list[str] | None = None) -> dict:
    """Every module's note (M1 for all in form 'full'; M0 for all + M1 for `m1` in form 'm0'), validated,
    with injection allowed only when the module's tools are really present."""
    base = {"version": 1, "engine": "walter-context", "id": LAYER_ID}
    try:
        settings = capability_settings()
    except (OSError, ValueError, KeyError, TypeError):
        return {**base, "status": "invalid", "error": "capability_settings_invalid", "notes": []}
    if not settings["modules_enabled"]:
        return {**base, "status": "disabled", "notes": []}
    if available_tools is not None and (not isinstance(available_tools, list)
                                        or not all(isinstance(t, str) for t in available_tools)):
        return {**base, "status": "invalid", "error": "invalid_tool_inventory", "notes": []}
    try:
        if form not in ("full", "m0") or not all(isinstance(x, str) and x for x in (m1 or [])):
            raise ValueError("invalid form or module selection")
        args = ["walter", "present", "notes", "--form", form] + [a for x in (m1 or []) for a in ("--m1", x)]
        out = subprocess.run(args, capture_output=True, text=True,
                             timeout=settings["timeout_seconds"])
        if out.returncode or len(out.stdout) > settings["layer_max_chars"] * 8:
            return {**base, "status": "unavailable", "error": "module_notes_command_failed", "notes": []}
        doc = json.loads(out.stdout)
        if doc.get("schema_version") != 1 or not isinstance(doc.get("notes"), list):
            raise ValueError("invalid notes document")
    except (OSError, subprocess.TimeoutExpired):
        return {**base, "status": "unavailable", "error": "module_notes_unavailable", "notes": []}
    except (ValueError, TypeError, AttributeError):
        return {**base, "status": "invalid", "error": "module_notes_invalid", "notes": []}
    have = set(available_tools or [])
    notes, seen = [], set()
    for note in doc["notes"]:
        if not isinstance(note, dict) or not _valid_note(note, settings["max_chars"]) or note["id"] in seen:
            notes.append({"id": note.get("id") if isinstance(note, dict) else None, "status": "invalid",
                          "injection_allowed": False, "content": None})
            continue
        seen.add(note["id"])
        missing = sorted(set(note["required_tools"]) - have)
        allowed = available_tools is not None and not missing
        notes.append({"id": note["id"], "module": note["module"], "level": note.get("level", "M1"),
                      "sha256": note["sha256"], "chars": note["chars"],
                      "required_tools": note["required_tools"], "missing_tools": missing,
                      "status": "ready" if allowed else "missing_tools" if available_tools is not None
                      else "needs_tool_inventory", "injection_allowed": allowed,
                      "content": note["content"] if allowed else None})
    problems = [p.get("module") for p in doc.get("problems") or [] if isinstance(p, dict)]
    return {**base, "status": "ready", "notes": notes, "problems": problems}


M0_TITLE = "### Capacités (une ligne par module)"


def compose(available_tools: list[str] | None, form: str = "full", m1: list[str] | None = None) -> dict:
    """The stable 'Modules W.Alter' layer, in presentation order, within budget.

    form='full' (default): header + every module's M1 (manifest/MANIFEST.md).
    form='m0': header + one M0 line per module (always), then the M1 of the modules in `m1` (chosen by the plan).
    """
    result = module_notes(available_tools, form, m1)
    base = {k: result[k] for k in ("version", "engine", "id")}
    base.update(placement="stable_capabilities", refresh="next_owner_message", form=form)
    if result["status"] != "ready":
        return {**base, "status": result["status"], "error": result.get("error"), "injection_allowed": False,
                "content": None, "modules": [], "skipped": []}
    settings = capability_settings()
    have = set(available_tools or [])
    header = (HEADER_M0 if form == "m0" else HEADER) if set(LAYER_TOOLS) <= have else HEADER_BARE
    lines, sections, modules, skipped = [], [], [], []
    size = len(header) + (len(M0_TITLE) + 2 if form == "m0" else 0)
    for note in result["notes"]:
        if not note["injection_allowed"]:
            skipped.append({"id": note["id"], "status": note["status"], "missing_tools": note.get("missing_tools", [])})
            continue
        text = note["content"].strip()
        if note.get("level") != "M0" and text.startswith("## "):  # a bare note's top heading becomes a section
            text = "#" + text
        cost = len(text) + (1 if note.get("level") == "M0" else 2)
        if size + cost > settings["layer_max_chars"]:
            skipped.append({"id": note["id"], "status": "over_budget"})
            continue
        (lines if note.get("level") == "M0" else sections).append(text)
        modules.append({"id": note["id"], "module": note["module"], "level": note.get("level", "M1"),
                        "sha256": note["sha256"], "chars": len(text)})
        size += cost
    if not lines and not sections:
        return {**base, "status": "empty", "injection_allowed": False, "content": None, "modules": [],
                "skipped": skipped, "problems": result["problems"]}
    blocks = [header] + ([M0_TITLE + "\n" + "\n".join(lines)] if lines else []) + sections
    content = "\n\n".join(blocks)
    return {**base, "status": "ready", "injection_allowed": True, "content": content, "chars": len(content),
            "sha256": hashlib.sha256(content.encode()).hexdigest(), "modules": modules, "skipped": skipped,
            "problems": result["problems"]}


class TurnLayer:
    """Host-owned snapshot of the composed module layer: identical bytes for the whole owner turn."""
    def __init__(self):
        self._turn = None
        self._snapshot = None

    def prepare(self, turn_id: str, available_tools: list[str], form: str = "full",
                m1: list[str] | None = None) -> dict:
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("owner turn id required")
        if turn_id != self._turn:
            self._snapshot = compose(available_tools, form, m1)
            self._turn = turn_id
        return copy.deepcopy(self._snapshot)


def declared_tools() -> list[str]:
    """Tool inventory of the shared walter MCP server, as the module contracts declare it (for file profiles)."""
    out = subprocess.run(["walter", "present", "catalog"], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise RuntimeError("walter present catalog failed")
    tools = {t for m in json.loads(out.stdout)["modules"] for t in m["tools"]}
    return sorted(tools | set(LAYER_TOOLS))


def write_layer() -> dict:
    """Publish the layer for runtimes whose profile is a file (Codex, DSH via walter-soul): @instance/state/context/
    modules.md, rewritten only when it changed; then walter-soul re-renders the profiles that include it."""
    import os
    import shutil
    import tempfile
    from pathlib import Path
    layer = compose(declared_tools())
    if not layer["injection_allowed"]:
        return {"written": None, "changed": False, "status": layer["status"]}
    out = subprocess.run(["walter", "instance", "path", "state/context/modules.md"], capture_output=True, text=True,
                         timeout=30)
    if out.returncode:
        raise RuntimeError("walter instance path failed")
    path = Path(out.stdout.strip())
    new = layer["content"] + "\n"
    changed = not (path.exists() and path.read_text() == new)
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            f.write(new)
            temporary = f.name
        os.replace(temporary, path)
        if shutil.which("walter-soul"):
            subprocess.run(["walter-soul", "sync"], capture_output=True, timeout=120)
    return {"written": str(path), "changed": changed, "chars": layer["chars"], "sha256": layer["sha256"],
            "modules": [m["module"] for m in layer["modules"]]}
