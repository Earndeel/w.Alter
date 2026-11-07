# Walter Browse — guide détaillé

## Objectif

Obtenir des données du web le plus vite et le plus fiablement possible, et agir sur un site connecté comme
{{owner.address}} quand c'est nécessaire. Le moteur choisit sa profondeur (requête directe, HTML statique, Scrapling,
Camoufox, Webtop) selon la demande et le site ; l'agent décrit ce qu'il veut, pas comment l'obtenir.

## Comment l'utiliser

1. **Chercher / lire / extraire** : `walter_browse(query=… | url=…)`. Lecture d'une page : `content_only=true`.
   Extraction structurée : `objective`, `expected_fields`, `required_fields`, `min_records`.
2. **Agir connecté comme {{owner.address}}** : `browser_session(site, session)` ouvre ou rafraîchit une session Camoufox
   avec ses cookies, injectés côté serveur (seules des métadonnées reviennent) ; `browser_sites` liste les sites.
   Piloter ensuite avec `walter-browser -s <session> new|nav|snap|click|clickxy|ktype|shot|eval|upload|fetch|close`.
   Si le site a besoin de Chromium : `browser_session(..., engine="chromium")` / `walter-browser -e chromium …` au
   premier appel de la session (CloakBrowser, même API, mêmes règles) ; la session garde ensuite son moteur.
3. Rappeler `browser_session` dès que le site affiche une page de connexion.

## Organisation

| Partie | Rôle |
|---|---|
| `walter_browse/` (façade), `runtime/universal_router.py` | Moteur commun : choix du chemin, contrat sémantique d'extraction identique sur tous les chemins |
| `runtime/profile_index.py`, `result_cache.py` | Profils appris par domaine, cache de résultats ; état dans l'instance (`state/browse`) |
| Camoufox `:9377` (écran X `:101`) | Navigateur persistant de W.Alter ; {{owner.address}} le voit et le pilote via Selkies (Tailscale :3011) |
| Chromium `:9378` (CloakBrowser, même écran) | Second moteur, à la demande d'un site qui exige Chromium ; même API et mêmes règles |
| Sortie réseau `walter-exit-default` | Par défaut : la machine de {{owner.address}} tant que son VPN France est connecté, sinon la sortie WireGuard France, automatiquement ; `network/wg-exit` pour d'autres sorties |
| `ports/hermes` | Adaptateur Hermes (outil `walter_browse`) |

## Interfaces

| Besoin | MCP | Hermes | CLI |
|---|---|---|---|
| Recherche / extraction | `walter_browse` | `walter_browse` | — |
| Session connectée | `browser_session`, `browser_sites` | navigateur Hermes | `walter-browser login SITE` |
| Pilotage | — | — | `walter-browser -s <session> …` |

## Règles et limites

- Ne jamais extraire de cookies soi-même ; un nouveau site se déclare dans `browser_sites.json` (sans secret).
- Les cookies de {{owner.address}} ne sont acceptés que par une session qui sort par sa sortie réseau.
- Frappe humaine (vraies touches), jamais de remplissage programmatique ; empreinte d'appareil figée.
- Si aucune sortie France n'est disponible, les connexions sont refusées (jamais l'IP du serveur).
