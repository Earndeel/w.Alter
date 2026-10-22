"""Walter Router tools for Hermes (plugin; Hermes core is never patched).

walter_route  which model/provider for a task, from the owner's favourites and the router's model database
              (the `walter-router` command): role by objective, route, workflow, cost, constraints.
walter_run    runs a text sub-task on the routed model in a separate one-shot Hermes process
              (`hermes chat --oneshot --provider P -m M`, the public CLI — plugin tools receive no parent agent,
              so delegate_task cannot be pinned to a model from here). Falls back to the next route on failure.
"""
from __future__ import annotations

import asyncio
import json
import re
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

CLI = os.environ.get("WALTER_ROUTER_CLI", "walter-router")   # Walter Router command on the PATH
HERMES_BIN = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "hermes-agent" / "venv" / "bin" / "hermes"
CHILD_ENV = "WALTER_ROUTER_CHILD"
ALLOWED_TOOLSETS = ("web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory")
DEFAULT_TOOLSETS = ["web", "walter-web", "file", "terminal"]
MAX_ATTEMPTS = 3
LAST_RESORT = {"hermes_provider": "openai-codex", "model": "gpt-6.1-sol", "reasoning": "high"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
FAILURE_MARKS = ("didn't answer after", "Provider said:", "looks temporarily unavailable")
FALLBACK_TASKS = ["general", "coding", "frontend", "ui_component", "3d", "gamedev", "dataviz", "svg", "fullstack",
                  "mobile_app", "vision", "document", "text_to_image", "image_edit", "logo", "graphic_design",
                  "text_to_video", "image_to_video", "video_edit", "tts", "speech_to_speech", "music", "weather",
                  "calculation", "research"]


async def _cli(*args: str, timeout: int = 60) -> dict:
    proc = await asyncio.create_subprocess_exec(CLI, *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((err or out).decode("utf-8", "replace")[-400:])
    return json.loads(out)


def _tasks() -> tuple[list[str], str]:
    import subprocess
    try:
        rows = json.loads(subprocess.run([CLI, "tasks"], capture_output=True, text=True, timeout=20).stdout)
        return [r["task"] for r in rows], "; ".join(f'{r["task"]} = {r["label"]}' for r in rows)
    except Exception as exc:  # noqa: BLE001 — the tool must still register
        logger.warning("WALTER_ROUTER tasks unavailable: %s", exc)
        return FALLBACK_TASKS, ", ".join(FALLBACK_TASKS)


TASKS, TASK_HELP = _tasks()


async def _decide(args: Mapping[str, Any]) -> dict:
    """With a task: that task. Without: the decision model classifies the request (task, video role, level,
    unrestricted), reading `conversation` too when the request depends on earlier turns."""
    task = str(args.get("task") or "").strip()
    if task and task not in TASKS:
        raise ValueError(f"unknown task {task}; use one of {TASKS}")
    request = str(args.get("request") or "")
    if args.get("require"):
        cmd = ["pick", task or "general", "--require", str(args["require"])]
    else:
        cmd = ["route", request] + (["--task", task] if task else [])
        if args.get("conversation"):
            cmd += ["--context", str(args["conversation"])[:600]]
    if args.get("level") in ("L1", "L2", "L3"):
        cmd += ["--level", str(args["level"])]
    return await _cli(*cmd)


def _compact(d: dict) -> dict:
    keep = ("task", "mode", "role", "role_label", "matched_signals", "model_id", "variant", "display_name", "provider",
            "level", "objective", "quality", "quality_unit", "real_cost", "cost_unit", "why", "warning", "require",
            "score_from_base", "unrestricted_signals", "role_source")
    out = {k: d[k] for k in keep if d.get(k) not in (None, [], "")}
    if d.get("profile"):
        out["profile"] = {k: v for k, v in d["profile"].items() if v}
    if d.get("execution"):
        out["execution"] = [_route_line(e) for e in d["execution"][:6]]
    route = d.get("route") or {}
    if route.get("paid") and not d.get("execution"):   # media decisions only: a chat model's cost is per route
        out["media_route"] = {k: route["paid"].get(k) for k in ("provider", "offer_key", "cost", "unit", "by_resolution")}
    if d.get("ui"):
        out["ui"] = d["ui"]
    if isinstance(d.get("intent"), dict):
        out["intent"] = {k: d["intent"].get(k) for k in ("task", "task_confidence", "video_role", "level",
                                                          "unrestricted", "error") if d["intent"].get(k) is not None}
    if d.get("brief"):
        out["brief"] = d["brief"]
    if d.get("alternatives"):
        out["alternatives"] = d["alternatives"][:5]
    return out


def _route_line(e: dict) -> dict:
    """One execution route as the agent needs it: who runs it, and what a million tokens costs there (in / out):
    the subscription's cost price while its quota lasts, else the host's or provider's price."""
    line = {k: e.get(k) for k in ("hermes_provider", "model", "reasoning", "probe_ok", "fallback_for") if e.get(k) is not None}
    sub = e.get("subscription") or {}
    price = e.get("cost_price_1m") or ({"in": e["host"]["price_in_1m"], "out": e["host"]["price_out_1m"]}
                                       if (e.get("host") or {}).get("price_in_1m") is not None else None)
    if price:
        line["usd_per_1m"] = {k: round(v, 4) for k, v in price.items() if v is not None}
    elif e.get("blended_1m") is not None:
        line["usd_per_1m_blended"] = round(e["blended_1m"], 4)
    if sub:
        line["subscription"] = {"plan": sub.get("plan"), "quota_used_percent": sub.get("quota_used_percent")}
    if (e.get("host") or {}).get("host"):
        line["host"] = e["host"]["host"]
    return line


async def _handle_route(args: Mapping[str, Any], **_: Any) -> str:
    try:
        return json.dumps(_compact(await _decide(args)), ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_route: {exc}"}, ensure_ascii=False)


async def _log(entry: dict) -> None:
    """Every routed attempt goes to models.exec_log: the router demotes provider x model pairs that keep failing."""
    try:
        await _cli("log-exec", json.dumps(entry, default=str), timeout=20)
    except Exception as exc:  # noqa: BLE001 — logging must never break a run
        logger.warning("WALTER_ROUTER log-exec failed: %s", exc)


async def _run_once(route: dict, prompt_file: str, toolsets: list[str], max_turns: int, budget: int) -> tuple[bool, str]:
    cmd = [str(HERMES_BIN), "chat", "--query-file", prompt_file, "--oneshot", "-Q", "--provider",
           route["hermes_provider"], "-m", route["model"], "-t", ",".join(toolsets), "--max-turns", str(max_turns),
           "--run-budget", str(budget), "--source", "walter-router"]
    if route.get("reasoning"):
        cmd += ["--reasoning", route["reasoning"]]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                env={**os.environ, CHILD_ENV: "1"})
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=budget + 120)
    except asyncio.TimeoutError:
        proc.kill()
        return False, f"timeout after {budget + 120}s"
    text = _ANSI.sub("", out.decode("utf-8", "replace"))
    lines = [ln for ln in text.splitlines() if not ln.startswith("session_id:")]
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith(("⚠", "Run 'hermes doctor'"))
                     or "Config issues detected" in lines[0]):
        lines.pop(0)  # Hermes start-up config warnings are not the sub-agent's answer
    text = "\n".join(lines).strip()
    failed = proc.returncode != 0 or not text or any(m in text[-600:] for m in FAILURE_MARKS)
    return not failed, text


