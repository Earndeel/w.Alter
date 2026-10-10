---
name: colab-external-gpu
description: "Use when using Colab as an external GPU. Check limits."
---

# Colab comme GPU externe

## Source vivante

Lire la FAQ officielle avant de conseiller un accès distant ou de citer un quota, un GPU ou une durée : https://research.google.com/colaboratory/faq.html.

## Règles de décision

- Vérifier le plan déjà détenu par Monsieur avant de raisonner comme si Colab était gratuit ou de recommander un nouvel abonnement GPU : les plans Google AI éligibles peuvent inclure des compute units et des avantages Colab. Lire l'annonce officielle https://developers.googleblog.com/colab-is-now-part-of-your-google-ai-plan/ puis la FAQ et les droits visibles du compte ; distinguer abonnement payant et période d'essai, déploiement progressif, Google AI Pro et Ultra.
- Ne pas transformer une annonce d'accès A100/H100 en garantie d'allocation : distinguer GPU éligible et GPU réellement attribué. Ne pas assimiler les avantages Pro à l'exécution en arrière-plan d'Ultra. Un quota de compute units n'est pas un nombre d'heures ; ne donner une conversion qu'après vérification du taux de consommation effectif.
- Si une réponse précédente a omis les avantages inclus d'un abonnement existant, corriger explicitement l'analyse économique plutôt que répéter les limites du gratuit.
- Distinguer calcul ponctuel dans un notebook interactif et worker GPU autonome. Le GPU appartient au runtime Colab ; il ne devient pas un périphérique CUDA de la VM de l'agent.
- Ne pas proposer Colab gratuit comme worker distant : la FAQ interdit le contrôle distant (SSH/desktop), les workers de calcul distribué et le contournement de l'interface notebook au profit d'une interface web lorsque le runtime est gratuit ou sans solde de compute units positif.
- Expliquer qu'une offre payante avec un solde positif lève ces restrictions spécifiques, pas les interdictions générales des runtimes gérés (dont les services web sans lien avec le calcul interactif Colab). Vérifier l'adéquation du projet plutôt que de promettre une autorisation générale d'hébergement.
- Ne pas promettre un type de GPU, un quota fixe ou une disponibilité permanente : les ressources et délais d'inactivité sont variables. La FAQ indique au plus 12 h en général selon disponibilité et usage ; Pro+ permet jusqu'à 24 h d'exécution continue avec suffisamment de compute units. Vérifier la source au moment de répondre.
- Ne pas recommander de keep-alive, de multi-comptes ou de contournements des restrictions. Sauvegarder les résultats/checkpoints avant expiration et choisir un service qui autorise le mode de calcul souhaité.
- Ne pas confondre l'autorisation Google depuis le notebook avec une API de provisionnement GPU. Vérifier une API documentée avant de proposer une automatisation ; distinguer Colab grand public et Colab Enterprise sur Google Cloud.
- Vérifier les deux voies officielles avant de conclure qu'il n'existe aucune API : le MCP `googlecolab/colab-mcp` documente un pont avec une session navigateur locale ; l'API REST `colaboratory.googleapis.com` documente le provisionnement grand public, mais en bêta sur allowlist de projet, avec un scope OAuth Colab distinct. Un abonnement AI Pro ne prouve pas l'autorisation du projet. Voir `references/official-access.md`.
- Pour un test ponctuel, suivre `references/on-demand-probe.md` : une création Drive ou un bouton GPU ne constitue jamais une preuve d'allocation ni un délai mesuré.
- Garder les données sensibles et secrets hors des exemples et limiter les autorisations. Les notebooks persistent dans Drive, mais les runtimes et fichiers locaux sont éphémères.
- Lors d'une question de faisabilité, expliquer sans créer de compte, lancer de runtime, acheter des crédits ou modifier l'infrastructure.

## Priorité sur le guide général

Pour Colab, appliquer ces garde-fous plutôt que les anciennes indications du skill free-gpu-stack concernant T4 garanti, sessions gratuites de durée fixe, API REST non documentée ou scripts keep-alive.
