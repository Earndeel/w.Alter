---
name: walter-browse-orchestrator
description: "Map of W.Alter's web procedures: which walter_browse parameters for which need, the boundary with computer_use, signed-in sessions as Monsieur, and which web skill to open for a blocked page, a crawl or a login. A plain search or page read needs only walter_browse's own contract, not this skill."
version: 1.1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [web, browse, walter, orchestrator, search, extraction]
---

# Walter Browse — orchestrateur (comment DÉCIDER, pas comment faire)

W.Alter a UN seul accès au Web : **`walter_browse`**. Son contrat (description et paramètres) suffit pour une
recherche ou la lecture d'une page : ouvrir cette skill sert quand la tâche va au-delà (session connectée, page
bloquée, extraction en masse, frontière avec le Mac).

## Paramètres selon le besoin

- information actuelle, trouver des sources ou des URL → `query`
- lire / résumer une URL → `url` + `objective` (`content_only=true` pour le texte)
- données structurées (prix, offres, listings) → `url` + `expected_fields` (+ `required_fields`)
- explorer, naviguer, interagir → `url` + `objective`
- comparer des pages → un appel par page, en parallèle
- son compte / sa session → `session_id` (+ `url`)
- route réseau / géolocalisation → seulement si demandée, dans `objective`

Walter Browse choisit seul le chemin le plus léger (recherche légère, HTTP, extraction, rejeu d'API appris, navigateur
furtif) et l'escalade : ne pas imposer curl, Scrapling, Camoufox, Playwright ni des sélecteurs, ne pas créer de
capability à la main, ne jamais passer de cookie ou de jeton en argument. Résumer le JSON rendu, ne pas le recopier.

## Frontière avec `computer_use`

`walter_browse` pour tout contenu Web (recherche, page, extraction, interaction, session de site). `computer_use`
seulement pour la surface native du Mac : lancer une app, Finder, barre d'adresse, dialogue OS, canvas, ou une action
demandée « sur mon Mac ». Un site ouvert dans une app ne suffit pas à choisir `computer_use`. Jamais les deux chemins
pour une tâche ordinaire.

## Réseau

Réseau `local` par défaut. VPN / proxy / sortie pays seulement si Monsieur le demande ; le routeur l'applique par
session, jamais au réseau global.

## Site connecté comme Monsieur

- `browser_session(site, session)` ouvre une session connectée (sites : `browser_sites()` ; ajouter un site dans
  `/opt/walter-core/browser_sites.json`), puis `/opt/walter-core/bin/walter-browser [-e chromium] -s <session>
  new|nav|snap|click|clickxy|ktype|shot|eval|upload|fetch|close` (ou `login SITE`). Moteurs : Camoufox Max
  (127.0.0.1:9377, défaut) ; CloakBrowser, Chromium furtif (127.0.0.1:9378), `-e chromium` quand le site l'exige.
- **Ne jamais extraire de cookies soi-même** (base Cookies de Brave, trousseau, LevelDB) : ils sont injectés côté
  serveur, l'agent ne reçoit que des métadonnées. Les procédures anciennes qui le décrivent (`web-service-browser`,
  `webtop-authenticated-browsing`, `mac-brave-walter`) servent d'historique et de dépannage.
- Mot de passe, création de compte, code 2FA ou code reçu par e-mail : `bitwarden-logins` (domaine secrets), jamais de
  mot de passe dans le chat ni dans les arguments.

## Quel skill ouvrir (domaine web)

| Besoin | Skill |
|---|---|
| Un résultat de `walter_browse` vide, faux ou incomplet : comprendre son routage, ses diagnostics, sa CLI | `universal-web-extraction-router` |
| Page bloquée : 403/429, paywall, WAF, mur anti-bot | `blocked-page-recovery` |
| Extraction en masse / crawl (diagnostic Scrapling) | `scrapling` |
| Session authentifiée qui ne tient pas (cookies présents mais pas de session) | `authenticated-session-fallbacks` |
| Document derrière un portail connecté (OTP, Cloudflare) | `authenticated-portal-document-retrieval` |
| Étape sensible que Monsieur doit faire lui-même | `human-in-the-loop-gate` |
| Remplir un profil de service connecté avec preuves | `authenticated-profile-evidence-gates` |
| API du serveur Camoufox Max (contrat, smoke test, pages dynamiques, React/SPA) | `camoufox-max-api-current` |
| Chromium réel via Playwright CDP dans le webtop ; administration du webtop | `playwright-cdp-browser-control`, `webtop-authenticated-browsing` |
| Brave séparé sur le Mac (CDP 9226) pour DataDome / Cloudflare | `mac-brave-walter` |
| Services web avec session (Gemini, Suno, Grok…) | `web-service-browser` |
| Google Flow ; sessions Google OAuth persistantes | `google-flow-authenticated-access`, `google-oauth-session-persistence` |
| Profils X / Facebook / Instagram sans API | `camoufox-social-scrape` |
| Prix exacts, disponibilités, preuves qui se contredisent | `research-evidence-verification` (domaine research) |

En réserve (`skill_read` le ramène automatiquement) : `anti-bot-navigation`, `agentic-web-navigation`,
`hermes-camoufox-setup`, `google-auth-novnc`.

## Worked / failed

- Worked: one `walter_browse(query=…)` per sub-question, in parallel, then `url=` + `content_only=true` on the primary
  sources found.
- Failed (2026-11-27): reading this skill and two others before every plain search: 15–28 s and up to 41 k characters
  per request, for no change in the calls made afterwards.
