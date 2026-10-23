---
name: walter-browse-orchestrator
description: Any web task uses walter_browse, the single web front door.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [web, browse, walter, orchestrator, search, extraction]
---

# Walter Browse — orchestrateur (comment DÉCIDER, pas comment faire)

W.Alter a UN seul accès au Web : **`walter_browse`**.

## When to Use

Charge cette skill dès que la tâche touche au Web : recherche d'information
actuelle, lecture d'URL, extraction de données, exploration de site,
navigation, interaction, session personnelle, comparaison de pages, ou
route réseau spécifique. Si la réponse peut venir du contexte/mémoire, pas de
skill nécessaire — walter_browse ne sert pas les questions sans Web.

## Frontière avec `computer_use`

- `walter_browse` est la porte d'entrée pour le Web : recherche, URL, contenu
de page, extraction, interaction web et session de site.
- `computer_use` est réservé à la surface native : lancer ou cibler une app,
Finder, barre d'adresse/browser chrome, dialogue OS, canvas ou toute action
explicitement demandée “sur mon Mac”.
- Un site ouvert dans une app native ne suffit pas à choisir `computer_use` : si
Monsieur veut seulement lire, rechercher, extraire ou interagir avec le contenu
de la page, utilisez `walter_browse` et son `session_id` si nécessaire.
- Ne chargez pas simultanément les deux chemins pour une tâche ordinaire. Le
backend Web reste interne à `walter_browse`; le backend GUI reste interne à
`computer_use`.

## Quand utiliser `walter_browse` (TOUJOURS, dès qu'il y a du Web)

- information actuelle / actualité factuelle → passe `query`
- recherche Web générale / trouver des sources ou URLs → `query`
- lire une page / résumer une URL → `url` + `objective`
- extraire des données structurées (prix, offres, listings) → `url` + `expected_fields`
- explorer un site, naviguer, interagir → `url` + `objective`
- comparer des pages → un appel `walter_browse` par page (ou un `query`)
- utiliser sa session perso / un compte → `session_id` (+ `url`)
- route réseau / géolocalisation demandée → `objective` le précise

## Ce que Walter Browse gère seul (ne pas dupliquer)

- recherche légère (search-lite, ~1s, pas de browser)
- lecture HTTP / contenu statique
- extraction structurée
- API/discovery/replay automatique
- capability réutilisables apprises
- escalade automatique vers browser furtif si nécessaire
- session, cookies, géo — si demandés

## Ce que le LLM fournit (le minimum)

- `query=` ou `url=` (+ `objective` en clair)
- `expected_fields`/`required_fields` si l'utilisateur veut des données précises
- `session_id` seulement si l'utilisateur parle de son compte/session
- la géo seulement si demandée

## Ce que le LLM NE DOIT JAMAIS faire

- NE PAS imposer : curl, Scrapling, Camoufox, Playwright, selectors, API replay.
  Le runtime choisit le chemin le plus rapide suffisant.
- NE PAS aller chercher un autre outil Web en premier. `walter_browse` EST
  la porte. Seul cas d'exception : debug explicitement demandé par
  l'utilisateur sur un backend précis.
- NE PAS créer de capability à la main — l'apprentissage est automatique.
- NE PAS passer des secrets (cookies, tokens) dans les arguments : la session
  se manipule via `session_id`.

## Contraintes réseau

- réseau `local` par défaut, TOUJOURS.
- VPN/proxy uniquement si l'utilisateur le demande explicitement (ex. « via
  un proxy FR ») — le router l'applique par session, ne touche jamais le
  réseau global.

## Style de sortie attendu

L'outil renvoie du JSON compact (results/records). Résume à l'utilisateur en
français, ne balance pas le JSON brut sauf si demandé.