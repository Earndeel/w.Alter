# Walter Computer — guide détaillé

## Objectif

Observer et manipuler un appareil de {{owner.address}} (son Mac) par actions atomiques sûres, pour les tâches qui
n'existent que dans une application native. L'agent garde le but, le plan et les décisions ; le module choisit
la cible, applique la politique de présence et d'interruption, vérifie les captures et reprend proprement.

## Comment l'utiliser

`computer_use(session_id, action, arguments)` avec une action atomique :
`list_apps`, `list_windows`, `device_context`, `capture`, `click`, `type`, `key`, `scroll`, `drag`, `set_value`,
`focus_app`, `launch_app`, `open_url`, `click_visual_ref`, `targeted_verify`, `wait`, `close`.

1. Capturer l'application exacte avant toute saisie.
2. Vérifier l'effet (`targeted_verify` ou nouvelle capture) après chaque action qui compte.
3. `close` à la fin de la tâche.

## Organisation

| Partie | Rôle |
|---|---|
| `walter_computer.policy`, `runtime`, `observer`, `types` | Noyau indépendant : politique, garde des références visuelles, observations |
| `operator`, `driver`, `transport` | Sessions (16 max, expirées après 15 min), port CuaDriver ; un verrou par appareil |
| Nœud d'appareil (`~/walter-computer-use`) | Transport SSH vers l'appareil enrôlé |
| `ports/hermes` | Adaptateur Hermes : approbations, baux, distribution |
| Configuration | `config/config.json` (aucun appareil) ; l'appareil réel est déclaré dans l'instance |

## Interfaces

| Besoin | MCP | Hermes | Python |
|---|---|---|---|
| Actions atomiques | `computer_use` (client stdio local seulement) | outil computer-use étendu | `OperatorSessions.call` |

## Règles et limites

- Les autorisations viennent de la politique serveur (`computer-policy.json`) ; un argument ne peut pas en accorder.
- Approbations de l'hôte et autorisation de la tâche par {{owner.address}} s'appliquent aux saisies et aux pixels.
- `device_busy` si un autre appel tient l'appareil ; la vision exige un capteur configuré.
- Pas disponible pour un client MCP distant (HTTP).
