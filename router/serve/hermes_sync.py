"""Hermes auxiliary jobs follow Walter Router (2026-10-16, the owner: every W.Alter module that uses AI goes through
the router's library).

Hermes holds its own Codex subscription session (single writer of its OAuth token), so its auxiliary jobs are not sent
through walter-llm: the router writes the poste's routes into config.yaml instead — first usable route as
provider/model/reasoning_effort, the next ones as auxiliary.<job>.fallback_chain — through `hermes config set`
(config backed up, gateway restarted gracefully only when something changed). Run at the end of every 48 h cycle and
after each verdict, so a model the owner adopts reaches Hermes; the core of Hermes is never patched.
2026-10-22: also the auxiliary jobs vision and curator (they were left on a model Codex no longer serves), and for
every OpenRouter model the router uses, its host order (cheapest usable host first) in Hermes' own
provider_routing.models.<id>.order — so Hermes' OpenRouter calls (fallbacks, auxiliary jobs, walter_run, delegated
agents) go to the same hosts as walter-llm's. Entries it writes carry _managed_by: walter-router.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance

HERMES = instance.hermes_bin()
HPY = instance.hermes_python()  # has PyYAML (this venv does not)
CONFIG = instance.hermes_home() / "config.yaml"
# Hermes homes whose auxiliary jobs follow the router: the main agent and the instance's profiles that set their own
# compression (host.json hermes_profiles_following_router); the other profiles inherit "auto" (their main model).
HOMES = [instance.hermes_home()] + [instance.hermes_home() / "profiles" / p
                                    for p in instance.host().get("hermes_profiles_following_router", [])]
BACKUPS = instance.hermes_home() / "backups" / "config"
# Hermes auxiliary job -> router poste
# (2026-10-22: vision and curator were left on gpt-5.6-luna, which Codex no longer serves with a ChatGPT login)
AUX_POSTES = {"compression": "summarization", "title_generation": "summarization", "vision": "vision",
              "curator": "summarization"}
MANAGED = "walter-router"   # marks the provider_routing.models entries this module writes (others are the owner's)
# Hermes cron agent jobs with their own model -> (router task, level): light background agent work = tier L1
CRON_JOBS = instance.hermes_home() / "cron" / "jobs.json"
CRON_POSTES = {k: tuple(v) for k, v in instance.host().get("cron_postes", {}).items()}   # job id -> (task, level)
MAX_FALLBACKS = 2


def _wanted(conn, poste: str, level: str | None = None) -> dict | None:
    from walter_router.cli import with_execution
    from walter_router.serve import choose
    d = with_execution(conn, choose.pick(conn, poste, level))
    routes = [r for r in d.get("execution") or [] if r.get("probe_ok") is not False and not r.get("unreliable")]
    if not routes:
        return None
    first, rest = routes[0], routes[1:1 + MAX_FALLBACKS]
    entry = lambda r: {"provider": r["hermes_provider"], "model": r["model"],  # noqa: E731
                       **({"reasoning_effort": r["reasoning"]} if r.get("reasoning") else {})}
    return {**entry(first), "fallback_chain": [entry(r) for r in rest], "_model_id": d.get("model_id"),
            "_variant": d.get("variant")}


def _aux(home: Path) -> dict:
    r = subprocess.run([str(HPY), "-c", "import json, sys, yaml; "
                        "print(json.dumps((yaml.safe_load(open(sys.argv[1])) or {}).get('auxiliary') or {}))",
                        str(home / "config.yaml")], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(r.stdout)


def plan(conn) -> list[dict]:
    out = []
    wanted = {poste: _wanted(conn, poste) for poste in set(AUX_POSTES.values())}
    for home in HOMES:
        if (home / "config.yaml").exists():
            out += _plan_home(home, _aux(home), wanted)
    return out + _plan_crons(conn) + _plan_routing(conn)


def _plan_home(home: Path, aux: dict, wanted: dict) -> list[dict]:
    out = []
    for job, poste in AUX_POSTES.items():
        want = wanted[poste]
        if not want:
            out.append({"home": str(home), "job": job, "poste": poste, "error": "no usable route"})
            continue
        cur = aux.get(job) or {}
        changes = {k: v for k, v in want.items() if not k.startswith("_") and cur.get(k) != v}
        if cur.get("base_url") or cur.get("api_key"):   # an old direct endpoint would override the provider
            changes.update({"base_url": "", "api_key": ""})
        out.append({"home": str(home), "job": job, "poste": poste, "model_id": want["_model_id"],
                    "variant": want["_variant"],
                    "current": {k: cur.get(k) for k in ("provider", "model", "reasoning_effort")}, "changes": changes})
    return out


def host_orders(conn) -> dict[str, list[str]]:
    """OpenRouter model id -> the router's host order (cheapest usable host first) for every OpenRouter route of
    every chat task: Hermes applies it through provider_routing.models.<id>.order (its own config, no core patch)."""
    from walter_router.cli import with_execution
    from walter_router.serve import choose
    out: dict[str, list[str]] = {}
    tasks = [r["task"] for r in conn.execute("select task from models.tasks where interface = 'chat'")]
    for task in tasks:
        for level in (["L1", "L2", "L3"] if task == "general" else [None]):
            try:
                d = with_execution(conn, choose.pick(conn, task, level))
            except Exception:  # noqa: BLE001 — one task must not stop the others
                continue
            for r in d.get("execution") or []:
                if r.get("hermes_provider") == "openrouter" and (r.get("or_provider") or {}).get("order"):
                    out.setdefault(r["model"], r["or_provider"]["order"])
    return out


def _routing(home: Path) -> dict:
    r = subprocess.run([str(HPY), "-c", "import json, sys, yaml; "
                        "print(json.dumps(((yaml.safe_load(open(sys.argv[1])) or {}).get('provider_routing') or {})"
                        ".get('models') or {}))", str(home / "config.yaml")], capture_output=True, text=True, timeout=30,
                       check=True)
    return json.loads(r.stdout)


def _plan_routing(conn) -> list[dict]:
    want = host_orders(conn)
    out = []
    for home in HOMES:
        if not (home / "config.yaml").exists():
            continue
        cur = _routing(home)
        changes = {m: {"order": o, "_managed_by": MANAGED} for m, o in want.items()
                   if (cur.get(m) or {}).get("order") != o and (not cur.get(m) or cur[m].get("_managed_by") == MANAGED)}
        gone = [m for m, e in cur.items() if isinstance(e, dict) and e.get("_managed_by") == MANAGED and m not in want]
        if changes or gone:
            out.append({"home": str(home), "routing": True, "changes": {"set": changes, "remove": gone}})
    return out


def _plan_crons(conn) -> list[dict]:
    out = []
    jobs = json.loads(CRON_JOBS.read_text()) if CRON_JOBS.exists() else {}
    jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    by_id = {j.get("id"): j for j in (jobs if isinstance(jobs, list) else jobs.values())}
    for job_id, (task, level) in CRON_POSTES.items():
        j, want = by_id.get(job_id), _wanted(conn, task, level)
        if not j or not want:
            continue
        cur = {"provider": j.get("provider"), "model": j.get("model"), "reasoning_effort": j.get("reasoning_effort")}
        changes = {k: want[k] for k in ("provider", "model", "reasoning_effort") if want.get(k) and cur.get(k) != want[k]}
        out.append({"cron": job_id, "name": j.get("name"), "poste": f"{task}/{level}", "model_id": want["_model_id"],
                    "current": cur, "changes": changes})
    return out


def apply(conn, restart: bool = True) -> dict:
    steps = plan(conn)
    todo = [s for s in steps if s.get("changes")]
    if not todo:
        return {"changed": False, "jobs": steps}
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"config.yaml.{ts}.pre-router-sync"
    shutil.copy2(CONFIG, backup)
    for s in [x for x in todo if x.get("cron")]:
        c = s["changes"]
        args = [str(HERMES), "cron", "edit", s["cron"], "--pin"]
        args += ["--model", c["model"]] if "model" in c else []
        args += ["--provider", c["provider"]] if "provider" in c else []
        args += ["--reasoning-effort", c["reasoning_effort"]] if "reasoning_effort" in c else []
        subprocess.run(args, check=True, capture_output=True, timeout=60)
    for s in [x for x in todo if x.get("routing")]:   # Hermes' own config API (comment-preserving save), no core patch
        code = ("import json, sys; from hermes_cli.config import load_config, save_config; "
                "ch = json.loads(sys.argv[1]); cfg = load_config(); "
                "m = cfg.setdefault('provider_routing', {}).setdefault('models', {}); "
                "[m.pop(k, None) for k in ch['remove']]; m.update(ch['set']); save_config(cfg, merge_existing=True)")
        if s["home"] != str(instance.hermes_home()):
            shutil.copy2(Path(s["home"]) / "config.yaml", Path(s["home"]) / f"config.yaml.{ts}.pre-router-sync")
        subprocess.run([str(HPY), "-c", code, json.dumps(s["changes"])], check=True, capture_output=True, timeout=60,
                       cwd=str(instance.hermes_home() / "hermes-agent"), env={**__import__("os").environ, "HERMES_HOME": s["home"]})
    todo = [x for x in todo if not x.get("cron") and not x.get("routing")]
    import os
    for s in todo:
        env = {**os.environ, "HERMES_HOME": s["home"]}
        if s["home"] != str(instance.hermes_home()):
            shutil.copy2(Path(s["home"]) / "config.yaml", Path(s["home"]) / f"config.yaml.{ts}.pre-router-sync")
        for key, value in s["changes"].items():
            v = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
            subprocess.run([str(HERMES), "config", "set", "--force", f"auxiliary.{s['job']}.{key}", v],
                           check=True, capture_output=True, timeout=60, env=env)
    restarted = False
    if restart and (todo or any(x.get("routing") for x in steps if x.get("changes"))):   # graceful: running turns finish first (cron edits need no restart)
        subprocess.run([str(HERMES), "gateway", "restart"], capture_output=True, timeout=1900)
        restarted = True
    return {"changed": True, "backup": str(backup), "restarted": restarted, "jobs": steps}
