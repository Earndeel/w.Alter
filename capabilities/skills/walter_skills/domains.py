"""Tier 0 — the domain map: one stable line per domain of the library, so the agent always knows what exists even when
the per-message cards do not show it. Deterministic (no LLM), rebuilt nightly, shown once per session (cache-friendly).
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import registry, store

HEADER = ("Bibliothèque de skills W.Alter (procédures testées sur cette VM) — domaines et skills les plus utilisés. "
          "Cherche avec {search} si la tâche relève d'un domaine sans fiche proposée :")


def build(top: int = 5) -> list[dict]:
    usage = Counter()
    with registry.db() as c:
        for r in c.execute("""select name, count(*) n from skills.reads where at > now() - interval '90 days'
                              group by 1"""):
            usage[r["name"]] += r["n"]
    prior = {}
    row = registry.ranker()
    if row:
        from .ranker import Ranker
        prior = Ranker.loads(bytes(row["blob"])).prior
    groups: dict[str, list[str]] = defaultdict(list)
    for s in store.iter_skills():
        groups[(s.domain or "misc").split("/")[0]].append(s.name)
    out = []
    for d, names in sorted(groups.items(), key=lambda x: -len(x[1])):
        names.sort(key=lambda n: -(usage[n] * 10 + prior.get(n, 0)))
        out.append({"domain": d, "count": len(names), "top": names[:top]})
    registry.set_state("domain_map", out)
    return out


def render(search_tool: str) -> str:
    m = registry.get_state("domain_map") or build()
    lines = [f"- {x['domain']} ({x['count']}) : {', '.join(x['top'])}" for x in m]
    return HEADER.format(search=search_tool) + "\n" + "\n".join(lines)
