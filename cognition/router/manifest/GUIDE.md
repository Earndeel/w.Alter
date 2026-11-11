# Walter Router — guide détaillé

## Objectif

Choisir, pour chaque tâche, le modèle et le fournisseur qui conviennent (benchmarks, prix, abonnements de
{{owner.address}}, ses préférences), et l'exécuter quand on le lui demande. L'agent reste l'orchestrateur : il définit le
travail, les données autorisées, vérifie le résultat. Son propre modèle ne change pas quand il appelle le routeur.
Aucun module de W.Alter n'écrit un nom de modèle en dur : il demande un poste au routeur.

## Comment l'utiliser

La note d'usage du routeur est dans la couche stable du prompt (`walter-router brief`). En résumé :

| Outil | Usage |
|---|---|
| `walter_run` | Faire une sous-tâche texte (sous-agent avec outils) ou une génération média demandée par {{owner.address}} |
| `walter_route` | Examiner un choix, ses routes et ses prix sans rien exécuter |
| `walter_decide` | Choix court ou répété parmi des options nommées |
| `audio_transcribe` | Transcrire des fichiers audio de la VM (notes vocales Beeper/WhatsApp/Telegram) par le poste `stt` ; jamais une clé de fournisseur sous `walter-secret exec` (sa sortie est jetée) |
| `walter_plans` | Lire les abonnements ; enregistrer un changement que {{owner.address}} annonce |
| `walter_web` | Converser avec un service web de chat activé par {{owner.address}} : message, fichiers joints, modèle facultatif ; réponse verbatim, fichiers produits en chemins |

L'index (`module_index('router')`) liste les tâches disponibles (clé, libellé, interface). Guide complet :
`docs/USAGE.md` ; parcours de la documentation : `docs/README.md`.

## Organisation

| Partie | Rôle |
|---|---|
| `research/`, `analysis/` | Classements (AA, Arena, Design Arena, BridgeBench, MTEB…) et prix (OpenRouter, Kie, Codex…) → PG schéma `models` |
| `plan/` | Abonnements de {{owner.address}} au coût réel du token |
| `serve/` | Choix par tâche, exécution (`run`, médias), décision, note d'usage |
| `interface/` | Page publique de la bibliothèque de modèles (domaine de l’instance), propositions Telegram |
| `llm/` (walter-llm, :8894) | Passerelle OpenAI-compatible pour les modules : `model` = un poste du routeur |
| `walter-router-refresh.timer` | Cycle de 48 h ; propositions avec boutons, jamais de bascule automatique |
| `guardian/` (`walter-router-guardian.timer`) | Maintenance autonome du module toutes les 6 h et après chaque cycle : détecte, répare ce qui est interne par le niveau L2 sur une copie, contrôles déterministes avant mise en place ; Telegram seulement si utile |

## Interfaces

| Besoin | MCP / Hermes | CLI |
|---|---|---|
| Exécuter / examiner / décider | `walter_run`, `walter_route`, `walter_decide` | `walter-router run|route|decide` |
| Abonnements | `walter_plans` | `walter-router plans` |
| Service web de chat | `walter_web` | `walter-router web` |
| Tâches | `module_index('router')` | `walter-router tasks` |
| Santé | `walter_health` | `walter-router health` |
| Maintenance | — | `walter-router-guardian status` |

## Règles et limites

- Si {{owner.address}} nomme un modèle, le transmettre (`model`, `provider`) ; aucun substitut.
- Génération média payante : uniquement à sa demande.
- Jamais de secret ni de donnée `local_only` vers un modèle cloud.
- Les favoris ne changent que sur décision de {{owner.address}}.
