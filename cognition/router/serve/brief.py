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

from walter_router import instance
from walter_router.serve.choose import REQUIREMENTS

MAX_CHARS = 4000
ANALYSIS = ("vision", "document", "long_context")   # chat tasks that read what they are given
LEVELS_FR = {"L1": "quotidien : réponse courte, résumé simple, fait rapide, petite reformulation",
             "L2": "plus dur : analyse en plusieurs étapes, comparaison, rédaction soignée, planification",
             "L3": "le plus dur ou à fort enjeu : recherche approfondie, raisonnement complexe, décision importante"}
CONSTRAINTS_FR = {"unrestricted": "contenu que les modèles grand public refusent",
                  "open_weights": "modèle à poids ouverts",
                  "video_input": "le modèle lit une vidéo (avec task=vision : analyser ou revoir une vidéo)"}
GENERATION = (("Images", ("image",)), ("Vidéo", ("video",)), ("Audio", ("audio", "music")))


def _short(text: str | None) -> str:
    """First sentence of a role description, without where it runs (« Via Flow… »: the router's business)."""
    first = re.split(r"(?<=[.!?])\s", (text or "").strip())[0]
    return first.split(" : ")[0].rstrip(".")


def _tasks(rows: list[dict], interfaces: tuple[str, ...], only: tuple[str, ...] = (), skip: tuple[str, ...] = ()) -> str:
    return " · ".join(f'`{r["task"]}` {r["label"]}' for r in rows if r["interface"] in interfaces
                      and (not only or r["task"] in only) and r["task"] not in skip)


def text(conn) -> str:
    owner = instance.owner()
    rows = list(conn.execute("""select task, label, interface from models.tasks
                                where not internal and interface <> 'tool' order by interface, task"""))
    roles = list(conn.execute("""select distinct on (role) role, label, description from models.preferences
                                 where task in ('text_to_video', 'image_to_video') order by role, priority"""))
    order = {"default": 0, "premium": 1, "action": 2, "ugc": 3, "budget": 4}
    roles.sort(key=lambda r: order.get(r["role"], 9))
    out = [
        "## Walter Router — quel modèle pour quel travail",
        "Walter Router sait quel modèle fait le mieux chaque travail et comment l'exécuter au moins cher (un abonnement "
        "d'abord, à son prix de revient) : benchmarks, prix et fournisseurs sont déjà comparés. Toi, orchestrateur, tu "
        "découpes le travail et tu choisis pour chaque morceau la spécialité (`task`) et le niveau (`level`) ; le "
        "router met le bon modèle derrière. Si " + owner + " nomme un modèle (et un fournisseur), passe-les "
        "(`model`, `provider`) : il est exécuté tel quel, ou la réponse dit pourquoi c'est impossible — jamais de "
        "substitut. Un changement de modèle par défaut lui est proposé, jamais fait d'office.",
        "",
        "Outils (mêmes noms dans chaque runtime) :",
        "- `walter_run` : fait le travail. Texte : un sous-agent avec outils sur le modèle choisi ; `goal` = des "
        "consignes complètes et `context` = ce qu'il doit savoir (il ne voit pas la conversation). Image, vidéo, "
        "musique, voix : la génération, prompt réécrit pour le modèle (coûte de l'argent : seulement à la demande "
        "de " + owner + ").",
        "- `walter_route` : le même choix sans rien exécuter (modèle, routes et prix), pour vérifier ou planifier. "
        "Sans `task`, le modèle de décision classe la demande ; `conversation` = une ligne sur ce qui précède quand "
        "la demande en dépend.",
        "- `walter_decide` : le modèle de décision pour tes propres choix rapides (trier, oui/non, une option parmi "
        "plusieurs, en masse) : une fraction de seconde, une fraction de centime.",
        f"- `walter_plans` : les abonnements IA de {owner} (lire ; enregistrer un changement qu'il annonce).",
        "",
        "Niveaux de réflexion (`level`, pour le texte général : `task` = `general` ou sans `task`) :",
        *[f"- {k} {v}" for k, v in LEVELS_FR.items()],
        "",
        "Spécialités texte (`task`) : " + _tasks(rows, ("chat",), skip=ANALYSIS + ("general",)),
        "Analyse : " + _tasks(rows, ("chat",), only=ANALYSIS),
    ]
    for title, interfaces in GENERATION:
        line = _tasks(rows, interfaces)
        if line:
            out.append(f"Génération — {title.lower()} : {line}")
    if roles:
        out.append("Objectif vidéo (`role`) : " + " · ".join(f'`{r["role"]}` {_short(r["description"]) or r["label"]}'
                                                            for r in roles))
    out.append("Contraintes (`require`) : " + " · ".join(f"`{k}` {CONSTRAINTS_FR.get(k, k)}" for k in REQUIREMENTS))
    out.append("Le router sert aussi les modules (transcription, embeddings, rerank, tri des messages) : rien à "
               "faire de ton côté.")
    body = "\n".join(out)
    if len(body) > MAX_CHARS:
        raise ValueError(f"brief too long for a system-prompt section ({len(body)} > {MAX_CHARS} characters)")
    return body


def write(conn) -> bool:
    """Write the brief to the instance's public file when it changed (read by profiles of Codex / DSH)."""
    path = instance.state_file("brief.md")
    new = text(conn) + "\n"
    if path.exists() and path.read_text() == new:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)
    return True