# Providers whose outages are frequent and slow to detect inside Hermes (7 retries ~ 3 min): a 5-token test first.
PREFLIGHT = {"kie": "kie", "kie-codex": "kie-codex"}


async def _preflight(status_key: str) -> bool:
    try:
        out = await _cli("probe", "--provider", status_key, "--timeout", "25", timeout=40)
        return bool(out.get(status_key, {}).get("ok"))
    except Exception:  # noqa: BLE001
        return False


async def _handle_run(args: Mapping[str, Any], **_: Any) -> str:
    started = time.monotonic()
    goal = str(args.get("goal") or "").strip()
    if not goal:
        return json.dumps({"error": "walter_run: goal is required"})
    try:
        d = await _decide(args)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_run: routing failed: {exc}"}, ensure_ascii=False)
    routes = d.get("execution") or []
    if not routes:
        return json.dumps({"error": "walter_run runs text tasks only; for image/video/voice/music use your media "
                                    "tools with this routing decision", "decision": _compact(d)},
                          ensure_ascii=False, default=str)
    toolsets = [t for t in (args.get("toolsets") or DEFAULT_TOOLSETS) if t in ALLOWED_TOOLSETS] or DEFAULT_TOOLSETS
    max_turns = max(1, min(int(args.get("max_turns") or 40), 120))
    budget = max(60, min(int(args.get("budget_seconds") or 900), 3600))
    prompt = goal if not args.get("context") else f"{goal}\n\nContexte :\n{args['context']}"
    attempts = []
    with tempfile.NamedTemporaryFile("w", suffix=".txt", prefix="walter-run-", delete=False) as fh:
        fh.write(prompt)
        prompt_file = fh.name
    try:
        runs = 0
        for route in routes:
            if runs >= MAX_ATTEMPTS:
                break
            preflightable = route["hermes_provider"] in PREFLIGHT
            # a substitute (fallback_for set) is identified by its provider model id only
            base = {"task": d.get("task"), "role": d.get("role"),
                    "model_id": None if route.get("fallback_for") else d.get("model_id"),
                    "provider": route["hermes_provider"], "model": route["model"],
                    "fallback_for": route.get("fallback_for")}
            if preflightable and not await _preflight(PREFLIGHT[route["hermes_provider"]]):
                attempts.append({"provider": route["hermes_provider"], "model": route["model"], "ok": False,
                                 "skipped": "provider test failed just before the run"})
                await _log({**base, "ok": False, "skipped": "preflight"})
                continue
            if route.get("probe_ok") is False and not preflightable:
                # known down (e.g. OpenRouter without credit): skip, it stays as the very last resort below
                attempts.append({"provider": route["hermes_provider"], "model": route["model"], "ok": False,
                                 "skipped": "last provider test failed"})
                continue
            runs += 1
            t0 = time.monotonic()
            ok, text = await _run_once(route, prompt_file, toolsets, max_turns, budget)
            await _log({**base, "ok": ok, "seconds": round(time.monotonic() - t0, 1)})
            attempts.append({"provider": route["hermes_provider"], "model": route["model"], "ok": ok})
            logger.info("WALTER_ROUTER_RUN task=%s model=%s provider=%s ok=%s", d.get("task"), route["model"],
                        route["hermes_provider"], ok)
            if ok:
                return json.dumps({"routed": {"task": d.get("task"), "role": d.get("role"), "model": route["model"],
                                              "fallback_for": route.get("fallback_for"),
                                              "provider": route["hermes_provider"], "reasoning": route.get("reasoning"),
                                              "attempts": attempts,
                                              "seconds": round(time.monotonic() - started)},
                                   "output": text[-30000:]}, ensure_ascii=False)
        tried = {a["provider"] for a in attempts}
        if "openai-codex" not in tried and not (d.get("require") == "unrestricted" or d.get("unrestricted_signals")):
            # Last resort: the owner's ChatGPT subscription (no per-call cost), flagged as a substitution.
            ok, text = await _run_once(LAST_RESORT, prompt_file, toolsets, max_turns, budget)
            attempts.append({"provider": "openai-codex", "model": LAST_RESORT["model"], "ok": ok,
                             "last_resort": True})
            if ok:
                return json.dumps({"routed": {"task": d.get("task"), "role": d.get("role"),
                                              "model": LAST_RESORT["model"], "provider": "openai-codex",
                                              "substituted_for": d.get("model_id"), "attempts": attempts,
                                              "seconds": round(time.monotonic() - started)},
                                   "output": text[-30000:]}, ensure_ascii=False)
        return json.dumps({"error": "every route failed", "attempts": attempts,
                           "last_output": (locals().get("text") or "")[-1500:]},
                          ensure_ascii=False)
    finally:
        os.unlink(prompt_file)


