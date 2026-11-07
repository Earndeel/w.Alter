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


def text(conn, owner: str | None = None) -> str:
    """Compact operational guidance, independent of current model names, prices and provider choices."""
    owner = owner or instance.owner()
    rows = list(conn.execute("""select task, label, interface from models.tasks
                                where not internal and interface <> 'tool' order by interface, task"""))
    roles = list(conn.execute("""select distinct on (role) role, label, description from models.preferences
                                 where task in ('text_to_video', 'image_to_video') order by role, priority"""))
    roles.sort(key=lambda r: {"default": 0, "premium": 1, "action": 2, "ugc": 3, "budget": 4}.get(r["role"], 9))
    keys = lambda interfaces, only=(), skip=(): " · ".join(
        f"`{r['task']}`" for r in rows if r["interface"] in interfaces
        and (not only or r["task"] in only) and r["task"] not in skip)
    out = [
        "## Walter Router — choisir et exécuter un modèle pour une sous-tâche",
        "Tu définis le travail, ses contraintes et le contexte ; le routeur choisit modèle et fournisseur selon les "
        "benchmarks, les coûts, les abonnements et les préférences de " + owner + ". Tu contrôles le résultat et l’intègres.",
        "Utilise-le lorsqu’une spécialité ou une sous-tâche distincte justifie le coût et la latence du transfert. "
        "Les faits et contraintes indispensables doivent accompagner chaque appel.",
        "- `walter_run` exécute. Donne `request`, `task`, `goal` complet pour le texte, `context` utile. "
        "L’exécuteur ne voit pas cette conversation. Appelle-le directement si le besoin est clair.",
        "- `walter_route` examine le choix, les routes et les prix sans exécuter ; utile pour vérifier ou planifier, "
        "pas un préalable obligatoire à `walter_run`. Sans `task`, le routeur classe la demande ; "
        "`conversation` explique un lien avec les échanges précédents.",
        "- `walter_decide` traite un choix court ou répété : `question`, `options` (au moins deux noms → sens), "
        "`context`. Pour une analyse longue, utilise une tâche texte.",
        "- `walter_plans` lit les abonnements ; une modification doit être demandée par leur propriétaire.",
        "`task=general` : L1 quotidien, résumé simple ; L2 analyse en plusieurs étapes ou rédaction soignée ; "
        "L3 raisonnement complexe ou fort enjeu. Les spécialités ont leur propre classement ; ne leur impose pas un niveau général.",
        "Texte : " + keys(("chat",), skip=ANALYSIS + ("general",)),
        "Analyse : " + keys(("chat",), only=ANALYSIS),
    ]
    for title, interfaces in GENERATION:
        line = keys(interfaces)
        if line:
            out.append(title + " : " + line)
    if roles:
        out.append("Objectif vidéo `role` : " + " · ".join(f"`{r['role']}`" for r in roles))
    out += [
        "Contraintes `require` : `open_weights` poids ouverts ; `unrestricted` politique de contenu compatible ; "
        "`video_input` route capable de lire une vidéo (`task=vision`). Fournis les sources ; la sélection seule n’attache aucun média.",
        "Si l’utilisateur nomme un modèle, transmets `model` (éventuellement /variante) et `provider` s’il l’impose ; "
        "aucun substitut. Les favoris ne changent pas sans sa décision.",
        "Pour le texte, limite `toolsets`, `max_turns`, `budget_seconds` au besoin. Outils natifs : terminal/code et fichiers ; "
        "autres capacités via leurs commandes si terminal autorisé. Les outils agissent sur l’hôte du routeur, "
        "avec ses droits ; les permissions d’un harness distant ne sont pas héritées automatiquement.",
        "Ne transmets pas de secrets ou de données local_only à un modèle cloud ; le harness contrôle les classes d’accès.",
        "Génération média payante : uniquement sur demande de l’utilisateur ; `image_urls`, `role`, "
        "`aspect_ratio`, `duration`, `resolution` selon le média. `paid_fallback` autorise une voie payante prévue manuelle.",
        "Texte : fournisseur en échec → fournisseur suivant du même modèle, historique conservé. "
        "Tous échouent → échec explicite. Une restriction de fournisseur nommé reste stricte.",
        "Lis `ok`, `routed`, `attempts`, `tools` et les erreurs. Si `user_notification_required`, "
        "transmets `user_notice` à l’utilisateur, même en cas d’échec. N’annonce jamais un succès sur la seule sélection.",
        "Exemple texte : {\"request\":\"Corriger ce bug\",\"task\":\"coding\",\"goal\":\"…\",\"context\":\"…\"}. "
        "Transcription, embeddings, rerank et postes internes sont servis aux modules ; ne les propose pas comme tâches usuelles.",
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
