"""Name links and the cycle report, for the Router's single agent (analysis/advisor.py).

History: 2026-11-13 the cycle's research agent became one Walter Engine delegation (before, a Hermes loop); 2026-11-20
(owner) it was merged into the advisor, so the Router has one agent that both checks the cycle (sources, providers,
names) and works out the consequences for the owner. What stays here is mechanical: the agent's "same model" links go
through `aliases_admin.add`, which refuses absurd links, and the report is written for the Router's log. Nothing else
is changed; a failed or unparsable answer leaves the cycle going (the report says so)."""
from __future__ import annotations


def apply(conn, aliases: list[dict], add) -> tuple[list[dict], list[dict]]:
    added, refused = [], []
    for a in aliases:
        try:
            added.append({**add(conn, a["key"], a["model_id"], a["reason"], "agent"), "reason": a["reason"]})
        except ValueError as e:
            refused.append({"key": a["key"], "model_id": a["model_id"], "why": str(e)})
    return added, refused


def report_text(day: str, answer: dict | None, added: list[dict], refused: list[dict], raw: str | None) -> str:
    head = f"# Walter Router — analyse du cycle, {day} UTC (agent du Router, Walter Engine)\n\n"
    if answer is None:
        why = "pas de réponse du moteur" if raw is None else "réponse sans l'objet JSON attendu"
        return head + f"Analyse non faite : {why}. Rien n'a été appliqué ; le cycle continue.\n"
    lines = [head + answer["report"].strip(), "", "## Liens de noms appliqués par le Router"]
    lines += [f"- {a['added']} → {a['model_id']} ({a['reason']})" for a in added] or ["- aucun"]
    if refused:
        lines += ["", "## Liens proposés et refusés par la validation"]
        lines += [f"- {r['key']} → {r['model_id']} : {r['why']}" for r in refused]
    return "\n".join(lines) + "\n"