ROUTE_SCHEMA = {
    "name": "walter_route",
    "description": (
        "Which model (and provider) to use for a task, chosen by Walter Router from the owner's declared favourites "
        "and the nightly benchmark/price database. Call it BEFORE generating an image/video/voice/music or before "
        "delegating any substantial work, and follow its answer: model, provider, route, workflow steps to plan "
        "(e.g. Seedance needs reference images first), cost, warnings. For video the role depends on the objective "
        "(premium, action, UGC, budget...). Pass the user's request verbatim in `request`; leave `task` empty and "
        "the router's decision model picks task, video objective, level and constraints. When the request only "
        "makes sense with earlier turns (« fais la suite », « pareil en mieux »), say what it is about in "
        "`conversation`. Set `task` (and `level` for general) only to force them. Each execution route shows its "
        "price per million tokens (a subscription at its cost price). If the chosen role looks wrong, use the "
        "`brief` to pick the right one. Tasks: " + TASK_HELP
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "enum": TASKS,
                     "description": "Optional: force the task family (otherwise classified from the request)."},
            "request": {"type": "string", "description": "The user's request, verbatim (French is fine)."},
            "conversation": {"type": "string", "description": "Optional: one line on what the conversation was "
                             "about, when the request depends on earlier turns."},
            "require": {"type": "string", "enum": ["unrestricted", "open_weights"],
                        "description": "Hard constraint, only when the request needs it."},
            "level": {"type": "string", "enum": ["L1", "L2", "L3"],
                      "description": "general only: L1 everyday, L2 harder, L3 hardest / highest stakes."},
        },
        "required": ["request"],
    },
}

