---
name: ai-model-research
description: "Use when analyzing a stealth or unknown LLM's identity."
version: 1.0.1
author: W.Alter
license: MIT
triggers:
  - stealth model
  - mystery model
  - who made this model
  - nouveau modèle openrouter
  - ox alpha
  - hunter alpha
metadata:
  hermes:
    tags: [research, llm, openrouter, stealth, community-sentiment]
---

# AI Model Research — identité, spécs vérifiées, sentiment communautaire

## When to Use

- Un modèle inconnu/nouveau apparaît (surtout OpenRouter `stealth/*`) et Monsieur demande
  ce que c'est, qui l'a fait, ou ce qu'il vaut.
- Vérifier des spécs annoncées (contexte, modalités, prix) contre la source primaire.
- Miner le sentiment X/Reddit sur un modèle avant de recommander de l'adopter.

Méthode pour toute question « c'est quoi ce modèle / qui est derrière / quelles sont ses vraies
spécs ». Déclenchée en pratique par les releases anonymes OpenRouter (stealth/*, ~1 par mois en
2026) mais généralisable à tout nouveau modèle.

## Étape 1 — Spécs vérifiées : passer par l'API, jamais la page HTML

La page HTML du modèle sur OpenRouter est protégée (challenge). La source primaire est l'API
publique : `GET https://openrouter.ai/api/v1/models` (User-Agent suffit, pas de clé).

⚠️ L'endpoint par-ID (`/api/v1/models/<id>`) peut renvoyer 404 alors que le modèle existe.
Toujours requêter la liste complète et filtrer sur l'id.

Champs à extraire : `architecture.input_modalities`/`output_modalities`, `context_length`,
`pricing`, `reasoning.mandatory`/`default_effort`, `supported_parameters`, date de création.

## Étape 2 — Discipline claims vs preuves (non négociable)

- Modalités annoncées, label « frontier », chiffres de capacité (ex. « 100T tokens/jour »),
  « zero data retention » = **déclarations du provider**, jamais des faits vérifiés.
  Les présenter comme tels à Monsieur, chaque fois.
- $0 en preview ≠ prix final (fenêtre gratuite ~1 semaine, prix d'après inconnu).
  Ne jamais budgéter dessus.
- Rétention : « not used for training » ≠ pas de logs. Ne pas router de données sensibles
  vers un provider anonyme sans avertir.

## Étape 3 — Sentiment communautaire (X + Reddit)

- **Reddit bloque en direct** (403 sur www, old.reddit et les .json). Ne pas hammer reddit.com.
  Route fiable : trouver les IDs de threads via moteur (`site:reddit.com "<sujet>"`), puis
  commentaires complets via miroir Arctic Shift :
  `https://arctic-shift.photon-reddit.com/api/comments/search?link_id={id_base36_sans_t3}&limit=100`
  → JSON brut (scores, auteurs, corps). Fallback texte intégral : PullPush
  `https://api.pullpush.io/reddit/search/comment/?q=%22...%22&size=40` (index peut laguer
  de quelques jours). Les params free-text d'Arctic Shift (`title=`, `body=`, `ids=`) renvoient
  souvent 400 — ne pas s'acharner, passer par link_id.
- **X/Twitter** : l'outil x_search est gated par crédits xAI (erreur spending-limit sans
  abonnement). Sans crédits, citer X *via* les posts Reddit qui le relaient, en marquant
  le relais.
- Restituer par **camps** avec la force de chaque signal, puis consensus transversal, puis
  avis tranché. Citer les tests concrets (benchmarks communautaires type EQ-Bench, tests
  comportementaux de similarité, tests de censure).

## Étape 4 — Spéculation d'identité : méthode avant intuition

- Ancrer dans l'historique du playbook stealth : qui a déjà utilisé l'anonymat, délais de
  reveal passés (5 jours à 2 mois), quel labo a eu quel canal.
- Distinguer signaux de **style** (chevauchement de formulations — copiable, faible) des
  signaux d'**architecture** (modalités, tokenizer, comportement de cache, censure — plus fiables).
- Les camps suivent souvent la méthode de leurs auteurs : utilisateurs pratiques vs testeurs
  comportementaux divergent structurellement. Le nommer explicitement.

## Cas d'étude complet

Ox Alpha (août 2026) — spécs vérifiées, camps MiMo V3 vs GLM 5.3, consensus :
voir `references/ox-alpha-case-study.md`.

Skills liées : `model-id-lookup` (résolution d'ID exacte avant usage — user-owned),
`blocked-page-recovery` (ladder générique pages bloquées — user-owned).
