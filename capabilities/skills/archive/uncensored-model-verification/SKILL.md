---
name: uncensored-model-verification
description: "Use when a model is claimed uncensored; verify by probe."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [llm, validation, uncensored, providers]
---

# Uncensored Model Verification

## Quand utiliser
- Un provider ou un repo revendique un modèle « uncensored » / « abliterated » et l'utilisateur en attend un comportement sans restriction.
- Avant de router des requêtes sensibles vers ce modèle, ou de recommander un setup (SaaS vs local).

## Procédure

1. **Lire la config vivante** : provider, `api`, `key_env` et `default_model` dans `/root/.hermes/config.yaml` (section `providers:`). Sourcer `/root/.hermes/.env` pour la clé ; ne jamais la coller dans les arguments d'outils.
2. **Sonde brute** : curl direct vers l'endpoint chat/completions du provider avec la requête sensible cible (celle de l'usage prévu, pas un test générique), SANS system prompt. La persona de session (SOUL.md) masque le comportement nu du modèle.
3. **Isoler model vs provider** : chercher le même modèle sur OpenRouter (`GET /api/v1/models`) et refaire la même sonde. Refus plus sec en base = le fine-tune du provider désaligne réellement ; refus identique = fine-tune cosmétique ou rebaptisage.
4. **Éliminer Hermes** : Hermes est un relais sans couche de modération. Un refus provient soit des poids (alignement ancré), soit du system prompt de session — éditer la persona n'enlève pas l'alignement des poids.
5. **Conclure en palier** : un modèle qui donne le principe mais refuse les détails opératoires a un dégrossissage, pas un abliteration. Pour du réellement pur : modèle local ablité (GGUF via Ollama/vast.ai).

## Règles
- « Uncensored » vérifié = une sonde directe qui réussit sur l'usage cible. Jamais un label, jamais un compte de téléchargements HF.
- Ne pas jailbreaker la session courante pour tester : le test pertinent est le modèle nu sur endpoint dédié.
- Préférer toujours un test réel (une requête) à un benchmark ou un read-me.

## Références
- `references/serving-uncensored-local.md` — pattern vast.ai pour servir un MoE 100B+ ablité en GGUF (dimensionnement, offres, coûts).

## Pitfalls
- Les variantes « uncensored » d'un modèle sont souvent des quantisations tierces (FP8/GGUF) publiées par des providers, pas l'éditeur : même nom de famille, alignement différent. Toujours sonder l'artefact exact qui servira en production.
- Un provider peut servir un modèle différent de celui étiqueté (rebaptisage) : une sonde de comportement double comme vérification d'identité du modèle servi.
- L'alignement résiduel ressort surtout sur les sujets à enjeu judiciaire ; les tests anodins ne prouvent rien.