RUN_SCHEMA = {
    "name": "walter_run",
    "description": (
        "Run a self-contained TEXT sub-task (analysis, comparison, code, writing, research synthesis...) on the "
        "model Walter Router picks for its task, in a separate Hermes run with its own tools; returns the result and "
        "which model ran it. Falls back to the next provider if one fails. Use it instead of doing heavy work "
        "yourself when another model is better suited or cheaper. Write `goal` as complete instructions (the "
        "sub-agent does not see this conversation). Not for image/video/voice/music: use walter_route + media tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "enum": TASKS, "description": "Optional: force the task family."},
            "request": {"type": "string", "description": "The user's request verbatim (used for routing)."},
            "conversation": {"type": "string", "description": "Optional: one line on what the conversation was "
                             "about, when the request depends on earlier turns (used for routing)."},
            "goal": {"type": "string", "description": "Complete, self-contained instructions for the sub-agent."},
            "context": {"type": "string", "description": "Facts/files/excerpts the sub-agent needs."},
            "level": {"type": "string", "enum": ["L1", "L2", "L3"]},
            "require": {"type": "string", "enum": ["unrestricted", "open_weights"]},
            "toolsets": {"type": "array", "items": {"type": "string", "enum": list(ALLOWED_TOOLSETS)},
                         "description": "Tools for the sub-agent (default web, walter-web, file, terminal)."},
            "max_turns": {"type": "integer", "description": "Tool iterations (default 40, max 120)."},
            "budget_seconds": {"type": "integer", "description": "Wall-clock budget (default 900, max 3600)."},
        },
        "required": ["request", "goal"],
    },
}


