"""Versioned public API descriptions, used by schema output and maintained reference docs.

Transport defaults and effective execution defaults are deliberately separate. This module
contains no provider keys, account details or model selections.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1


def p(kind, description, default=None, **extra):
    return {"type": kind, "description": description, "default": default, **extra}


RUN = {
    "request": p("string", "Demande originale. Obligatoire dans l'outil MCP ; le CLI accepte goal seul pour le texte."),
    "goal": p("string", "Instructions complètes de la sous-tâche texte ; obligatoire à l'exécution texte.", ""),
    "context": p("string", "Faits, contraintes, extraits et chemins nécessaires à l'exécuteur ; il ne voit pas le chat.", ""),
    "conversation": p("string", "Une ligne sur les échanges précédents pour classer une demande dépendante du contexte.", "",
                      **{"x-note": "MCP limite à 600 caractères pour route ; run transmet actuellement sans cette coupure."}),
    "task": p("string", "Clé de spécialité ; omise = classification par le modèle de décision.", ""),
    "level": p("string", "Niveau fonctionnel du texte général ; les spécialités ont leur classement propre.", "",
               enum=["", "L1", "L2", "L3"]),
    "model": p("string", "Seulement si l'utilisateur nomme le modèle ; identifiant, alias, nom ou modèle/variante.", ""),
    "provider": p("string", "Avec model, fournisseur expressément demandé : restriction stricte à ce fournisseur. claude-pro désigne le transport d’abonnement Claude du Router, contexte et outils du consommateur.", ""),
    "require": p("string", "Contrainte dure appliquée à la sélection et aux routes ; une seule par appel.", "",
                 enum=["", "unrestricted", "open_weights", "video_input"]),
    "toolsets": p(["array", "null"], "Groupes d'outils du texte. Par défaut les capacités Walter (walter-web = walter_browse, skills, memory) via le Tool Gateway ; terminal et fichiers seulement sur demande explicite.", None,
                  items={"type": "string"}, **{"x-effective-default": ["walter-web", "skills", "memory"],
                  "x-note": "MCP omet la liste vide ; elle ne désactive donc pas les outils via ce transport."}),
    "max_turns": p("integer", "Nombre maximal d'itérations du texte, appels modèle compris.", 0,
                   **{"x-effective-default": 40, "x-effective-range": [1, 120], "x-coercion": "0 devient 40 ; bornage 1..120"}),
    "budget_seconds": p("integer", "Budget total texte pour tous les fournisseurs et outils ; une part reste réservée aux fournisseurs suivants.", 0,
                        **{"x-effective-default": 900, "x-effective-range": [60, 3600], "x-coercion": "0 devient 900 ; bornage 60..3600"}),
    "role": p("string", "Objectif média, notamment vidéo ; le CLI run ne transmet pas ce champ à la décision texte.", ""),
    "image_urls": p(["array", "null"], "URLs de références pour la génération média ; HTTP(S) exigé par MCP. Pas d'attachement automatique au chat texte.", None,
                    items={"type": "string"}),
    "aspect_ratio": p("string", "Format de génération ; valeurs prises en charge selon le modèle et le fournisseur.", ""),
    "duration": p("integer", "Durée média demandée, en secondes ; dépend des capacités du modèle.", 0),
    "resolution": p("string", "Résolution média ; la valeur peut être normalisée selon les formats du modèle.", ""),
    "paid_fallback": p("boolean", "Autorise le passage d'un rôle prévu en interface manuelle à une génération payante ; exige la demande de l'utilisateur.", False),
}

ROUTE_KEYS = ("request", "task", "level", "model", "provider", "require", "conversation")
PLANS = {
    "action": p("string", "Lire, enregistrer une déclaration ou retirer un abonnement.", "list", enum=["list", "set", "retire"]),
    "plan_id": p("string", "Identifiant obligatoire pour set/retire.", ""),
    "vendor": p("string", "Éditeur déclaré par l'utilisateur.", ""),
    "plan": p("string", "Nom du forfait déclaré.", ""),
    "price_usd_month": p(["number", "null"], "Prix mensuel en USD, uniquement sur déclaration ou preuve validée.", None),
    "models": p(["array", "null"], "Identifiants des modèles inclus ; ne pas les inventer.", None, items={"type": "string"}),
    "since": p("string", "Date déclarée de début, YYYY-MM-DD.", ""),
    "until": p("string", "Fin déclarée d'une offre, YYYY-MM-DD.", ""),
    "note": p("string", "Précisions sur l'abonnement.", ""),
    "why": p("string", "Provenance ou raison de la déclaration, conservée dans l'historique.", ""),
}


def tools():
    definitions = {
        "walter_route": ("Examiner un choix et ses routes, sans exécuter la tâche. Pour le texte, provider reflète la première route exécutable ; après exécution, routed.provider indique le fournisseur réel.", {k: RUN[k] for k in ROUTE_KEYS}, []),
        "walter_run": ("Exécuter une sous-tâche texte ou une génération autorisée ; transmettre user_notice si requis.", RUN, ["request"]),
        "walter_decide": ("Décision courte, avec options explicites et contexte utile.", {
            "question": p("string", "Question de décision."),
            "options": p("object", "Nom court → sens de chaque option ; au moins deux options dans MCP.", minProperties=2,
                         additionalProperties={"type": "string"}),
            "context": p("string", "Données sur lesquelles décider.", "")}, ["question", "options"]),
        "walter_plans": ("Lire les abonnements, ou enregistrer une modification demandée par leur propriétaire.", PLANS, []),
    }
    return [{"name": name, "description": desc,
             "inputSchema": {"type": "object", "properties": deepcopy(properties), "required": required,
                             "additionalProperties": False}}
            for name, (desc, properties, required) in definitions.items()]


def schema():
    from walter_router.serve.run import ALLOWED_TOOLSETS
    definitions = tools()
    next(t for t in definitions if t["name"] == "walter_run")["inputSchema"]["properties"]["toolsets"]["items"]["enum"] = list(ALLOWED_TOOLSETS)
    route_request = next(t for t in definitions if t["name"] == "walter_route")["inputSchema"]["properties"]["request"]
    route_request["default"] = ""
    route_request["description"] = "Demande à classer ; fournir au moins request, task ou model. La sélection n'exécute pas la tâche."
    return {"schema_version": VERSION, "module": "router", "tools": definitions,
            "execution": {"text": "native", "fallback": "same-model providers only",
                          "notification": "relay user_notice whenever user_notification_required is true"}}
