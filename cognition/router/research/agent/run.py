"""Step 2 of the 48 h cycle: the research agent, run by Walter Engine (2026-11-13; before, a Hermes loop with shell,
file and web tools started by the cycle script — the last agent loop outside the engine).

The Router gathers what the agent reads (cycle digest, health, existing name links) and puts it in the prompt. The
agent is one unattended engine delegation (`oneshot.delegate`, Engine API `delegate`, `api` preset: read and browse,
no shell, no file write, no message): it checks names on the web and answers in JSON. The Router applies each
"same model" link itself through `aliases_admin.add`, which refuses absurd links, and writes the report. Nothing
else is changed; a failed or unparsable answer leaves the cycle going (report says so)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance, paths

SOURCE = "walter-router-analysis"
TIMEOUT_S = 1100


def prompt(data: dict) -> str:
    text = paths.AGENT_PROMPT.read_text()
    text = text.replace("{{owner.address}}", instance.owner()).replace("{{router_root}}", str(paths.ROOT))
    return text + "\n## Données du cycle (JSON)\n" + json.dumps(data, ensure_ascii=False, default=str) + "\n"


def parse(text: str | None) -> dict | None:
    """The agent's JSON object {aliases, report} (tolerates a code fence or text around it); None if absent."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(out, dict) or not isinstance(out.get("report"), str):
        return None
    out["aliases"] = [a for a in out.get("aliases") or [] if isinstance(a, dict)
                      and all(isinstance(a.get(k), str) and a.get(k) for k in ("key", "model_id", "reason"))]
    return out


def apply(conn, aliases: list[dict], add) -> tuple[list[dict], list[dict]]:
    added, refused = [], []
    for a in aliases:
        try:
            added.append({**add(conn, a["key"], a["model_id"], a["reason"], "agent"), "reason": a["reason"]})
        except ValueError as e:
            refused.append({"key": a["key"], "model_id": a["model_id"], "why": str(e)})
    return added, refused


def report_text(day: str, answer: dict | None, added: list[dict], refused: list[dict], raw: str | None) -> str:
    head = f"# Walter Router — analyse du cycle, {day} UTC (agent Walter Engine)\n\n"
    if answer is None:
        why = "pas de réponse du moteur" if raw is None else "réponse sans l'objet JSON attendu"
        return head + f"Analyse non faite : {why}. Rien n'a été appliqué ; le cycle continue.\n"
    lines = [head + answer["report"].strip(), "", "## Liens de noms appliqués par le Router"]
    lines += [f"- {a['added']} → {a['model_id']} ({a['reason']})" for a in added] or ["- aucun"]
    if refused:
        lines += ["", "## Liens proposés et refusés par la validation"]
        lines += [f"- {r['key']} → {r['model_id']} : {r['why']}" for r in refused]
    return "\n".join(lines) + "\n"


def run(conn, *, delegate=None, gather=None, add=None, log_dir: Path | None = None, now: datetime | None = None) -> dict:
    from walter_router.analysis import aliases_admin
    from walter_router.serve import oneshot
    delegate = delegate or oneshot.delegate
    add = add or aliases_admin.add
    if gather is None:
        from walter_router.health import health
        from walter_router.research.agent import review

        def gather(c):
            return {"review": review.digest(c), "health": health(), "aliases": aliases_admin.listing()}
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    log_dir = log_dir or instance.host_path("log_dir")
    raw = delegate(prompt(gather(conn)), SOURCE, timeout=TIMEOUT_S)
    answer = parse(raw)
    added, refused = apply(conn, answer["aliases"], add) if answer else ([], [])
    path = Path(log_dir) / f"analysis-{day}.md"
    path.write_text(report_text(day, answer, added, refused, raw))
    return {"ok": answer is not None, "runtime": "walter-engine", "report": str(path),
            "added": [a["added"] for a in added], "refused": len(refused),
            "error": None if answer else ("no_answer" if raw is None else "unparsable_answer")}