async def _handle_verdict(args: Mapping[str, Any], **_: Any) -> str:
    try:
        cmd = ["verdict", str(int(args["alert_id"])), "adopted" if args.get("decision") == "adopter" else "dismissed"]
        if args.get("note"):
            cmd += ["--note", str(args["note"])]
        if args.get("role"):
            cmd += ["--role", str(args["role"])]
        return json.dumps(await _cli(*cmd), ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_verdict: {exc}"}, ensure_ascii=False)


async def _handle_feedback(args: Mapping[str, Any], **_: Any) -> str:
    try:
        cmd = ["feedback", str(args.get("model") or "last"), str(int(args["rating"]))]
        if args.get("task"):
            cmd += ["--task", str(args["task"])]
        if args.get("note"):
            cmd += ["--note", str(args["note"])]
        return json.dumps(await _cli(*cmd), ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_feedback: {exc}"}, ensure_ascii=False)


async def _handle_plans(args: Mapping[str, Any], **_: Any) -> str:
    """The owner's subscriptions (Walter Router plan/): list, change or cancel when he says so (2026-10-22)."""
    try:
        action = args.get("action") or "list"
        if action == "list":
            return json.dumps(await _cli("plans", "list"), ensure_ascii=False, default=str)
        cmd = ["plans", "retire" if action == "retire" else "set", str(args["plan_id"]),
               "--why", str(args.get("why") or "dit par le propriétaire dans la conversation")]
        for key, flag in (("vendor", "--vendor"), ("plan", "--plan"), ("price_usd_month", "--price"), ("note", "--note"),
                          ("since", "--since"), ("until", "--until")):
            if action == "set" and args.get(key) not in (None, ""):
                cmd += [flag, str(args[key])]
        if action == "set" and args.get("models"):
            cmd += ["--models", ",".join(str(m) for m in args["models"])]
        return json.dumps(await _cli(*cmd), ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_plans: {exc}"}, ensure_ascii=False)


async def _handle_generate(args: Mapping[str, Any], **_: Any) -> str:
    try:
        cmd = ["generate", str(args.get("request") or "")]
        for key, flag in (("task", "--task"), ("role", "--role"), ("aspect_ratio", "--aspect-ratio"),
                          ("duration", "--duration"), ("resolution", "--resolution")):
            if args.get(key):
                cmd += [flag, str(args[key])]
        for u in args.get("image_urls") or []:
            cmd += ["--image-url", str(u)]
        if args.get("paid_fallback"):
            cmd.append("--paid-fallback")
        return json.dumps(await _cli(*cmd, timeout=2700), ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"walter_generate: {exc}"}, ensure_ascii=False)


GENERATE_SCHEMA = {
    "name": "walter_generate",
    "description": (
        "Generate an image, a video, a music track or a voice-over on the model Walter Router picks (the owner's "
        "favourite for the objective), with the prompt rewritten for that model by the economic text tier and the "
        "model's workflow applied (e.g. Seedance premium: a reference still first). Provider order: Kie when "
        "available and not much dearer, OpenRouter otherwise. Returns local file paths (send them to the user with "
        "MEDIA:<path>), cost and the prompt used. A UI-only choice (Omni via Flow credits) comes back as manual "
        "unless paid_fallback=true. Pass the user's request verbatim."),
    "parameters": {"type": "object", "properties": {
        "request": {"type": "string", "description": "The user's request, verbatim."},
        "task": {"type": "string", "enum": [t for t in TASKS if t in (
            "text_to_image", "image_edit", "logo", "graphic_design", "text_to_video", "image_to_video",
            "video_edit", "music", "tts")]},
        "role": {"type": "string", "description": "Force a role (premium, action, ugc, budget, default)."},
        "image_urls": {"type": "array", "items": {"type": "string"}, "description": "Public URLs of input images."},
        "aspect_ratio": {"type": "string"}, "duration": {"type": "integer"}, "resolution": {"type": "string"},
        "paid_fallback": {"type": "boolean"}}, "required": ["request"]},
}


VERDICT_SCHEMA = {
    "name": "walter_verdict",
    "description": ("The owner's answer to a Walter Router Telegram message (« adopter 1 », « ignorer 2 », "
                    "« adopter 1 action »): adopting a new model pins it for the roles it beats (or only the named "
                    "role); adopting a text tier pins it; ignoring a new #1 keeps the previous model."),
    "parameters": {"type": "object", "properties": {
        "alert_id": {"type": "integer", "description": "The short number shown in the message (1, 2, 3…)."},
        "role": {"type": "string", "description": "Optional role named by the owner (premium, action, ugc, budget, "
                                                  "default, L1, L2, L3)."},
        "decision": {"type": "string", "enum": ["adopter", "ignorer"]},
        "note": {"type": "string"}}, "required": ["alert_id", "decision"]},
}

FEEDBACK_SCHEMA = {
    "name": "walter_feedback",
    "description": ("Record the owner's opinion of a model's result (e.g. « ce rendu est nul », « super ce modèle »): "
                    "rating -2..2, on the model of the last routed run unless he names one. It moves that model's "
                    "score for the task (+/-3 points per rating, capped) — benchmarks stay, his experience counts."),
    "parameters": {"type": "object", "properties": {
        "rating": {"type": "integer", "minimum": -2, "maximum": 2},
        "model": {"type": "string", "description": "model id; omit for the last routed run"},
        "task": {"type": "string", "enum": TASKS},
        "note": {"type": "string", "description": "His words, short."}}, "required": ["rating"]},
}


PLANS_SCHEMA = {
    "name": "walter_plans",
    "description": ("The owner's AI subscriptions as Walter Router knows them (ChatGPT Plus, Claude Pro, Google AI "
                    "Pro…): list them, or record a change he tells you about (new plan, price, end of an offer, models "
                    "included) or a cancellation. Plan ids are lowercase with dashes (openai-plus, google-ai-pro). "
                    "Only on his word: never invent a plan or a price."),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["list", "set", "retire"]},
        "plan_id": {"type": "string"}, "vendor": {"type": "string"}, "plan": {"type": "string"},
        "price_usd_month": {"type": "number"}, "models": {"type": "array", "items": {"type": "string"}},
        "since": {"type": "string", "description": "YYYY-MM-DD"}, "until": {"type": "string", "description": "YYYY-MM-DD"},
        "note": {"type": "string"}, "why": {"type": "string", "description": "His words, short."}},
        "required": ["action"]},
}


