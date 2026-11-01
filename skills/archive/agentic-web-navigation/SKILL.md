---
name: agentic-web-navigation
description: 'Use for designing agentic browsing stacks or complex interactive navigation; normal public web extraction routes through walter_browse.'
---

# Navigation web agentique — architecture et choix de stack

## Pré-recherche structurée avant navigation

Quand une recherche live peut être séparée en un scan structuré peu coûteux puis une vérification navigateur, appliquer le pattern décrit dans `references/flight-preflight-engine.md` : générer la requête source, collecter et normaliser les cartes, filtrer/classer localement, puis naviguer uniquement sur les meilleurs candidats. Traiter les prix live comme des observations horodatées et garder un fallback navigateur pour les faits de réservation.

## Déclencheur

Utiliser ce skill pour comparer ou concevoir des solutions de navigation web
agentique, choisir une architecture multi-sites, ou exécuter une collecte qui
combine recherche, interaction et analyse visuelle. Pour une extraction
structurée normale sur une URL connue, utiliser `walter_browse` et ne pas
charger ce skill comme routeur concurrent.

## Principe directeur

Il n’existe pas de « meilleur navigateur agentique » universel. Séparer quatre couches :

1. **Découverte** : moteur de recherche et identification des sources.
2. **Extraction** : lecture rapide et structurée du contenu.
3. **Interaction** : navigation JavaScript, formulaires, filtres, clics et sessions.
4. **Résilience** : session authentifiée, anti-bot, géolocalisation et escalade.

Ne pas utiliser un navigateur agentique lourd pour une page qui se laisse extraire proprement. Inversement, ne pas prétendre qu’un extracteur sait remplir un formulaire ou sélectionner une chambre.

## Routage par défaut

### Recherche sans URL connue

- Utiliser le moteur de recherche pour la découverte.
- Dédupliquer les domaines et produire une liste de sources candidates.
- Ne pas ouvrir un navigateur stealth pour la simple recherche de liens.

### URL connue — extraction ou recherche de contenu

1. Pour une extraction structurée, appeler `walter_browse` en `mode=auto` avec
   le contrat de champs ; le tool choisit Scrapling, Camoufox ou Webtop selon
   les preuves disponibles.
2. Pour une interaction explicitement nécessaire — clics, formulaires, filtres,
   login ou inspection visuelle — utiliser directement le navigateur adapté.
3. Réserver les appels directs à Scrapling au bulk/crawl, aux diagnostics ou à
   l'absence de `walter_browse`.
4. Ne déclarer un échec que si les données nécessaires sont absentes, bloquées,
   tronquées ou derrière un login ; un HTTP 200 isolé ne vaut pas succès.

### Tâche exigeant une interaction dès le départ

Si la demande exige explicitement des clics, saisies, dates, filtres, sélection d’options, téléchargement ou observation visuelle interactive, utiliser directement Playwright/CDP ou le navigateur adapté. Ne pas faire passer une interaction pour une extraction Scrapling qui aurait « échoué ».

### Échec du navigateur ou protection forte

- Session personnelle/authentifiée : rester sur Camoufox Max, Webtop Chromium ou Brave Mac CDP selon la session disponible.
- Page publique bloquée, géolocalisée ou à gros volume : envisager ultérieurement un navigateur cloud/proxy comme Browserbase, Browserless, Steel ou une solution équivalente. Ce n’est pas la route par défaut.
- Ne jamais envoyer les cookies personnels à un service cloud d’unblocking.
- Bright Data reste une option de secours publique, pas une dépendance de la navigation personnelle.

## Choix des briques

| Brique | Rôle | Choix recommandé |
|---|---|---|
| Playwright/CDP | Contrôle déterministe du navigateur | Socle des interactions |
| Scrapling | Backend d'extraction bulk/diagnostic | Appelé par Walter Browse ou utilisé directement seulement pour bulk/crawl |
| Stagehand | Couche sémantique `observe`/`act`/`extract` | À tester pour des interfaces DOM imprévisibles |
| Browser Use Cloud | Agent autonome piloté en langage naturel | POC ou service cloud turnkey, pas forcément adapté aux cookies personnels |
| Skyvern | Workflows visuels et persistants | Automatisations métier longues |
| Browserbase/Browserless/Steel | Infrastructure de navigateurs cloud parallèles | Seulement si le volume ou l’isolation le justifie |
| Camoufox/Camofox Browser | Anti-détection et sessions protégées | Escalade spécialisée, pas navigateur universel |
| Hermes browser | Accès opérationnel rapide | Tâches simples et interactions courtes |