def _available() -> bool:
    # Hidden inside a walter_run child (no recursive routing) and when the router is not installed.
    # CLI is a command name since 2026-10-19: look it up on the PATH (os.access on a bare name checked the current
    # directory, so every walter-router tool was hidden from Hermes until 2026-10-22)
    import shutil
    return os.environ.get(CHILD_ENV) != "1" and bool(shutil.which(CLI) or os.access(CLI, os.X_OK))


ROUTING_RULE = (
    "Walter Router — choix des modèles (règle du propriétaire). Pour générer une image, une vidéo, une musique ou une "
    "voix, utilise walter_generate avec la demande de l'utilisateur mot pour mot (via tool_call si l'outil est différé) : "
    "il choisit le modèle favori selon l'objectif, rédige le prompt et renvoie les fichiers. Avant de confier un "
    "travail texte important (analyse longue, code, comparatif) à un sous-agent, utilise walter_route / walter_run. Ses favoris "
    "et rôles (premium, action, UGC, budget…) priment sur tout skill spécifique à un modèle ; un skill sert "
    "ensuite à exécuter le modèle choisi. Pour exécuter une sous-tâche texte sur le modèle choisi, utilise "
    "walter_run. Si l'utilisateur nomme lui-même un modèle, son choix prime. Quand il répond « adopter N » ou "
    "« ignorer N » à une alerte Walter Router, appelle walter_verdict ; quand il juge le résultat d'un modèle "
    "(« nul », « parfait »…), enregistre-le avec walter_feedback. Quand il parle d'un changement d'abonnement IA "
    "(nouveau forfait, prix, fin d'offre, résiliation), enregistre-le avec walter_plans."
)


def _home_chat() -> str | None:
    """The owner's Telegram chat (gateway home channel); only they may press the buttons."""
    m = re.search(r"^TELEGRAM_HOME_CHANNEL:\s*'?(-?\d+)'?\s*$",
                  (Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "config.yaml").read_text(), re.M)
    return m.group(1) if m else os.environ.get("TELEGRAM_HOME_CHANNEL")


def _wire_buttons(application: Any, adapter: Any) -> None:
    """Buttons of the Walter Router notification (callback data 'wr:<a|d>:<ref>[:<role>]', sent by the
    router's analysis/telegram.py): run `walter-router verdict`, then drop that row and append the outcome."""
    from telegram import InlineKeyboardMarkup
    from telegram.ext import CallbackQueryHandler

    async def _on_button(update: Any, context: Any) -> None:
        q = update.callback_query
        home = _home_chat()
        if not home or str(q.from_user.id) != home or str(q.message.chat.id) != home:
            await q.answer("Non autorisé.")
            return
        _, code, ref, *role = q.data.split(":", 3)
        cmd = ["verdict", ref, "adopted" if code == "a" else "dismissed"] + (["--role", role[0]] if role else [])
        try:
            await _cli(*cmd)
        except Exception as exc:  # noqa: BLE001
            await q.answer(f"Échec : {exc}"[:190], show_alert=True)
            return
        rows = q.message.reply_markup.inline_keyboard if q.message.reply_markup else []
        clicked = next((b.text for row in rows for b in row if b.callback_data == q.data), q.data)
        keep = [r for r in ([b for b in row if (b.callback_data or "").split(":")[2:3] != [ref]] for row in rows) if r]
        try:
            await q.edit_message_text(f"{q.message.text}\n\n→ {clicked}",
                                      reply_markup=InlineKeyboardMarkup(keep) if keep else None,
                                      disable_web_page_preview=True)
        except Exception as exc:  # noqa: BLE001 — the verdict is recorded even if the edit fails
            logger.warning("WALTER_ROUTER button edit failed: %s", exc)
        await q.answer(f"Enregistré : {clicked}"[:190])

    application.add_handler(CallbackQueryHandler(_on_button, pattern=r"^wr:[ad]:\d+"))


def register(ctx: Any) -> None:
    if callable(getattr(ctx, "register_system_prompt_section", None)) and os.environ.get(CHILD_ENV) != "1":
        try:
            ctx.register_system_prompt_section("walter-router.routing-rule", ROUTING_RULE)
        except Exception as exc:  # noqa: BLE001
            logger.error("WALTER_ROUTER_DEGRADED system_prompt_section: %s", exc)
    if callable(getattr(ctx, "register_telegram_handler", None)) and os.environ.get(CHILD_ENV) != "1":
        try:
            ctx.register_telegram_handler(_wire_buttons)
        except Exception as exc:  # noqa: BLE001
            logger.error("WALTER_ROUTER_DEGRADED telegram buttons: %s", exc)
    if not callable(getattr(ctx, "register_tool", None)):
        logger.error("WALTER_ROUTER_DEGRADED register_tool_missing")
        return
    for schema, handler, emoji in ((ROUTE_SCHEMA, _handle_route, "🧭"), (RUN_SCHEMA, _handle_run, "🚦"),
                                   (VERDICT_SCHEMA, _handle_verdict, "✅"), (FEEDBACK_SCHEMA, _handle_feedback, "⭐"), (PLANS_SCHEMA, _handle_plans, "💳"),
                                   (GENERATE_SCHEMA, _handle_generate, "🎨")):
        kwargs = {"name": schema["name"], "toolset": "walter-router", "schema": schema, "handler": handler,
                  "check_fn": _available, "is_async": True, "emoji": emoji}
        try:
            ctx.register_tool(**kwargs)
        except TypeError:
            for k in ("emoji", "is_async", "toolset"):
                kwargs.pop(k, None)
            try:
                ctx.register_tool(**kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.error("WALTER_ROUTER_DEGRADED register %s: %s", schema["name"], exc)