Les descriptions de capacités fournies par les vendeurs sont des affirmations commerciales, pas des garanties de taux de réussite. Évaluer toujours sur les domaines réels, avec le même profil réseau, les mêmes cookies et les mêmes critères de sortie.

## Boucle agentique locale : browser-use × Camoufox (validé)

Le remplacement local de « Stagehand/Browser Use Cloud » est **browser-use 0.4.5**
(celle de l'ère Playwright native) qui pilote une instance Camoufox : boucle
LLM `observe → act → extract` DANS la page, avec anti-détection Firefox, hook
React fiber et sortie IP FR. Recette complète, versions exactes, venv isolé et
benchmark chiffré : `references/browser-use-camoufox-integration.md`.

Position dans la stack (confirmée par benchmark, 2026-08-11) :
- `walter_browse` = boucle de routage/jugement au sommet, imbattable sur
  JSON/API (0,5 s, ~0 token) ;
- browser-use×Camoufox = backend d'escalade quand l'extraction échoue sur du
  HTML statique ou une page interactive (lit le DOM, tolère les formulaires) ;
- le trou connu de `walter_browse` : son scorer ne valide que des candidats
  JSON/XHR — un HTML brut de 49 Ko peut donner zéro record. Un fallback DOM
  (hook React ou projection DOM) est le correctif à prévoir avant d'escalader.

**PITFALL version (cher)** : browser-use ≥ 0.13 (CLI 3.0, « Browser Harness »)
est CDP-only et ne peut JAMAIS piloter Camoufox (Firefox). Ne pas perdre de
temps avec. La bonne version est 0.4.5 (`Browser = PatchrightBrowser |
PlaywrightBrowser`) avec `openai==1.85.0` épinglé.

## Recherche approfondie multi-sites

Pour une comparaison de prix, d’hôtels, de chambres ou de produits :

1. Définir les paramètres qui rendent les offres comparables : dates, voyageurs, devise, taxes, frais, annulation, repas, type de chambre/produit et disponibilité.
2. Découvrir les sources via recherche.
3. Lancer une collecte parallèle bornée, idéalement une session isolée par domaine.
4. Utiliser `walter_browse` pour les pages publiques structurées ; utiliser le
   navigateur direct uniquement pour les formulaires, filtres, sessions ou
   interactions qui ne peuvent pas être exprimés par un contrat de champs.
5. Escalader site par site lorsqu'un domaine bloque ou nécessite une session.
6. Normaliser les résultats dans un schéma commun et conserver URL, heure de
   collecte et statut de validation.
7. Pour les photos, récupérer les images disponibles puis inspecter visuellement une sélection représentative ; ne pas comparer uniquement les textes marketing.
8. Marquer explicitement les champs non vérifiés, estimés ou dépendants d’une session.

## Critères de décision

Évaluer une solution sur :

- fidélité d’extraction et possibilité de vérifier la source ;
- contrôle déterministe versus autonomie opaque ;
- conservation et isolation des cookies ;
- résistance aux protections sur les domaines réellement visés ;
- latence, coût par tâche et coût des appels LLM ;
- parallélisme et limites de domaine ;
- reproductibilité, logs et captures de preuve ;
- possibilité de rester local et de changer de fournisseur.

## Vérification avant de conclure

- Les offres sont-elles comparées dans les mêmes conditions ?
- Le prix inclut-il les taxes et frais annoncés ?
- La page a-t-elle été réellement chargée ou seulement trouvée dans un extrait ?
- Le compte authentifié est-il le bon ?
- Les données proviennent-elles du domaine attendu ?
- Une capture, une URL ou un extrait permet-il de justifier chaque donnée importante ?
- Un échec d’un domaine a-t-il été isolé au lieu de contaminer toute la collecte ?

## Référence

Pour le paysage de solutions et les sources officielles consultées, voir `references/solution-landscape.md`.

Pour la recherche de prix d'hôtels avec dates spécifiques (Google Hotels, recherche en thaï, anti-bot OTAs), voir `references/google-hotels-travel-pricing.md`.
